# Copyright 2016-2017 Versada <https://versada.eu/>
# Copyright 2021 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
import warnings
from collections import abc
from decimal import Decimal

import odoo.http
from odoo.tools import config as odoo_config

from . import const
from .logutils import (
    InvalidGitRepository,
    SanitizeOdooCookiesProcessor,
    fetch_git_sha,
    get_extra_context,
)

_logger = logging.getLogger(__name__)

config_bool = const.config_bool

HAS_SENTRY_SDK = True
try:
    import sentry_sdk
    from sentry_sdk.integrations.logging import ignore_logger
    from sentry_sdk.integrations.threading import ThreadingIntegration
    from sentry_sdk.integrations.wsgi import SentryWsgiMiddleware
except ImportError:  # pragma: no cover
    HAS_SENTRY_SDK = False  # pragma: no cover
    _logger.debug(
        "Cannot import 'sentry-sdk'.\
                        Please make sure it is installed."
    )  # pragma: no cover


class Sampler:
    """
    Custom traces sampler for Sentry APM that allows different sampling rates
    for different types of operations (HTTP requests, cron jobs, queue jobs).

    This enables fine-grained control over which transactions are sent to Sentry,
    reducing costs while maintaining visibility into critical operations.
    """

    def __init__(self, config):
        """
        Initialize the sampler with configuration values.

        Args:
            config: Odoo configuration object containing sampling rate settings
        """
        # Rates are parsed once here; traces_sampler runs on every
        # transaction and must stay allocation-free.
        self.traces_sample_rate_http = float(
            Decimal(
                str(
                    config.get(
                        "sentry_traces_sample_rate_http",
                        const.DEFAULT_TRACES_SAMPLE_RATE_HTTP,
                    )
                )
            )
        )
        self.traces_sample_rate_cron = float(
            Decimal(
                str(
                    config.get(
                        "sentry_traces_sample_rate_cron",
                        const.DEFAULT_TRACES_SAMPLE_RATE_CRON,
                    )
                )
            )
        )
        self.traces_sample_rate_job = float(
            Decimal(
                str(
                    config.get(
                        "sentry_traces_sample_rate_job",
                        const.DEFAULT_TRACES_SAMPLE_RATE_JOB,
                    )
                )
            )
        )
        self.exclude_paths = tuple(
            const.split_multiple(
                config.get(
                    "sentry_traces_exclude_paths",
                    const.DEFAULT_TRACES_EXCLUDE_PATHS,
                )
            )
        )

    def traces_sampler(self, sampling_context):
        """
        Determine the sampling rate for a given transaction.

        Args:
            sampling_context: Context information about the transaction

        Returns:
            float: Sampling rate between 0 and 1
        """
        # Respect an upstream sampling decision (distributed tracing):
        # keep traces complete across services
        parent_sampled = sampling_context.get("parent_sampled")
        if parent_sampled is not None:
            return 1.0 if parent_sampled else 0.0

        # Get path from WSGI environment
        wsgi_environ = sampling_context.get("wsgi_environ", {})
        path = wsgi_environ.get("PATH_INFO", "")

        # Get operation type from transaction context
        transaction_context = sampling_context.get("transaction_context", {})
        op = transaction_context.get("op", "")

        # High-frequency, low-value paths: assets, websocket, statics, ...
        if path and path.startswith(self.exclude_paths):
            return 0.0

        # Queue job requests
        if path and path.startswith("/queue_job"):
            return self.traces_sample_rate_job

        # Cron job transactions
        if op == "cron":
            return self.traces_sample_rate_cron

        # HTTP server requests and default for unknown operations
        return self.traces_sample_rate_http


def before_send(event, hint):
    """Prevent the capture of any exceptions in
    the DEFAULT_IGNORED_EXCEPTIONS list
        -- or --
    Add context to event if include_context is True
    and sanitize sensitive data"""

    exc_info = hint.get("exc_info")
    if exc_info is None and "log_record" in hint:
        # Odoo handles UserErrors by logging the raw exception rather
        # than a message string in odoo/http.py
        try:
            module_name = hint["log_record"].msg.__module__
            class_name = hint["log_record"].msg.__class__.__name__
            qualified_name = module_name + "." + class_name
        except AttributeError:
            qualified_name = "not found"

        if qualified_name in const.DEFAULT_IGNORED_EXCEPTIONS:
            return None

    if event.setdefault("tags", {}).get("include_context"):
        cxtest = get_extra_context(odoo.http.request)
        info_request = ["tags", "user", "extra", "request"]

        for item in info_request:
            info_item = event.setdefault(item, {})
            info_item.update(cxtest.setdefault(item, {}))

    raven_processor = SanitizeOdooCookiesProcessor()
    raven_processor.process(event)

    return event


def _wrap_wsgi_application():
    """Patch ``odoo.http.Application.__call__`` so every WSGI request
    runs through SentryWsgiMiddleware, regardless of server mode or of
    when this module was loaded. Idempotent."""
    import functools

    Application = odoo.http.Application
    if getattr(Application, "_sentry_wsgi_patched", False):
        return

    _ori_call = Application.__call__

    def __call__(self, environ, start_response):
        middleware = getattr(self, "_sentry_wsgi_middleware", None)
        if middleware is None:
            middleware = SentryWsgiMiddleware(functools.partial(_ori_call, self))
            self._sentry_wsgi_middleware = middleware
        return middleware(environ, start_response)

    Application.__call__ = __call__
    Application._sentry_wsgi_patched = True


