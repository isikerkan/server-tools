# Copyright 2026 Erkan Isik
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models
from odoo.tools import config

from ..const import SENTRY_MODE_JAVASCRIPT, get_sentry_mode

REPLAY_IDENTIFY_USER_PARAM = "sentry.replay_identify_user"
REPLAY_FLUSH_ON_RPC_ERROR_PARAM = "sentry.replay_flush_on_rpc_error"
TRUE_VALUES = ("1", "true", "yes", "on")


def _param_is_true(value):
    return str(value or "").strip().lower() in TRUE_VALUES


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def sentry_frontend_enabled(self):
        """Whether the Sentry browser SDK loader may be injected into
        web pages. Called from the web.layout QWeb template (which is
        why this method cannot be underscore-private: the QWeb sandbox
        forbids underscore attribute access).

        The mode comes from the server config, not the database, so a
        multi-db server behaves consistently:

        - sentry_mode = javascript: inject the loader when the
          sentry.browser_loader_url system parameter is set
        - sentry_mode = python (default): never inject; Sentry runs as
          a pure backend/Python integration
        """
        return get_sentry_mode(config) == SENTRY_MODE_JAVASCRIPT

    def sentry_replay_options(self):
        """Opt-in browser-side options for the loader snippet, both off
        by default and toggled with system parameters:

        - sentry.replay_identify_user: attach the logged-in Odoo user
          (id, login, name - no email) to browser events and replays so
          a replay can be found by user. Off by default because it is
          personal data.
        - sentry.replay_flush_on_rpc_error: when a server-side error
          comes back over RPC (the Odoo error dialog), upload the replay
          buffered so far. Without it, replays recorded in buffer mode
          are only uploaded for errors thrown in the browser itself,
          so backend failures never get a replay.

        Called from QWeb, hence public.
        """
        params = self.env["ir.config_parameter"].sudo()
        identify = _param_is_true(params.get_param(REPLAY_IDENTIFY_USER_PARAM))
        flush = _param_is_true(params.get_param(REPLAY_FLUSH_ON_RPC_ERROR_PARAM))
        user = None
        if identify and self.env.uid and not self.env.user._is_public():
            current = self.env.user
            user = {"id": current.id, "login": current.login, "name": current.name}
        return {"identify_user": identify, "flush_on_rpc_error": flush, "user": user}
