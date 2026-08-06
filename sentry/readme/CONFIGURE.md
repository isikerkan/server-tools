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

## Cron Monitoring (Sentry Crons)

| Option | Description | Default |
|--------|-------------|---------|
| `sentry_cron_monitors_enabled` | Send a Sentry Crons check-in for every ir.cron run; monitors and their schedules are upserted automatically from the cron's interval, so missed, late and failed runs alert without any setup in Sentry | `false` |
| `sentry_cron_monitors_include` | Comma-separated list of cron names to monitor; empty means all crons | all |
| `sentry_queue_job_monitor_enabled` | OCA queue_job monitoring: a Crons heartbeat for the jobrunner thread (missed check-in = dead runner) plus per-database backlog gauges `queue_job.pending/enqueued/started/failed` | `false` |

Queue jobs themselves have no schedule, so they cannot be individual
Sentry Crons monitors; the jobrunner heartbeat plus backlog gauges cover the
operational questions instead (is the runner alive, is the queue
draining). The heartbeat uses one monitor (`odoo-queue-jobrunner`).

Check-ins report the real job outcome: a run that Odoo marks as failed
closes its check-in with the error status, even though the exception
never leaves Odoo's cron machinery. Missed and overlong runs are
detected by the monitor schedule and its max_runtime.

Runtime overhead is negligible (two asynchronous envelopes per run),
but every monitored cron counts against the Sentry Crons monitor quota
of your plan - on instances with many frequent crons, use the include
list to monitor only the business-critical ones. Monitor slugs are
prefixed with the database name.

## Test runs

When Odoo runs with `--test-enable`, Sentry is not initialized: test
suites raise expected exceptions constantly and would flood the
project with noise. Set `sentry_enable_in_tests = true` to opt back in
(e.g. to test the integration itself).

## Integration mode: Python vs JavaScript app

| Option | Description | Default |
|--------|-------------|---------|
| `sentry_mode` | `python`: backend SDK only, the browser loader is never injected regardless of system parameters. `javascript`: additionally inject the Sentry Loader Script (browser errors, Session Replay) when `sentry.browser_loader_url` is set. Unknown values fall back to `python`. | `python` |

The mode is a server option so multi-database deployments behave
consistently. In `python` mode the Sentry project should keep the
`python` platform; in `javascript` mode set it to `javascript` so the
Replay UI is available.

## Session Replay (browser)

Session Replay only applies in `sentry_mode = javascript`.
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
