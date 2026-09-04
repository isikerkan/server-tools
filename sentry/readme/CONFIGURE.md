The following additional configuration options can be added to your Odoo
configuration file (`[options]` section). Every key is read once at
server start, so a change needs an Odoo restart. Boolean keys accept
`true`/`false` (also `1`/`0`, `yes`/`no`, `on`/`off`); log level keys
accept the Odoo level names `debug`, `info`, `warn`, `error`, `critical`.

## Core

| Option | Description | Default |
|--------|-------------|---------|
| `sentry_enabled` | Enable the integration. Nothing is initialized while it is `false`. | `false` |
| `sentry_dsn` | The DSN of the Sentry project (Settings → Projects → Client Keys). Required. | unset |
| `sentry_environment` | Environment name shown in Sentry (for example `production`, `staging`). | SDK default (`production`, or `$SENTRY_ENVIRONMENT`) |
| `sentry_release` | Release identifier attached to every event. Takes precedence over `sentry_odoo_dir`. | unset |
| `sentry_odoo_dir` | Path of the Odoo git checkout; its current commit SHA is used as release when `sentry_release` is empty. | unset |
| `sentry_include_context` | Attach Odoo request context (user, database, request data, tags) to error events. | `true` |
| `sentry_ignore_exceptions` | Comma-separated list of exception classes (`module.Class`) never reported. | `odoo.exceptions.AccessDenied, AccessError, DeferredException, MissingError, RedirectWarning, UserError, ValidationError, Warning, except_orm` |
| `sentry_exclude_loggers` | Comma-separated list of loggers whose records are ignored entirely (events, breadcrumbs and Sentry Logs). | `werkzeug` |
| `sentry_transport` | Deprecated and ignored (`HttpTransport` is always used); setting it only emits a `DeprecationWarning`. | unset |

