## 18.0.2.4.0 (2026-09-03)

- Session Replay: opt-in identification of the logged-in Odoo user
  (`sentry.replay_identify_user`) and upload of the buffered replay when
  a backend error reaches the browser over RPC
  (`sentry.replay_flush_on_rpc_error`).
- Cron transactions run in a forked scope so the transaction name no
  longer leaks into later errors on the same cron thread.

## 18.0.2.3.0 (2026-08-07)

- `sentry_mode` (`python` / `javascript`): the browser loader is only
  injected in `javascript` mode; `python` (default) keeps the module a
  pure backend integration.
- Sentry Crons check-ins for `ir.cron` runs (`sentry_cron_monitors_enabled`,
  `sentry_cron_monitors_include`); monitors and schedules are upserted from
  the cron interval and check-ins report the real job outcome, including
  runs failed by timeout.
- OCA queue_job monitoring (`sentry_queue_job_monitor_enabled`): jobrunner
  heartbeat monitor and per-database backlog gauges; queue_job executions
  are tagged with model, method and uuid.
- Sentry is not initialized while Odoo runs with `--test-enable` unless
  `sentry_enable_in_tests` is set.
- APM patches are idempotent when `post_load` runs more than once.

## 18.0.2.2.0 (2026-07-13)

- Host and database gauges from a background collector
  (`sentry_system_metrics_enabled`, `sentry_system_metrics_interval`).
- Sentry Loader Script injection for browser errors and Session Replay
  (`sentry.browser_loader_url`), with configurable replay sample rates
  (`sentry.replay_session_sample_rate`, `sentry.replay_error_sample_rate`)
  passed to the browser as data attributes.

## 18.0.2.1.0 (2026-07-09)

- Compatibility with Odoo 18 request handling and sentry-sdk 2.x: WSGI
  middleware applied at the `odoo.http.Application` level, `_serve_db` /
  `_serve_nodb` instrumentation, `TransactionSource` enum, span `name`
  keyword, `propagate_scope`; dependency range widened to
  `sentry_sdk>=2.0.0,<3.0.0`.
- Profiling (`sentry_profiles_sample_rate`) and `before_send_transaction`
  scrubbing of cookies and passwords on transactions.
- Sentry Metrics: `odoo.request` / `odoo.cron` counters and duration
  distributions (`sentry_metrics_enabled`); zero-cost fast path for SQL
  spans on unsampled transactions; default exclusion of asset, static,
  websocket and longpolling paths (`sentry_traces_exclude_paths`).
- Sentry Logs forwarding (`sentry_logs_enabled`, `sentry_logs_level`).
- Separate breadcrumb and event log levels
  (`sentry_breadcrumb_logging_level`, `sentry_event_logging_level`) and
  opt-in ORM spans (`sentry_trace_orm`).
- Boolean config keys are parsed as booleans, so `sentry_enabled = false`
  is honoured; cron jobs with a NULL name no longer break the cron patch.

## 18.0.2.0.0 (2025-12-18)

- APM (Application Performance Monitoring): per-operation traces sampler
  (`sentry_apm_enabled`, `sentry_traces_sample_rate_http` / `_cron` /
  `_job`), HTTP transaction names, user context and tags, SQL query
  spans, cron transactions and queue_job tags.
