# Copyright 2026 Erkan Isik
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.tests import TransactionCase

from .. import hooks


class TestTestModeGuard(TransactionCase):
    """Sentry must not initialize during test runs unless opted in."""

    def _config(self, **overrides):
        config = {
            "sentry_enabled": "true",
            "sentry_dsn": "http://public:secret@example.com/1",
            "test_enable": True,
        }
        config.update(overrides)
        return config

    def test_disabled_during_tests(self):
        with patch.object(hooks.sentry_sdk, "init") as init:
            result = hooks.initialize_sentry(self._config())
        self.assertIsNone(result)
        init.assert_not_called()

    def test_opt_in_during_tests(self):
        with patch.object(hooks.sentry_sdk, "init") as init:
            hooks.initialize_sentry(self._config(sentry_enable_in_tests="true"))
        init.assert_called_once()
