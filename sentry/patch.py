# Copyright 2016-2017 Versada <https://versada.eu/>
# Copyright 2021 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

"""
Monkey-patching for Sentry APM (Application Performance Monitoring).

This module provides instrumentation for:
- HTTP request handling with transaction names and user context
- SQL query tracing for database performance analysis
- Cron job transactions
- Queue job tagging (if queue_job module is installed)
"""

import logging

_logger = logging.getLogger(__name__)

HAS_SENTRY_SDK = True
try:
    import sentry_sdk
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
except ImportError:
    HAS_SENTRY_SDK = False


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
            sentry_sdk.set_user({"id": uid, "email": session.get("login")})
        db = getattr(session, "db", None)
        if db:
            sentry_sdk.set_tag("odoo.db", db)


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

    _ori_serve_db = Request._serve_db
    _ori_serve_nodb = Request._serve_nodb

    def _serve_db(self):
        _set_request_context(self)
        return _ori_serve_db(self)

    def _serve_nodb(self):
        _set_request_context(self)
        return _ori_serve_nodb(self)

    Request._serve_db = _serve_db
    Request._serve_nodb = _serve_nodb
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
            params = getattr(self.request, "params", None) or {}
            for key in ("model", "method"):
                if key in params:
                    sentry_sdk.set_tag(f"odoo.{key}", params[key])

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
        span_kwargs = {_SPAN_NAME_KWARG: str(query)[:1000] if query else ""}
        with sentry_sdk.start_span(op="db.sql.query", **span_kwargs) as span:
            if hasattr(self, "dbname"):
                span.set_data("db.name", self.dbname)
            return _ori_execute(
                self, query, params=params, log_exceptions=log_exceptions
            )

    Cursor.execute = execute
    _logger.debug("Patched odoo.sql_db.Cursor.execute for Sentry APM")


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

    @classmethod
    def _process_job(cls, db, cron_cr, job):
        cron_name = job.get("cron_name", "unknown").replace(" ", "_")
        with sentry_sdk.start_transaction(
            op="cron",
            name=f"Cron: {cron_name}",
            source=TRANSACTION_SOURCE_ROUTE,
        ) as transaction:
            transaction.set_tag("odoo.cron.name", job.get("cron_name", "unknown"))
            transaction.set_tag("odoo.cron.id", job.get("id", "unknown"))
            if hasattr(cron_cr, "dbname"):
                transaction.set_tag("odoo.db", cron_cr.dbname)
            return _ori_process_job.__func__(cls, db, cron_cr, job)

    ir_cron._process_job = _process_job
    _logger.debug("Patched ir_cron._process_job for Sentry APM")


def patch_queue_job():
    """
    Monkey-patch the queue_job module (if installed) to add Sentry tags
    for job model and method.
    """
    if not HAS_SENTRY_SDK:
        return

    try:
        from odoo.addons.queue_job.jobrunner.runner import QueueJobRunner
    except ImportError:
        _logger.debug("queue_job module not installed, skipping APM patch")
        return

    if not hasattr(QueueJobRunner, "_try_perform_job"):
        _logger.debug("QueueJobRunner._try_perform_job not found, skipping patch")
        return

    _ori_try_perform_job = QueueJobRunner._try_perform_job

    def _try_perform_job(self, env, job):
        sentry_sdk.set_tag("odoo.job.model", job.model_name)
        sentry_sdk.set_tag("odoo.job.method", job.method_name)
        sentry_sdk.set_tag("odoo.job.uuid", job.uuid)
        return _ori_try_perform_job(self, env, job)

    QueueJobRunner._try_perform_job = _try_perform_job
    _logger.debug("Patched QueueJobRunner._try_perform_job for Sentry APM")


def apply_apm_patches():
    """
    Apply all APM monkey-patches to instrument Odoo for Sentry performance monitoring.
    """
    _logger.info("Applying Sentry APM patches...")
    patch_odoo_request()
    patch_cursor_execute()
    patch_cron_job()
    patch_queue_job()
    _logger.info("Sentry APM patches applied successfully")
