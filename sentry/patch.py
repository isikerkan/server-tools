# Copyright 2026 Erkan Isik
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

"""
Monkey-patching for Sentry APM (Application Performance Monitoring).

This module provides instrumentation for:
- HTTP request handling with transaction names and user context
- SQL query tracing for database performance analysis
- Cron job transactions
- Queue job tagging (if queue_job module is installed)
- Optional metrics (request/cron counters and duration distributions)
"""

import logging
import re
import threading
import time
from contextlib import contextmanager

_logger = logging.getLogger(__name__)

# Written by the _run_job patch, read by the _process_job wrapper to
# report the real job outcome to Sentry Crons (Odoo handles job
# failures internally, so no exception reaches _process_job)
_cron_state = threading.local()

HAS_SENTRY_SDK = True
sentry_metrics = None
try:
    import sentry_sdk

    try:
        # sentry-sdk >= 2.23: enum replaces the removed string constants
        from sentry_sdk.tracing import TransactionSource

        TRANSACTION_SOURCE_ROUTE = TransactionSource.ROUTE
    except ImportError:
        from sentry_sdk.tracing import TRANSACTION_SOURCE_ROUTE

    # sentry-sdk >= 2.15 renamed the span `description` kwarg to `name`
    # and warns on the old one
    import inspect as _inspect

    from sentry_sdk.tracing import Span as _Span

    _SPAN_NAME_KWARG = (
        "name"
        if "name" in _inspect.signature(_Span.__init__).parameters
        else "description"
    )

    try:
        # sentry-sdk >= 2.63
        from sentry_sdk import metrics as sentry_metrics
    except ImportError:
        sentry_metrics = None
except ImportError:
    HAS_SENTRY_SDK = False

# Idempotency guard: post_load can run more than once per process
_PATCHES_APPLIED = False
# Set from config by apply_apm_patches()
_METRICS_ENABLED = False
_ORM_ENABLED = False
_ORM_PATCHED = False
_CRON_MONITORS_ENABLED = False
_CRON_MONITORS_INCLUDE = ()

# ORM methods traced when sentry_trace_orm is enabled
ORM_TRACED_METHODS = ("create", "write", "unlink", "read", "_search")

# ir.cron interval_type -> Sentry monitor schedule unit
CRON_UNIT_MAP = {
    "minutes": "minute",
    "hours": "hour",
    "days": "day",
    "weeks": "week",
    "months": "month",
}
# Grace period before a missed check-in alerts, and runtime cap (minutes)
CRON_CHECKIN_MARGIN = 5
CRON_MAX_RUNTIME = 30

# Numeric path segments (record ids, attachment ids, ...) would explode
# metric attribute cardinality
_ID_SEGMENT_RE = re.compile(r"/\d+")


def _scrub_path(path):
    """Replace numeric path segments so metric attributes stay low-cardinality."""
    return _ID_SEGMENT_RE.sub("/:id", path)


def _send_default_pii():
    client = sentry_sdk.get_client()
    return bool(client and client.options.get("send_default_pii"))


def _set_request_context(request):
    """Set Sentry transaction name, user and tags from an Odoo request."""
    path_info = request.httprequest.environ.get("PATH_INFO", "/")
    scope = sentry_sdk.get_current_scope()
    scope.set_transaction_name(path_info, source=TRANSACTION_SOURCE_ROUTE)
    sentry_sdk.set_tag("odoo.path", path_info)

    session = getattr(request, "session", None)
    if session is not None:
        uid = getattr(session, "uid", None)
        if uid:
            user = {"id": uid}
            if _send_default_pii():
                user["email"] = session.get("login")
            sentry_sdk.set_user(user)
        db = getattr(session, "db", None)
        if db:
            sentry_sdk.set_tag("odoo.db", db)


def _emit_request_metrics(request, started):
    if not (_METRICS_ENABLED and sentry_metrics):
        return
    attributes = {
        "path": _scrub_path(request.httprequest.environ.get("PATH_INFO", "/")),
        "db": getattr(getattr(request, "session", None), "db", None) or "",
    }
    elapsed_ms = (time.monotonic() - started) * 1000.0
    sentry_metrics.count("odoo.request", 1, attributes=attributes)
    sentry_metrics.distribution(
        "odoo.request.duration",
        elapsed_ms,
        unit="millisecond",
        attributes=attributes,
    )


