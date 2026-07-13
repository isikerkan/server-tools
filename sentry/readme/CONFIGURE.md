The following additional configuration options can be added to your Odoo
configuration file:

[TABLE]

Other [client
arguments](https://docs.sentry.io/platforms/python/configuration/) can
be configured by prepending the argument name with *sentry\_* in your
Odoo config file. Currently supported additional client arguments are:
`include_local_variables, max_breadcrumbs, release, environment, server_name, shutdown_timeout, in_app_include, in_app_exclude, default_integrations, dist, sample_rate, send_default_pii, http_proxy, https_proxy, max_request_body_size, attach_stacktrace, ca_certs, propagate_traces, traces_sample_rate, profiles_sample_rate, auto_enabling_integrations, max_value_length`.

## APM (Application Performance Monitoring)

To enable Sentry APM for performance monitoring, set `sentry_apm_enabled = true`.
This enables transaction tracing for HTTP requests, cron jobs, queue jobs, and SQL queries.

### APM Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `sentry_apm_enabled` | Enable Sentry APM (Application Performance Monitoring) | `false` |
| `sentry_traces_sample_rate_http` | Sampling rate for HTTP requests (0.0 to 1.0) | `0.1` |
| `sentry_traces_sample_rate_cron` | Sampling rate for cron jobs (0.0 to 1.0) | `0.1` |
| `sentry_traces_sample_rate_job` | Sampling rate for queue jobs (0.0 to 1.0) | `0.1` |
| `sentry_traces_exclude_paths` | Comma-separated path prefixes never traced | assets, statics, websocket, longpolling, favicon, robots |
| `sentry_trace_orm` | Add ORM-level spans (`model.method`) for create/write/unlink/read/search | `false` |
| `sentry_profiles_sample_rate` | Attach performance profiles to sampled transactions (0.0 to 1.0) | unset |
| `sentry_breadcrumb_logging_level` | Minimum log level for breadcrumbs | `info` |
| `sentry_event_logging_level` | Minimum log level for error events (falls back to `sentry_logging_level`) | `warn` |

### APM Features

When APM is enabled, the following instrumentation is applied:

- **HTTP Request Tracking**: Transaction names, user context, and tags (db, model, method) are set for each request
- **SQL Query Tracing**: Database queries are captured as spans for performance analysis
- **ORM Tracing** (opt-in): `odoo.orm` spans per model method on top of the SQL spans
- **Cron Job Transactions**: Each cron execution creates a separate transaction
- **Queue Job Tags**: If `queue_job` module is installed, job model and method are tagged

Distributed traces respect the upstream sampling decision (`parent_sampled`).
The user email is only sent when `sentry_send_default_pii = true`.

## Metrics (Sentry Metrics product, sentry-sdk >= 2.63)

| Option | Description | Default |
|--------|-------------|---------|
| `sentry_metrics_enabled` | Emit `odoo.request` / `odoo.cron` counters and duration distributions | `true` when supported |
| `sentry_system_metrics_enabled` | Emit host and database gauges from a background thread: `system.cpu.percent`, `system.memory.*`, `system.disk.*`, `system.network.*`, `db.connections.*`, `db.size` | `false` |
| `sentry_system_metrics_interval` | Collection interval in seconds (minimum 10) | `60` |

Host gauges require `psutil`; database gauges only need a database
cursor and are tagged per database.

## Logs (Sentry Logs product, sentry-sdk >= 2.63)

| Option | Description | Default |
|--------|-------------|---------|
| `sentry_logs_enabled` | Forward stdlib log records to Sentry Logs | `false` |
| `sentry_logs_level` | Minimum level forwarded | `info` |

Loggers listed in `sentry_exclude_loggers` are also excluded from Logs.

## Session Replay (browser)

Session Replay records the user's browser session and therefore can
only be captured by the Sentry **JavaScript** SDK - not by this Python
addon. This module can inject the Sentry Loader Script into every web
page: create the Loader in Sentry (Settings → Projects → Loader Script,
enable Session Replay and choose the sample rates there) and store its
URL in the system parameter `sentry.browser_loader_url` (Settings →
Technical → System Parameters). Remove the parameter to disable the
injection. The loader also enables browser-side error and performance
capture, so backend traces and frontend replays are linked.

The Loader ships with a fixed 10% session sample rate. Two optional
system parameters override the rates client-side (parsed in the
browser; invalid values fall back to the defaults):

| System parameter | Description | Default |
|------------------|-------------|---------|
| `sentry.replay_session_sample_rate` | Fraction of sessions recorded (0.0 to 1.0) | `0.1` |
| `sentry.replay_error_sample_rate` | Fraction of error sessions recorded (0.0 to 1.0) | `1.0` |

## Example Odoo configuration

Below is an example of Odoo configuration file with *Odoo Sentry*
options:

    [options]
    sentry_dsn = https://<public_key>:<secret_key>@sentry.example.com/<project id>
    sentry_enabled = true
    sentry_logging_level = warn
    sentry_exclude_loggers = werkzeug
    sentry_ignore_exceptions = odoo.exceptions.AccessDenied,
        odoo.exceptions.AccessError,odoo.exceptions.MissingError,
        odoo.exceptions.RedirectWarning,odoo.exceptions.UserError,
        odoo.exceptions.ValidationError,odoo.exceptions.Warning,
        odoo.exceptions.except_orm
    sentry_include_context = true
    sentry_environment = production
    sentry_release = 1.3.2
    sentry_odoo_dir = /home/odoo/odoo/

    ; APM Configuration (optional)
    sentry_apm_enabled = true
    sentry_traces_sample_rate_http = 0.2
    sentry_traces_sample_rate_cron = 0.1
    sentry_traces_sample_rate_job = 0.05
    sentry_trace_orm = true
    sentry_profiles_sample_rate = 0.1

    ; Metrics and Logs (optional)
    sentry_metrics_enabled = true
    sentry_system_metrics_enabled = true
    sentry_system_metrics_interval = 60
    sentry_logs_enabled = true
    sentry_logs_level = warn