def before_send_transaction(event, hint):
    """Sanitize sensitive data (cookies, passwords) on APM transaction
    events; ``before_send`` only applies to error events."""
    SanitizeOdooCookiesProcessor().process(event)
    return event


def get_odoo_commit(odoo_dir):
    """Attempts to get Odoo git commit from :param:`odoo_dir`."""
    if not odoo_dir:
        return
    try:
        return fetch_git_sha(odoo_dir)
    except InvalidGitRepository:
        _logger.debug("Odoo directory: '%s' not a valid git repository", odoo_dir)


def initialize_sentry(config):
    """Setup an instance of :class:`sentry_sdk.Client`.
    :param config: Sentry configuration
    :param client: class used to instantiate the sentry_sdk client.
    """
    enabled = config_bool(config, "sentry_enabled")
    if not (HAS_SENTRY_SDK and enabled):
        return
    _logger.info("Initializing sentry...")
    if config.get("sentry_odoo_dir") and config.get("sentry_release"):
        _logger.debug(
            "Both sentry_odoo_dir and \
                       sentry_release defined, choosing sentry_release"
        )
    if config.get("sentry_transport"):
        warnings.warn(
            "`sentry_transport` has been deprecated.  "
            "Its not neccesary send it, will use `HttpTranport` by default.",
            DeprecationWarning,
            stacklevel=1,
        )
    options = {}
    for option in const.get_sentry_options():
        value = config.get(f"sentry_{option.key}", option.default)
        if isinstance(option.converter, abc.Callable):
            value = option.converter(value)
        options[option.key] = value

    exclude_loggers = const.split_multiple(
        config.get("sentry_exclude_loggers", const.DEFAULT_EXCLUDE_LOGGERS)
    )

    if not options.get("release"):
        options["release"] = config.get(
            "sentry_release", get_odoo_commit(config.get("sentry_odoo_dir"))
        )

    # Change name `ignore_exceptions` (with raven)
    # to `ignore_errors' (sentry_sdk)
    options["ignore_errors"] = options["ignore_exceptions"]
    del options["ignore_exceptions"]

    options["before_send"] = before_send
    options["before_send_transaction"] = before_send_transaction

    # Remove logging_level, the integration is rebuilt below from the
    # sentry_logging_level / sentry_breadcrumb_logging_level /
    # sentry_event_logging_level keys
    del options["logging_level"]

    # Sentry Logs: forward stdlib log records as structured logs
    logs_level = None
    if config_bool(config, "sentry_logs_enabled"):
        if const.SUPPORTS_SENTRY_LOGS:
            options["enable_logs"] = True
            logs_level = config.get("sentry_logs_level", const.DEFAULT_LOGS_LEVEL)
        else:
            _logger.warning(
                "sentry_logs_enabled is set but the installed sentry-sdk "
                "does not support Sentry Logs (needs >= 2.63)"
            )

    options["integrations"] = [
        const.get_logging_integration(config, logs_level=logs_level),
        ThreadingIntegration(propagate_scope=True),
    ]

    # APM Configuration: Setup custom traces sampler if APM is enabled
    apm_enabled = config_bool(config, "sentry_apm_enabled")
    if apm_enabled:
        _logger.info("Sentry APM is enabled, configuring traces sampler...")
        sampler = Sampler(config)
        options["traces_sampler"] = sampler.traces_sampler
        # Remove traces_sample_rate if traces_sampler is set
        # (traces_sampler takes precedence)
        options.pop("traces_sample_rate", None)

    client = sentry_sdk.init(**options)

    sentry_sdk.set_tag(
        "include_context", config_bool(config, "sentry_include_context", True)
    )

    if exclude_loggers:
        for item in exclude_loggers:
            ignore_logger(item)

    # Wrap the WSGI entry point at the Application class level. This
    # works in every server mode (threaded, prefork, gevent) and also
    # when this module is loaded via server_wide_modules, i.e. before
    # odoo.service.server.server exists. Replacing odoo.http.root or
    # server.app instead would miss modes where the singleton was
    # already handed to the server, and replacing the root object would
    # break attribute access like root.nodb_routing_map.
    _wrap_wsgi_application()

    # Apply APM patches if enabled
    if apm_enabled:
        from .patch import apply_apm_patches

        apply_apm_patches(config)

    # Optional host/database gauges (CPU, RAM, disk, network, db
    # connections/size) emitted by a background thread
    if config_bool(config, "sentry_system_metrics_enabled"):
        from .sysmetrics import start_system_metrics

        start_system_metrics(config)

    with sentry_sdk.new_scope() as scope:
        scope.set_extra("debug", False)
        scope.set_extra("apm_enabled", apm_enabled)
        sentry_sdk.capture_message("Starting Odoo Server", "info")

    return client


def post_load():
    initialize_sentry(odoo_config)