def patch_odoo_request():
    """
    Monkey-patch Odoo's HTTP request handling to set Sentry transaction
    names, user context, and tags for better APM filtering.

    Since Odoo 16 there is no ``odoo.http.Root`` anymore; requests are
    served through ``odoo.http.Request._serve_db`` / ``_serve_nodb``,
    so those are patched instead.
    """
    if not HAS_SENTRY_SDK:
        return

    try:
        from odoo.http import Request
    except ImportError:
        _logger.warning("Could not import odoo.http.Request for APM patching")
        return

    def _wrap_serve(original):
        def _serve(self):
            # Never let Sentry instrumentation break request processing
            try:
                _set_request_context(self)
            except Exception:
                _logger.debug("Sentry request context failed", exc_info=True)
            started = time.monotonic()
            try:
                return original(self)
            finally:
                try:
                    _emit_request_metrics(self, started)
                except Exception:
                    _logger.debug("Sentry request metrics failed", exc_info=True)

        return _serve

    Request._serve_db = _wrap_serve(Request._serve_db)
    Request._serve_nodb = _wrap_serve(Request._serve_nodb)
    _logger.debug("Patched odoo.http.Request._serve_db/_serve_nodb for Sentry APM")

    try:
        from odoo.http import JsonRPCDispatcher
    except ImportError:
        _logger.debug("JsonRPCDispatcher not found, skipping model/method tags")
        return

    _ori_dispatch = JsonRPCDispatcher.dispatch

    def dispatch(self, endpoint, args):
        try:
            return _ori_dispatch(self, endpoint, args)
        finally:
            # params are only parsed inside dispatch(); tag afterwards so
            # the tags are on the scope before any exception is captured
            try:
                params = getattr(self.request, "params", None) or {}
                for key in ("model", "method"):
                    if key in params:
                        sentry_sdk.set_tag(f"odoo.{key}", params[key])
            except Exception:
                _logger.debug("Sentry dispatch tags failed", exc_info=True)

    JsonRPCDispatcher.dispatch = dispatch
    _logger.debug("Patched odoo.http.JsonRPCDispatcher.dispatch for Sentry APM")


def patch_cursor_execute():
    """
    Monkey-patch the database cursor's execute method to trace SQL queries.
    This allows Sentry to capture database performance metrics.
    """
    if not HAS_SENTRY_SDK:
        return

    try:
        from odoo.sql_db import Cursor
    except ImportError:
        _logger.warning("Could not import odoo.sql_db.Cursor for APM patching")
        return

    _ori_execute = Cursor.execute

    def execute(self, query, params=None, log_exceptions=True):
        # Fast path: skip stringification and span allocation entirely
        # when there is no sampled transaction. Odoo issues thousands of
        # queries per request; this must cost nothing when untraced.
        current = sentry_sdk.get_current_span()
        if current is None or not current.sampled:
            return _ori_execute(
                self, query, params=params, log_exceptions=log_exceptions
            )

        span_kwargs = {_SPAN_NAME_KWARG: str(query)[:1000] if query else ""}
        with sentry_sdk.start_span(op="db.sql.query", **span_kwargs) as span:
            if hasattr(self, "dbname"):
                span.set_data("db.name", self.dbname)
            return _ori_execute(
                self, query, params=params, log_exceptions=log_exceptions
            )

    Cursor.execute = execute
    _logger.debug("Patched odoo.sql_db.Cursor.execute for Sentry APM")


def _cron_monitor_slug(dbname, cron_name):
    """Sentry monitor slug: max 50 chars of [a-z0-9-_], db-prefixed so
    the same cron on different databases gets distinct monitors."""
    slug = re.sub(r"[^a-z0-9_-]+", "-", f"{dbname}-{cron_name}".lower())
    return slug.strip("-")[:50] or "unknown"


def _cron_checkin_start(job, dbname):
    """Open a Sentry Crons check-in for this run. The monitor and its
    schedule are upserted from the cron's own interval, so missed and
    late runs are detected without any setup in Sentry."""
    if not _CRON_MONITORS_ENABLED:
        return None, None
    cron_name = job.get("cron_name") or ""
    if _CRON_MONITORS_INCLUDE and cron_name not in _CRON_MONITORS_INCLUDE:
        return None, None

    from sentry_sdk.crons import MonitorStatus, capture_checkin

    monitor_config = None
    unit = CRON_UNIT_MAP.get(job.get("interval_type"))
    if unit and job.get("interval_number"):
        monitor_config = {
            "schedule": {
                "type": "interval",
                "value": job["interval_number"],
                "unit": unit,
            },
            "checkin_margin": CRON_CHECKIN_MARGIN,
            "max_runtime": CRON_MAX_RUNTIME,
            "timezone": "UTC",
        }
    slug = _cron_monitor_slug(dbname, cron_name)
    check_in_id = capture_checkin(
        monitor_slug=slug,
        status=MonitorStatus.IN_PROGRESS,
        monitor_config=monitor_config,
    )
    return slug, check_in_id


