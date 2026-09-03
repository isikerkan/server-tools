# Copyright 2026 Erkan Isik
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
        self.addCleanup(setattr, sysmetrics, "_SYSTEM_ENABLED", False)
        self.addCleanup(setattr, sysmetrics, "_QUEUE_ENABLED", False)
        sysmetrics._collector_thread = None

    def _started_interval(self, config):
        """Start the collector with a stubbed loop, return the interval
        it was invoked with."""
        loop = patch.object(sysmetrics, "_collector_loop").start()
        self.addCleanup(patch.stopall)
        sysmetrics.start_system_metrics(
            {"sentry_system_metrics_enabled": "true", **config}
        )
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
        enabled = {"sentry_system_metrics_enabled": "true"}
        with patch.object(
            sysmetrics,
            "_collector_loop",
            side_effect=lambda interval, stop: release.wait(10),
        ):
            sysmetrics.start_system_metrics(enabled)
            first = sysmetrics._collector_thread
            sysmetrics.start_system_metrics(enabled)
            self.assertIs(sysmetrics._collector_thread, first)
            release.set()
            first.join(5)

    def test_noop_without_metrics_support(self):
        with patch.object(sysmetrics, "sentry_metrics", None):
            sysmetrics.start_system_metrics({"sentry_system_metrics_enabled": "true"})
        self.assertIsNone(sysmetrics._collector_thread)

    def test_noop_when_nothing_enabled(self):
        sysmetrics.start_system_metrics({})
        self.assertIsNone(sysmetrics._collector_thread)

    def test_queue_monitor_alone_starts_collector(self):
        interval_config = {"sentry_queue_job_monitor_enabled": "true"}
        loop = patch.object(sysmetrics, "_collector_loop").start()
        self.addCleanup(patch.stopall)
        sysmetrics.start_system_metrics(interval_config)
        thread = sysmetrics._collector_thread
        self.assertIsNotNone(thread)
        thread.join(5)
        self.assertTrue(loop.called)
        self.assertTrue(sysmetrics._QUEUE_ENABLED)
        self.assertFalse(sysmetrics._SYSTEM_ENABLED)