Other [client
arguments](https://docs.sentry.io/platforms/python/configuration/) can
be configured by prepending the argument name with *sentry\_* in your
Odoo config file. The value is handed to `sentry_sdk.init()` unchanged
(numbers are converted where noted), so the SDK defaults apply:

| Option | Description | Default |
|--------|-------------|---------|
| `sentry_include_local_variables` | Include local variables in stack traces. | `true` (SDK) |
| `sentry_max_breadcrumbs` | Maximum number of breadcrumbs kept per event (integer). | `100` (SDK) |
| `sentry_server_name` | Server name tag. | hostname (SDK) |
| `sentry_shutdown_timeout` | Seconds to wait for pending events on shutdown. | `2` (SDK) |
| `sentry_in_app_include` | Comma-separated module prefixes treated as application code. | empty (SDK) |
| `sentry_in_app_exclude` | Comma-separated module prefixes treated as library code. | empty (SDK) |
| `sentry_default_integrations` | Load the SDK default integrations. | `true` (SDK) |
| `sentry_auto_enabling_integrations` | Auto-enable integrations for detected libraries. | `true` (SDK) |
| `sentry_dist` | Distribution identifier. | unset (SDK) |
| `sentry_sample_rate` | Fraction of *error* events sent (float 0.0 to 1.0). | `1.0` (SDK) |
| `sentry_send_default_pii` | Send personal data (the Odoo login as user email on APM transactions and events). | `false` (SDK) |
| `sentry_http_proxy`, `sentry_https_proxy` | Proxy URLs for the transport. | unset (SDK) |
| `sentry_ca_certs` | Path to a CA bundle for the transport. | unset (SDK) |
| `sentry_max_request_body_size` | How much of the request body to attach (`never`, `small`, `medium`, `always`). | `medium` (SDK) |
| `sentry_max_value_length` | Truncate string values longer than this (integer). | SDK default (`1024`) |
| `sentry_attach_stacktrace` | Attach a stack trace to messages captured without exception. | `false` (SDK) |
| `sentry_propagate_traces` | Add distributed tracing headers to outgoing HTTP requests. | `true` (SDK) |
| `sentry_traces_sample_rate` | Global transaction sample rate (float). Ignored when `sentry_apm_enabled = true`, where the per-operation sampler below replaces it. | unset (SDK: tracing off) |
| `sentry_profiles_sample_rate` | Attach performance profiles to sampled transactions (float 0.0 to 1.0). | unset (SDK: profiling off) |
| `sentry_integrations` | Read for completeness but overwritten by the module's own integration list (logging + threading); do not use. | – |

## Logging

| Option | Description | Default |
|--------|-------------|---------|
| `sentry_logging_level` | Legacy key: minimum level of log records reported as *error events*. Used when `sentry_event_logging_level` is not set. | `warn` |
| `sentry_event_logging_level` | Minimum level of log records reported as error events; overrides `sentry_logging_level`. | falls back to `sentry_logging_level` |
| `sentry_breadcrumb_logging_level` | Minimum level of log records kept as breadcrumbs on events. | `info` |
| `sentry_logs_enabled` | Forward stdlib log records to the Sentry Logs product (requires sentry-sdk >= 2.63; a warning is logged otherwise). | `false` |
| `sentry_logs_level` | Minimum level forwarded to Sentry Logs. | `info` |

Loggers listed in `sentry_exclude_loggers` are also excluded from Logs.

## APM (Application Performance Monitoring)

To enable Sentry APM for performance monitoring, set `sentry_apm_enabled = true`.
This enables transaction tracing for HTTP requests, cron jobs, queue jobs, and SQL queries.
Several other features (request/cron metrics, Crons check-ins, queue_job tags)
are installed by the same instrumentation and therefore also need `sentry_apm_enabled`.

| Option | Description | Default |
|--------|-------------|---------|
| `sentry_apm_enabled` | Enable Sentry APM: per-operation traces sampler plus request, SQL, cron and queue_job instrumentation. | `false` |
| `sentry_traces_sample_rate_http` | Sampling rate for HTTP requests (0.0 to 1.0). Also used for unknown operation types. | `0.1` |
| `sentry_traces_sample_rate_cron` | Sampling rate for cron job transactions (0.0 to 1.0). | `0.1` |
| `sentry_traces_sample_rate_job` | Sampling rate for queue_job requests (`/queue_job/...`) (0.0 to 1.0). | `0.1` |
| `sentry_traces_exclude_paths` | Comma-separated path prefixes never traced (replaces the default list). | `/longpolling, /websocket, /web/assets, /web/static, /web/image, /web/content, /favicon.ico, /robots.txt` |
| `sentry_trace_orm` | Add `odoo.orm` spans (`model.method`) for `create`, `write`, `unlink`, `read` and `_search` on top of the SQL spans. Adds a wrapper to the hottest ORM methods, so opt-in. | `false` |
| `sentry_profiles_sample_rate` | Attach performance profiles to sampled transactions (0.0 to 1.0). | unset |

When APM is enabled, the following instrumentation is applied:

- **HTTP Request Tracking**: transaction names, user context, and tags (`odoo.db`, `odoo.path`, `odoo.model`, `odoo.method`) are set for each request
- **SQL Query Tracing**: database queries are captured as `db.sql.query` spans for performance analysis
- **ORM Tracing** (opt-in): `odoo.orm` spans per model method on top of the SQL spans
- **Cron Job Transactions**: each cron execution creates a separate `Cron: <name>` transaction tagged `odoo.cron.name`, `odoo.cron.id`, `odoo.db`
- **Queue Job Tags**: if the `queue_job` module is installed, `odoo.job.model`, `odoo.job.method` and `odoo.job.uuid` are tagged

Distributed traces respect the upstream sampling decision (`parent_sampled`).
The user email is only sent when `sentry_send_default_pii = true`.
Cookies and passwords are scrubbed from transactions as they are from error events.

## Metrics and system metrics (Sentry Metrics product, sentry-sdk >= 2.63)

| Option | Description | Default |
|--------|-------------|---------|
| `sentry_metrics_enabled` | Emit `odoo.request` / `odoo.cron` counters and `odoo.request.duration` / `odoo.cron.duration` distributions (attributes: scrubbed `path`, `db`, `cron`). Only effective with `sentry_apm_enabled = true`. | `true` when the SDK supports metrics, else `false` |
| `sentry_system_metrics_enabled` | Emit host and database gauges from a background thread: `system.cpu.percent`, `system.memory.percent`, `system.memory.used`, `system.disk.percent`, `system.disk.read`, `system.disk.write`, `system.network.sent`, `system.network.received`, `db.connections.active`, `db.connections.idle`, `db.size` (per database). Does not need APM. | `false` |
| `sentry_system_metrics_interval` | Collection interval in seconds. Values below 10 are raised to 10; an invalid value falls back to 60. | `60` |

Host gauges require the `psutil` Python package (when it is missing only
the database gauges are emitted); database gauges only need a database
cursor and are tagged per database (`db` attribute). One collector thread
runs per Odoo process.

## Cron monitoring (Sentry Crons)

Requires `sentry_apm_enabled = true` (the check-ins are sent from the cron
instrumentation).

| Option | Description | Default |
|--------|-------------|---------|
| `sentry_cron_monitors_enabled` | Send a Sentry Crons check-in for every `ir.cron` run; monitors and their schedules are upserted automatically from the cron's interval, so missed, late and failed runs alert without any setup in Sentry. | `false` |
| `sentry_cron_monitors_include` | Comma-separated list of cron names (the `ir.cron` display name) to monitor; empty means all crons. | all |

Monitor slugs are `<database>-<cron name>` lower-cased and reduced to
`[a-z0-9_-]` (max 50 characters), so the same cron on different databases
gets distinct monitors. The upserted schedule is the cron interval in UTC with
a 5 minute check-in margin and a 30 minute maximum runtime.

Check-ins report the real job outcome: a run that Odoo marks as failed
(including a run failed by timeout) closes its check-in with the error
status, even though the exception never leaves Odoo's cron machinery.
Missed and overlong runs are detected by the monitor schedule and its
max runtime.

Runtime overhead is negligible (two asynchronous envelopes per run),
but every monitored cron counts against the Sentry Crons monitor quota
of your plan - on instances with many frequent crons, use the include
list to monitor only the business-critical ones.

## queue_job (OCA)

| Option | Description | Default |
|--------|-------------|---------|
| `sentry_queue_job_monitor_enabled` | OCA queue_job monitoring from the background collector thread: a Sentry Crons heartbeat for the jobrunner thread (monitor `odoo-queue-jobrunner`, a missed check-in means the runner died) plus per-database backlog gauges `queue_job.pending`, `queue_job.enqueued`, `queue_job.started`, `queue_job.failed`. Does not need APM. | `false` |

Queue jobs themselves have no schedule, so they cannot be individual
Sentry Crons monitors; the jobrunner heartbeat plus backlog gauges cover the
operational questions instead (is the runner alive, is the queue
draining). The heartbeat is only sent from the process that runs the
jobrunner thread, at the `sentry_system_metrics_interval` cadence. The job
tags and the `sentry_traces_sample_rate_job` sampling rate described under
APM apply to the job executions themselves.

## Integration mode and browser loader / Session Replay

| Option | Description | Default |
|--------|-------------|---------|
| `sentry_mode` | `python`: backend SDK only, the browser loader is never injected regardless of system parameters. `javascript`: additionally inject the Sentry Loader Script (browser errors, Session Replay) into every web page when `sentry.browser_loader_url` is set. Unknown values fall back to `python`. | `python` |

The mode is a server option so multi-database deployments behave
consistently. In `python` mode the Sentry project should keep the
`python` platform; in `javascript` mode set it to `javascript` so the
Replay UI is available.

Session Replay records the user's browser session and therefore can
only be captured by the Sentry **JavaScript** SDK - not by this Python
addon. In `javascript` mode this module injects the Sentry Loader Script into
every web page (backend, portal and website, via `web.layout`): create the
Loader in Sentry (Settings → Projects → Loader Script, enable Session Replay
and choose the sample rates there) and store its URL in the system parameter
`sentry.browser_loader_url` (Settings → Technical → System Parameters).
Remove the parameter to disable the injection. The loader also enables
browser-side error and performance capture, so backend traces and frontend
replays are linked.

The remaining settings are `ir.config_parameter` system parameters (per
database), all optional:

| System parameter | Description | Default |
|------------------|-------------|---------|
| `sentry.browser_loader_url` | URL of the Sentry Loader Script (`https://js.sentry-cdn.com/<key>.min.js`). Empty disables the injection. | unset |
| `sentry.replay_session_sample_rate` | Fraction of sessions recorded (0.0 to 1.0). Parsed in the browser; invalid values fall back to the default. | `0.1` |
| `sentry.replay_error_sample_rate` | Fraction of sessions with an error recorded (0.0 to 1.0). Parsed in the browser; invalid values fall back to the default. | `1.0` |
| `sentry.replay_identify_user` | `true`: attach the logged-in Odoo user (id, login, name - no email) to browser events and replays, so a replay can be searched by user. Public/portal visitors are never identified. Personal data, hence off by default. | `false` |
| `sentry.replay_flush_on_rpc_error` | `true`: when a server-side error comes back over RPC (Odoo's error dialog), upload the replay buffered so far and add an `odoo.rpc` breadcrumb. Otherwise replays sampled "on error" are only uploaded for errors thrown in the browser itself, and backend failures never get a replay. The backend event and the replay are linked through the propagated trace; no duplicate browser error is created. | `false` |
| `sentry.feedback_widget` | `false` hides the Loader Script's "Report a Bug" user-feedback button, `true` forces it on. Unset: whatever the Loader Script is configured to do in Sentry (Settings → Projects → Loader Script). | unset |

Replay is a recording of the *user's* session: leave
`sentry.replay_flush_on_rpc_error` off if you only care about frontend
crashes, turn it on when you want to see what a user did before a
backend error dialog appeared.

## Test runs

| Option | Description | Default |
|--------|-------------|---------|
| `sentry_enable_in_tests` | Initialize Sentry even when Odoo runs with `--test-enable` (`test_enable = true`). | `false` |

When Odoo runs with `--test-enable`, Sentry is not initialized: test
suites raise expected exceptions constantly and would flood the
project with noise. Set `sentry_enable_in_tests = true` to opt back in
(e.g. to test the integration itself).

## Example Odoo configuration

Below is an example of Odoo configuration file with *Odoo Sentry*
options (optional keys are commented out with their default value):

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
    ; sentry_send_default_pii = false
    ; sentry_breadcrumb_logging_level = info
    ; sentry_event_logging_level = warn

    ; Sentry Logs (optional, sentry-sdk >= 2.63)
    ; sentry_logs_enabled = false
    ; sentry_logs_level = info

    ; APM (optional)
    sentry_apm_enabled = true
    sentry_traces_sample_rate_http = 0.2
    sentry_traces_sample_rate_cron = 0.1
    sentry_traces_sample_rate_job = 0.05
    ; sentry_traces_exclude_paths = /longpolling,/websocket,/web/assets,/web/static,/web/image,/web/content,/favicon.ico,/robots.txt
    ; sentry_trace_orm = false
    ; sentry_profiles_sample_rate = 0.1

    ; Metrics and system metrics (optional, sentry-sdk >= 2.63)
    ; sentry_metrics_enabled = true
    ; sentry_system_metrics_enabled = false
    ; sentry_system_metrics_interval = 60

    ; Sentry Crons for ir.cron (optional, needs sentry_apm_enabled)
    ; sentry_cron_monitors_enabled = false
    ; sentry_cron_monitors_include = Mail: Email Queue Manager,Base: Auto-vacuum internal data

    ; OCA queue_job monitoring (optional)
    ; sentry_queue_job_monitor_enabled = false

    ; Browser SDK / Session Replay (optional; the loader URL and replay
    ; parameters are system parameters, see above)
    ; sentry_mode = python

    ; Test runs (optional)
    ; sentry_enable_in_tests = false
