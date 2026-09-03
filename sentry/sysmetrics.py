# Copyright 2026 Erkan Isik
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

"""
Optional host and database monitoring for Sentry Metrics.

A daemon thread periodically emits gauges so the Sentry Metrics page
shows the full picture next to the request/cron counters:

- system.cpu.percent
- system.memory.percent / system.memory.used
- system.disk.percent / system.disk.read / system.disk.write
- system.network.sent / system.network.received
- db.connections.active / db.connections.idle / db.size (per database)

Enabled with sentry_system_metrics_enabled; the interval is set with
sentry_system_metrics_interval (seconds, default 60). Requires psutil
for the host metrics; database metrics only need an Odoo cursor.
"""

import logging
import threading

_logger = logging.getLogger(__name__)

try:
    import psutil
except ImportError:
    psutil = None

try:
    from sentry_sdk import metrics as sentry_metrics
except ImportError:
    sentry_metrics = None

DEFAULT_INTERVAL = 60.0
MIN_INTERVAL = 10.0

# Sentry Crons heartbeat for the OCA queue_job jobrunner thread
QUEUE_HEARTBEAT_SLUG = "odoo-queue-jobrunner"
QUEUE_JOB_GAUGE_STATES = ("pending", "enqueued", "started", "failed")

# Set from config by start_system_metrics()
_SYSTEM_ENABLED = False
_QUEUE_ENABLED = False

_collector_thread = None
# io counters are cumulative; deltas are emitted starting from the
# second tick
_last_disk_io = None
_last_net_io = None


def _emit_host_metrics():
    global _last_disk_io, _last_net_io

    sentry_metrics.gauge(
        "system.cpu.percent", psutil.cpu_percent(interval=None), unit="percent"
    )

    memory = psutil.virtual_memory()
    sentry_metrics.gauge("system.memory.percent", memory.percent, unit="percent")
    sentry_metrics.gauge("system.memory.used", memory.used, unit="byte")

    disk = psutil.disk_usage("/")
    sentry_metrics.gauge("system.disk.percent", disk.percent, unit="percent")

    disk_io = psutil.disk_io_counters()
    if disk_io is not None:
        if _last_disk_io is not None:
            sentry_metrics.gauge(
                "system.disk.read",
                disk_io.read_bytes - _last_disk_io.read_bytes,
                unit="byte",
            )
            sentry_metrics.gauge(
                "system.disk.write",
                disk_io.write_bytes - _last_disk_io.write_bytes,
                unit="byte",
            )
        _last_disk_io = disk_io

    net_io = psutil.net_io_counters()
    if net_io is not None:
        if _last_net_io is not None:
            sentry_metrics.gauge(
                "system.network.sent",
                net_io.bytes_sent - _last_net_io.bytes_sent,
                unit="byte",
            )
            sentry_metrics.gauge(
                "system.network.received",
                net_io.bytes_recv - _last_net_io.bytes_recv,
                unit="byte",
            )
        _last_net_io = net_io


def _emit_db_metrics():
    import odoo.modules.registry
    import odoo.sql_db

    for dbname in list(odoo.modules.registry.Registry.registries.d):
        try:
            db = odoo.sql_db.db_connect(dbname)
            with db.cursor() as cr:
                cr.execute(
                    """
                    SELECT state, count(*)
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                    GROUP BY state
                    """
                )
                states = dict(cr.fetchall())
                cr.execute("SELECT pg_database_size(current_database())")
                (size,) = cr.fetchone()
            attributes = {"db": dbname}
            sentry_metrics.gauge(
                "db.connections.active",
                states.get("active", 0),
                attributes=attributes,
            )
            sentry_metrics.gauge(
                "db.connections.idle", states.get("idle", 0), attributes=attributes
            )
            sentry_metrics.gauge("db.size", size, unit="byte", attributes=attributes)
        except Exception:
            _logger.debug("Sentry db metrics failed for %s", dbname, exc_info=True)


def _jobrunner_alive():
    return any(
        type(thread).__name__ == "QueueJobRunnerThread" and thread.is_alive()
        for thread in threading.enumerate()
    )


