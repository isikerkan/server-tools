# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.tests import TransactionCase
from odoo.tools import config

from ..const import (
    SENTRY_MODE_JAVASCRIPT,
    SENTRY_MODE_PYTHON,
    get_sentry_mode,
)


class TestSentryMode(TransactionCase):
    def test_default_is_python(self):
        self.assertEqual(get_sentry_mode({}), SENTRY_MODE_PYTHON)

    def test_javascript_mode(self):
        self.assertEqual(
            get_sentry_mode({"sentry_mode": "JavaScript"}), SENTRY_MODE_JAVASCRIPT
        )

    def test_unknown_value_falls_back(self):
        self.assertEqual(
            get_sentry_mode({"sentry_mode": "nodejs"}), SENTRY_MODE_PYTHON
        )

    def test_frontend_enabled_follows_mode(self):
        ir_http = self.env["ir.http"]
        with patch.dict(config.options, {"sentry_mode": "javascript"}):
            self.assertTrue(ir_http.sentry_frontend_enabled())
        with patch.dict(config.options, {"sentry_mode": "python"}):
            self.assertFalse(ir_http.sentry_frontend_enabled())
        with patch.dict(config.options):
            config.options.pop("sentry_mode", None)
            self.assertFalse(ir_http.sentry_frontend_enabled())