def _cron_checkin_finish(slug, check_in_id, ok, duration):
    if not check_in_id:
        return
    from sentry_sdk.crons import MonitorStatus, capture_checkin

    capture_checkin(
        monitor_slug=slug,
        check_in_id=check_in_id,
        status=MonitorStatus.OK if ok else MonitorStatus.ERROR,
        duration=duration,
    )


def _finish_checkin_safe(slug, check_in_id, ok, started):
    try:
        _cron_checkin_finish(slug, check_in_id, ok, time.monotonic() - started)
    except Exception:
        _logger.debug("Sentry cron check-in failed", exc_info=True)


@contextmanager
def _cron_transaction(cron_name, job, dbname):
    """Run a cron job inside its own Sentry transaction and scope.

    The scopes are forked so the transaction name and tags do not
    outlive the job: cron threads are long-lived and an error raised
    later on the same thread (for instance the connection poll during
    shutdown) would otherwise be attributed to the last job that ran.
    """
    with (
        sentry_sdk.isolation_scope(),
        sentry_sdk.start_transaction(
            op="cron",
            name=f"Cron: {cron_name.replace(' ', '_')}",
            source=TRANSACTION_SOURCE_ROUTE,
        ) as transaction,
    ):
        transaction.set_tag("odoo.cron.name", cron_name)
        transaction.set_tag("odoo.cron.id", job.get("id") or "unknown")
        if dbname:
            transaction.set_tag("odoo.db", dbname)
        yield transaction


def patch_cron_job():
    """
    Monkey-patch Odoo's cron job processing to create Sentry transactions
    for each cron execution.
    """
    if not HAS_SENTRY_SDK:
        return

    try:
        from odoo.addons.base.models.ir_cron import ir_cron
    except ImportError:
        _logger.warning("Could not import ir_cron for APM patching")
        return

    _ori_process_job = ir_cron._process_job
    _ori_run_job = ir_cron._run_job

    @classmethod
    def _run_job(cls, job):
        # record the completion status so the check-in reflects the
        # real outcome (failed jobs do not raise out of _process_job)
        status = _ori_run_job.__func__(cls, job)
        _cron_state.last_status = status
        return status

    ir_cron._run_job = _run_job

    @classmethod
    def _process_job(cls, db, cron_cr, job):
        # job values can be NULL in the database, so .get() defaults
        # are not enough
        cron_name = job.get("cron_name") or "unknown"
        dbname = getattr(cron_cr, "dbname", "")
        started = time.monotonic()
        slug = check_in_id = None
        try:
            slug, check_in_id = _cron_checkin_start(job, dbname)
        except Exception:
            _logger.debug("Sentry cron check-in failed", exc_info=True)
        _cron_state.last_status = None
        try:
            with _cron_transaction(cron_name, job, dbname):
                result = _ori_process_job.__func__(cls, db, cron_cr, job)
            # 'failed' comes from CompletionStatus. If the status is
            # still None, _run_job was never called: that is Odoo's
            # failed_by_timeout branch, which records FAILED without
            # running the job - report it as an error too.
            status = getattr(_cron_state, "last_status", None)
            job_ok = status is not None and status != "failed"
            _finish_checkin_safe(slug, check_in_id, job_ok, started)
            return result
        except Exception:
            _finish_checkin_safe(slug, check_in_id, False, started)
            raise
        finally:
            if _METRICS_ENABLED and sentry_metrics:
                try:
                    attributes = {"cron": cron_name, "db": dbname}
                    elapsed_ms = (time.monotonic() - started) * 1000.0
                    sentry_metrics.count("odoo.cron", 1, attributes=attributes)
                    sentry_metrics.distribution(
                        "odoo.cron.duration",
                        elapsed_ms,
                        unit="millisecond",
                        attributes=attributes,
                    )
                except Exception:
                    _logger.debug("Sentry cron metrics failed", exc_info=True)

    ir_cron._process_job = _process_job
    _logger.debug("Patched ir_cron._process_job for Sentry APM")