def _emit_queue_heartbeat(interval):
    """Heartbeat check-in while the queue_job jobrunner thread lives -
    Sentry Crons alerts on the missed check-in when it dies. The queue
    itself has no schedule, so job states are reported as gauges by
    :func:`_emit_queue_gauges` instead."""
    if not _jobrunner_alive():
        return
    from sentry_sdk.crons import MonitorStatus, capture_checkin

    capture_checkin(
        monitor_slug=QUEUE_HEARTBEAT_SLUG,
        status=MonitorStatus.OK,
        monitor_config={
            "schedule": {
                "type": "interval",
                "value": max(1, round(interval / 60)),
                "unit": "minute",
            },
            "checkin_margin": 5,
            "max_runtime": 5,
            "timezone": "UTC",
        },
    )


def _emit_queue_gauges():
    """Per-database backlog gauges for queue_job states."""
    import odoo.modules.registry
    import odoo.sql_db

    for dbname in list(odoo.modules.registry.Registry.registries.d):
        try:
            db = odoo.sql_db.db_connect(dbname)
            with db.cursor() as cr:
                cr.execute("SELECT to_regclass('queue_job')")
                if cr.fetchone()[0] is None:
                    continue
                cr.execute("SELECT state, count(*) FROM queue_job GROUP BY state")
                states = dict(cr.fetchall())
            attributes = {"db": dbname}
            for state in QUEUE_JOB_GAUGE_STATES:
                sentry_metrics.gauge(
                    f"queue_job.{state}", states.get(state, 0), attributes=attributes
                )
        except Exception:
            _logger.debug(
                "Sentry queue_job metrics failed for %s", dbname, exc_info=True
            )


def _collector_loop(interval, stop_event):
    while not stop_event.wait(interval):
        # each signal is isolated: a failing host metric must not
        # suppress the db metrics, and neither may suppress the
        # heartbeat (a skipped heartbeat reads as a dead jobrunner)
        if _SYSTEM_ENABLED and psutil is not None:
            try:
                _emit_host_metrics()
            except Exception:
                _logger.debug("Sentry host metrics tick failed", exc_info=True)
        if _SYSTEM_ENABLED:
            try:
                _emit_db_metrics()
            except Exception:
                _logger.debug("Sentry db metrics tick failed", exc_info=True)
        if _QUEUE_ENABLED:
            try:
                _emit_queue_heartbeat(interval)
            except Exception:
                _logger.debug("Sentry queue heartbeat failed", exc_info=True)
            try:
                _emit_queue_gauges()
            except Exception:
                _logger.debug("Sentry queue gauges failed", exc_info=True)


def start_system_metrics(config):
    """Start the metrics collector thread once per process (idempotent).

    The thread runs when host/database metrics
    (sentry_system_metrics_enabled) or queue_job monitoring
    (sentry_queue_job_monitor_enabled) is requested."""
    global _collector_thread, _SYSTEM_ENABLED, _QUEUE_ENABLED

    from .const import config_bool

    _SYSTEM_ENABLED = config_bool(config, "sentry_system_metrics_enabled")
    _QUEUE_ENABLED = config_bool(config, "sentry_queue_job_monitor_enabled")
    if not (_SYSTEM_ENABLED or _QUEUE_ENABLED):
        return

    if sentry_metrics is None:
        _logger.warning(
            "sentry_system_metrics_enabled is set but the installed "
            "sentry-sdk has no metrics support (needs >= 2.63)"
        )
        return
    if _collector_thread is not None and _collector_thread.is_alive():
        return
    if psutil is None:
        _logger.info(
            "psutil is not installed; host metrics disabled, "
            "database metrics still emitted"
        )

    try:
        interval = float(config.get("sentry_system_metrics_interval", "") or 0)
    except ValueError:
        interval = 0
    interval = max(interval, MIN_INTERVAL) if interval else DEFAULT_INTERVAL

    stop_event = threading.Event()
    _collector_thread = threading.Thread(
        target=_collector_loop,
        args=(interval, stop_event),
        name="sentry.system_metrics",
        daemon=True,
    )
    _collector_thread.start()
    _logger.info("Sentry system metrics collector started (every %ss)", interval)
