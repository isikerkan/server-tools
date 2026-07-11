# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase

from ..hooks import Sampler


def make_config(values=None):
    config = {
        "sentry_traces_sample_rate_http": "0.5",
        "sentry_traces_sample_rate_cron": "0.25",
        "sentry_traces_sample_rate_job": "0.75",
    }
    config.update(values or {})
    return config


def http_context(path, op="http.server", parent_sampled=None):
    context = {
        "transaction_context": {"op": op},
        "wsgi_environ": {"PATH_INFO": path},
    }
    if parent_sampled is not None:
        context["parent_sampled"] = parent_sampled
    return context


class TestSampler(TransactionCase):
    def setUp(self):
        super().setUp()
        self.sampler = Sampler(make_config())

    def test_http_rate(self):
        rate = self.sampler.traces_sampler(http_context("/web/dataset/call_kw"))
        self.assertEqual(rate, 0.5)

    def test_cron_rate(self):
        context = {"transaction_context": {"op": "cron"}}
        self.assertEqual(self.sampler.traces_sampler(context), 0.25)

    def test_queue_job_rate(self):
        rate = self.sampler.traces_sampler(http_context("/queue_job/runjob"))
        self.assertEqual(rate, 0.75)

    def test_excluded_paths_default(self):
        for path in (
            "/longpolling/poll",
            "/websocket",
            "/web/assets/some.css",
            "/web/static/src/js/x.js",
            "/web/image/17",
            "/web/content/42",
            "/favicon.ico",
            "/robots.txt",
        ):
            self.assertEqual(
                self.sampler.traces_sampler(http_context(path)), 0.0, path
            )

    def test_exclude_paths_configurable(self):
        sampler = Sampler(make_config({"sentry_traces_exclude_paths": "/custom"}))
        self.assertEqual(sampler.traces_sampler(http_context("/custom/x")), 0.0)
        # default exclusions replaced by the custom list
        self.assertEqual(
            sampler.traces_sampler(http_context("/web/assets/y.css")), 0.5
        )

    def test_parent_sampled_respected(self):
        sampler = self.sampler
        self.assertEqual(
            sampler.traces_sampler(http_context("/any", parent_sampled=True)), 1.0
        )
        self.assertEqual(
            sampler.traces_sampler(http_context("/any", parent_sampled=False)), 0.0
        )
        # parent decision wins even over exclusions
        self.assertEqual(
            sampler.traces_sampler(
                http_context("/web/assets/z.css", parent_sampled=True)
            ),
            1.0,
        )

    def test_unknown_op_uses_http_rate(self):
        context = {"transaction_context": {"op": "something.else"}}
        self.assertEqual(self.sampler.traces_sampler(context), 0.5)

    def test_defaults_when_unconfigured(self):
        sampler = Sampler({})
        self.assertEqual(
            sampler.traces_sampler(http_context("/web/dataset/call_kw")), 0.1
        )
