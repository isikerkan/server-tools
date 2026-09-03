# Copyright 2026 Erkan Isik
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from unittest.mock import patch

import sentry_sdk

from odoo.tests import TransactionCase

from .. import patch as sentry_patch


class TestCronMonitors(TransactionCase):
    def setUp(self):
        super().setUp()
        self.job = {
            "cron_name": "Mail: Email Queue Manager",
            "interval_number": 5,
            "interval_type": "minutes",
        }
        self.addCleanup(
            setattr,
            sentry_patch,
            "_CRON_MONITORS_ENABLED",
            sentry_patch._CRON_MONITORS_ENABLED,
        )
        self.addCleanup(
            setattr,
            sentry_patch,
            "_CRON_MONITORS_INCLUDE",
            sentry_patch._CRON_MONITORS_INCLUDE,
        )

    def test_slug(self):
        slug = sentry_patch._cron_monitor_slug("odoo_18", "Mail: Email Queue!")
        self.assertEqual(slug, "odoo_18-mail-email-queue")

    def test_slug_truncated_to_50(self):
        slug = sentry_patch._cron_monitor_slug(
            "a-very-long-database-name", "A Cron With An Extremely Long Name Indeed"
        )
        self.assertEqual(len(slug), 50)
        self.assertTrue(slug.startswith("a-very-long-database-name-a-cron"))

    def test_disabled_no_checkin(self):
        # the module-level flag mirrors the server config, so a dev box
        # with sentry_cron_monitors_enabled = true must not fail here:
        # assert the behaviour of the disabled state, not the default
        sentry_patch._CRON_MONITORS_ENABLED = False
        with patch("sentry_sdk.crons.capture_checkin") as checkin:
            result = sentry_patch._cron_checkin_start(self.job, "db1")
        self.assertEqual(result, (None, None))
        checkin.assert_not_called()

    def test_include_list_filters(self):
        sentry_patch._CRON_MONITORS_ENABLED = True
        sentry_patch._CRON_MONITORS_INCLUDE = ("Some Other Cron",)
        with patch("sentry_sdk.crons.capture_checkin") as checkin:
            result = sentry_patch._cron_checkin_start(self.job, "db1")
        self.assertEqual(result, (None, None))
        checkin.assert_not_called()

    def test_checkin_with_schedule_from_interval(self):
        sentry_patch._CRON_MONITORS_ENABLED = True
        sentry_patch._CRON_MONITORS_INCLUDE = ()
        with patch("sentry_sdk.crons.capture_checkin", return_value="cid") as checkin:
            slug, check_in_id = sentry_patch._cron_checkin_start(self.job, "db1")
        self.assertEqual(check_in_id, "cid")
        self.assertTrue(slug.startswith("db1-mail"))
        monitor_config = checkin.call_args.kwargs["monitor_config"]
        self.assertEqual(
            monitor_config["schedule"],
            {"type": "interval", "value": 5, "unit": "minute"},
        )

    def test_finish_reports_status(self):
        with patch("sentry_sdk.crons.capture_checkin") as checkin:
            sentry_patch._cron_checkin_finish("slug", "cid", False, 1.5)
        self.assertEqual(checkin.call_args.kwargs["status"], "error")
        self.assertEqual(checkin.call_args.kwargs["duration"], 1.5)

    def test_finish_noop_without_checkin(self):
        with patch("sentry_sdk.crons.capture_checkin") as checkin:
            sentry_patch._cron_checkin_finish(None, None, True, 0.1)
        checkin.assert_not_called()

    def test_transaction_does_not_leak_into_thread_scope(self):
        # the cron thread is long-lived: a job's transaction name must
        # not stay on the scope once the job is done, otherwise later
        # errors on the thread get attributed to that job
        before = sentry_sdk.get_current_scope()._transaction
        with sentry_patch._cron_transaction("Some Cron", {"id": 7}, "db1") as tx:
            self.assertEqual(tx.name, "Cron: Some_Cron")
            self.assertEqual(tx.op, "cron")
            self.assertEqual(
                sentry_sdk.get_current_scope()._transaction, "Cron: Some_Cron"
            )
        self.assertEqual(sentry_sdk.get_current_scope()._transaction, before)
        self.assertIsNone(sentry_sdk.get_current_scope().span)
