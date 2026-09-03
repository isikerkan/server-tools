Once configured and installed, the module will report any logging event
at and above the configured Sentry logging level, no additional actions
are necessary. On every server start an informational event *Starting
Odoo Server* is sent, which is the quickest way to confirm that the DSN
and the network path work.

[![Try me on Runboat](https://odoo-community.org/website/image/ir.attachment/5784_f2813bd/datas)](https://runboat.odoo-community.org/webui/builds.html?repo=OCA/server-tools)

## Verifying the integration end to end

The list below says what each kind of failure looks like in Sentry, so
a fresh setup can be checked feature by feature. The companion addon
[`sentry_error_lab`](https://github.com/isikerkan/sentry-error-lab)
(not part of OCA) adds a *Settings → Technical → Sentry Error Lab* menu
with one button per case below, so each of them can be triggered on
demand instead of waiting for a real failure.

- **Python exception** (an unhandled exception in a controller or model
  method, for example a `ZeroDivisionError`): an *Issue* on the Python
  project with the full stack trace and local variables. With
  `sentry_include_context` the event carries the Odoo user and request
  data; with `sentry_apm_enabled` it is also tagged `odoo.db`,
  `odoo.path`, `odoo.model` and `odoo.method`. Exceptions listed in
  `sentry_ignore_exceptions` (`UserError`, `ValidationError`, ...) are
  not reported - they are user feedback, not bugs.
- **Logged error** (`_logger.error("...")` without an exception): an
  *Issue* whose title is the log message, grouped by logger and message.
  Records at the `sentry_breadcrumb_logging_level` appear as
  breadcrumbs on the next event instead. With `sentry_logs_enabled` the
  same records also show up on the *Logs* page, searchable by logger,
  level and message.
- **Cron failure** (an `ir.cron` method that raises): an *Issue* for the
  exception, plus - with `sentry_cron_monitors_enabled` - a check-in
  with status *error* on the Crons monitor `<database>-<cron name>`.
  Missed runs (the cron did not start on schedule) and runs longer than
  30 minutes are flagged on the monitor without any event being
  raised. Sampled runs additionally appear in *Performance* as the
  transaction `Cron: <name>`.
- **queue_job failure** (a job that raises): an *Issue* tagged
  `odoo.job.model`, `odoo.job.method` and `odoo.job.uuid` (requires
  `sentry_apm_enabled`); sampled executions appear as `/queue_job/runjob`
  transactions. With `sentry_queue_job_monitor_enabled` the gauge
  `queue_job.failed` for that database increases on the next collector
  tick, and the monitor `odoo-queue-jobrunner` keeps receiving
  check-ins while the jobrunner thread is alive - a *missed* check-in
  there means the runner died.
- **Slow request or trace** (`sentry_apm_enabled`): an entry in
  *Performance* / *Traces* named after the request path (numeric ids
  intact in the transaction name, replaced by `:id` in the metrics
  attributes), with `db.sql.query` spans for every query, `odoo.orm`
  spans when `sentry_trace_orm` is on, and a profile when
  `sentry_profiles_sample_rate` is set. Only the configured fraction of
  requests is sampled (`sentry_traces_sample_rate_http`), so run a slow
  action a few times or raise the rate temporarily. Request counts and
  durations are on the *Metrics* page as `odoo.request` and
  `odoo.request.duration`.
- **System metrics** (`sentry_system_metrics_enabled`): the gauges
  `system.*` and `db.*` appear on the *Metrics* page after the first two
  collection intervals (disk and network are deltas and need a previous
  sample).
- **Browser error** (`sentry_mode = javascript` and
  `sentry.browser_loader_url` set): an *Issue* on the JavaScript side
  (platform `javascript`) for uncaught exceptions, unhandled promise
  rejections and errors thrown in OWL components, with the minified
  Odoo asset frames. Verify the injection by looking for the
  `js.sentry-cdn.com` script in the page source.
- **Session Replay**: the *Replays* tab lists recorded sessions
  according to `sentry.replay_session_sample_rate`, and a replay is
  attached to browser errors according to
  `sentry.replay_error_sample_rate`. With
  `sentry.replay_flush_on_rpc_error` a replay is also uploaded when the
  Odoo error dialog shows a *backend* error, and is linked to the
  Python issue through the propagated trace; with
  `sentry.replay_identify_user` replays can be searched by Odoo user
  id or login.

## Known cosmetic noise

- **Shutdown tracebacks**: when the server is stopped, the cron worker
  and the connection pool can log `psycopg2.InterfaceError: connection
  already closed` (or similar) tracebacks while the process is going
  down. They are reported as regular error events although nothing is
  wrong. Ignore the issue in Sentry or add `psycopg2.InterfaceError` to
  `sentry_ignore_exceptions` if they are frequent (for example on
  development machines that are restarted often).
- **Starting Odoo Server**: one informational event per process start,
  by design. Filter on `level:info` to hide it.
- **Duplicate host gauges in multi-process deployments**: the system
  metrics collector runs in every Odoo process that executed the
  module's `post_load` hook; if several such processes run on one
  host, the `system.*` gauges are emitted once per process.
