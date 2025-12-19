The following additional configuration options can be added to your Odoo
configuration file:

[TABLE]

Other [client
arguments](https://docs.sentry.io/platforms/python/configuration/) can
be configured by prepending the argument name with *sentry\_* in your
Odoo config file. Currently supported additional client arguments are:
`with_locals, max_breadcrumbs, release, environment, server_name, shutdown_timeout, in_app_include, in_app_exclude, default_integrations, dist, sample_rate, send_default_pii, http_proxy, https_proxy, request_bodies, debug, attach_stacktrace, ca_certs, propagate_traces, traces_sample_rate, auto_enabling_integrations`.

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
| `sentry_breadcrumb_logging_level` | Minimum log level for breadcrumbs | `info` |
| `sentry_event_logging_level` | Minimum log level for events | `error` |

### APM Features

When APM is enabled, the following instrumentation is applied:

- **HTTP Request Tracking**: Transaction names, user context, and tags (db, model, method) are set for each request
- **SQL Query Tracing**: Database queries are captured as spans for performance analysis
- **Cron Job Transactions**: Each cron execution creates a separate transaction
- **Queue Job Tags**: If `queue_job` module is installed, job model and method are tagged

Note: Long-polling requests (`/longpolling/*`) are automatically excluded from tracing to reduce noise.

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
