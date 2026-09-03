# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase

from ..models.ir_http import REPLAY_FLUSH_ON_RPC_ERROR_PARAM, REPLAY_IDENTIFY_USER_PARAM


class TestReplayOptions(TransactionCase):
    def setUp(self):
        super().setUp()
        self.params = self.env["ir.config_parameter"].sudo()
        self.params.set_param(REPLAY_IDENTIFY_USER_PARAM, False)
        self.params.set_param(REPLAY_FLUSH_ON_RPC_ERROR_PARAM, False)

    def test_defaults_are_off(self):
        options = self.env["ir.http"].sentry_replay_options()
        self.assertEqual(
            options, {"identify_user": False, "flush_on_rpc_error": False, "user": None}
        )

    def test_identify_user(self):
        self.params.set_param(REPLAY_IDENTIFY_USER_PARAM, "True")
        options = (
            self.env["ir.http"]
            .with_user(self.env.ref("base.user_demo"))
            .sentry_replay_options()
        )
        self.assertTrue(options["identify_user"])
        self.assertEqual(options["user"]["login"], "demo")
        self.assertNotIn("email", options["user"])

    def test_public_user_is_not_identified(self):
        self.params.set_param(REPLAY_IDENTIFY_USER_PARAM, "1")
        public = self.env.ref("base.public_user")
        options = self.env["ir.http"].with_user(public).sentry_replay_options()
        self.assertIsNone(options["user"])

    def test_flush_flag(self):
        self.params.set_param(REPLAY_FLUSH_ON_RPC_ERROR_PARAM, "yes")
        self.assertTrue(
            self.env["ir.http"].sentry_replay_options()["flush_on_rpc_error"]
        )
        self.params.set_param(REPLAY_FLUSH_ON_RPC_ERROR_PARAM, "nope")
        self.assertFalse(
            self.env["ir.http"].sentry_replay_options()["flush_on_rpc_error"]
        )
