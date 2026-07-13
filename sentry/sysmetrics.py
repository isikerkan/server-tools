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


def _collector_loop(interval, stop_event):
    while not stop_event.wait(interval):
        try:
            if psutil is not None:
                _emit_host_metrics()
            _emit_db_metrics()
        except Exception:
            # Monitoring must never take the server down
            _logger.debug("Sentry system metrics tick failed", exc_info=True)


def start_system_metrics(config):
    """Start the metrics collector thread once per process (idempotent)."""
    global _collector_thread

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
