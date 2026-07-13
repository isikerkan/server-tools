# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import threading
from unittest.mock import patch

from odoo.tests import TransactionCase

from .. import sysmetrics


class TestSystemMetrics(TransactionCase):
    def setUp(self):
        super().setUp()
        # never leave a collector thread reference behind
        self.addCleanup(setattr, sysmetrics, "_collector_thread", None)
        sysmetrics._collector_thread = None

    def _started_interval(self, config):
        """Start the collector with a stubbed loop, return the interval
        it was invoked with."""
        loop = patch.object(sysmetrics, "_collector_loop").start()
        self.addCleanup(patch.stopall)
        sysmetrics.start_system_metrics(config)
        thread = sysmetrics._collector_thread
        self.assertIsNotNone(thread)
        self.assertTrue(thread.daemon)
        thread.join(5)
        self.assertTrue(loop.called)
        return loop.call_args[0][0]

    def test_starts_thread_with_default_interval(self):
        interval = self._started_interval({})
        self.assertEqual(interval, sysmetrics.DEFAULT_INTERVAL)

    def test_interval_clamped_to_minimum(self):
        interval = self._started_interval({"sentry_system_metrics_interval": "3"})
        self.assertEqual(interval, sysmetrics.MIN_INTERVAL)

    def test_invalid_interval_falls_back_to_default(self):
        interval = self._started_interval(
            {"sentry_system_metrics_interval": "not-a-number"}
        )
        self.assertEqual(interval, sysmetrics.DEFAULT_INTERVAL)

    def test_idempotent_while_running(self):
        release = threading.Event()
        with patch.object(
            sysmetrics,
            "_collector_loop",
            side_effect=lambda interval, stop: release.wait(10),
        ):
            sysmetrics.start_system_metrics({})
            first = sysmetrics._collector_thread
            sysmetrics.start_system_metrics({})
            self.assertIs(sysmetrics._collector_thread, first)
            release.set()
            first.join(5)

    def test_noop_without_metrics_support(self):
        with patch.object(sysmetrics, "sentry_metrics", None):
            sysmetrics.start_system_metrics({})
        self.assertIsNone(sysmetrics._collector_thread)