def patch_orm():
    """
    Monkey-patch BaseModel CRUD/search methods to create ORM-level spans.
    Gives Sentry semantic visibility (model + operation) on top of the
    raw SQL spans. Opt-in via sentry_trace_orm: it adds a wrapper call
    to some of the hottest methods in Odoo. Idempotent.
    """
    global _ORM_PATCHED

    if not HAS_SENTRY_SDK or _ORM_PATCHED:
        return
    _ORM_PATCHED = True

    import functools

    try:
        from odoo.models import BaseModel
    except ImportError:
        _logger.warning("Could not import BaseModel for ORM APM patching")
        return

    def make_wrapper(method_name, original):
        # functools.wraps also copies __dict__, preserving the _api
        # attribute Odoo's call_kw dispatching relies on
        @functools.wraps(original)
        def wrapper(self, *args, **kwargs):
            current = sentry_sdk.get_current_span()
            if current is None or not current.sampled:
                return original(self, *args, **kwargs)
            span_kwargs = {_SPAN_NAME_KWARG: f"{self._name}.{method_name}"}
            with sentry_sdk.start_span(op="odoo.orm", **span_kwargs) as span:
                span.set_data("odoo.model", self._name)
                span.set_data("odoo.method", method_name)
                return original(self, *args, **kwargs)

        return wrapper

    for method_name in ORM_TRACED_METHODS:
        original = getattr(BaseModel, method_name, None)
        if original is None:
            _logger.debug("BaseModel.%s not found, skipping", method_name)
            continue
        setattr(BaseModel, method_name, make_wrapper(method_name, original))

    _logger.debug("Patched BaseModel ORM methods for Sentry APM")


def patch_queue_job():
    """
    Monkey-patch the queue_job module (if installed) to add Sentry tags
    for job model and method.
    """
    if not HAS_SENTRY_SDK:
        return

    try:
        from odoo.addons.queue_job.controllers.main import RunJobController
    except ImportError:
        _logger.debug("queue_job module not installed, skipping APM patch")
        return

    if not hasattr(RunJobController, "_try_perform_job"):
        _logger.debug("RunJobController._try_perform_job not found, skipping patch")
        return

    _ori_try_perform_job = RunJobController._try_perform_job

    @classmethod
    def _try_perform_job(cls, env, job):
        # jobs execute in the HTTP workers through RunJobController
        # (the jobrunner thread only dispatches HTTP calls), so this is
        # where the tags land on the job's own transaction
        try:
            sentry_sdk.set_tag("odoo.job.model", job.model_name)
            sentry_sdk.set_tag("odoo.job.method", job.method_name)
            sentry_sdk.set_tag("odoo.job.uuid", job.uuid)
        except Exception:
            _logger.debug("Sentry queue_job tags failed", exc_info=True)
        return _ori_try_perform_job.__func__(cls, env, job)

    RunJobController._try_perform_job = _try_perform_job
    _logger.debug("Patched RunJobController._try_perform_job for Sentry APM")


def apply_apm_patches(config=None):
    """
    Apply all APM monkey-patches to instrument Odoo for Sentry performance
    monitoring. Idempotent: safe to call more than once per process.
    """
    global _PATCHES_APPLIED, _METRICS_ENABLED, _ORM_ENABLED
    global _CRON_MONITORS_ENABLED, _CRON_MONITORS_INCLUDE

    if config is not None:
        from .const import config_bool, split_multiple

        _METRICS_ENABLED = config_bool(
            config, "sentry_metrics_enabled", sentry_metrics is not None
        ) and (sentry_metrics is not None)
        _ORM_ENABLED = config_bool(config, "sentry_trace_orm")
        _CRON_MONITORS_ENABLED = config_bool(config, "sentry_cron_monitors_enabled")
        _CRON_MONITORS_INCLUDE = tuple(
            split_multiple(config.get("sentry_cron_monitors_include", ""))
        )

    # per-patch flag: honored even when the base patches are already
    # applied, so a later call with sentry_trace_orm newly enabled still
    # installs the ORM spans (true idempotency per patch)
    if _ORM_ENABLED:
        patch_orm()

    if _PATCHES_APPLIED:
        _logger.debug("Sentry APM patches already applied, skipping")
        return

    _logger.info("Applying Sentry APM patches...")
    patch_odoo_request()
    patch_cursor_execute()
    patch_cron_job()
    patch_queue_job()
    _PATCHES_APPLIED = True
    _logger.info("Sentry APM patches applied successfully")
