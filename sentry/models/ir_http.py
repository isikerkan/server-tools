# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models
from odoo.tools import config

from ..const import SENTRY_MODE_JAVASCRIPT, get_sentry_mode


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
