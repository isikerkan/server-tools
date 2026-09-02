- **No database separation** -- This module functions by intercepting
  all Odoo logging records in a running Odoo process. This means that
  once installed in one database, it will intercept and report errors
  for all Odoo databases, which are used on that Odoo server.
- **Frontend integration** -- Browser-side error capture and Session
  Replay are available through the Sentry Loader Script injection
  (`sentry_mode = javascript`). Remaining ideas: integrate the
  [Sentry user feedback
  widget](https://docs.sentry.io/product/user-feedback/) into the Odoo
  client error dialog so users can describe what they were doing, and
  upload source maps for the minified Odoo asset bundles so browser
  stack traces resolve to readable frames.
