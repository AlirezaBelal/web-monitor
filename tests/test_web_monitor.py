import json
import tempfile
import unittest
from pathlib import Path

import requests

from web_monitor import (
    ConfigurationError,
    MonitorConfig,
    MonitorError,
    MonitorSuiteConfig,
    SnapshotStore,
    WebMonitor,
)


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200, headers=None):
        self.text = text
        self.status_code = status_code
        self.headers = headers or {}
        self.encoding = "utf-8"
        self.closed = False

    def iter_content(self, chunk_size=65536):
        payload = self.text.encode(self.encoding)
        for start in range(0, len(payload), chunk_size):
            yield payload[start : start + chunk_size]

    def close(self):
        self.closed = True

    def raise_for_status(self):
        if self.status_code >= 400:
            response = requests.Response()
            response.status_code = self.status_code
            raise requests.HTTPError(response=response)


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class MonitorConfigTests(unittest.TestCase):
    def test_accepts_valid_configuration(self):
        config = MonitorConfig.from_mapping(
            {
                "target_url": "https://example.com/page",
                "css_selector": ".item",
                "check_interval_seconds": 60,
                "request_timeout_seconds": 5,
                "max_attempts": 2,
                "backoff_seconds": 0.25,
            }
        )

        self.assertEqual(config.target_url, "https://example.com/page")
        self.assertEqual(config.css_selector, ".item")
        self.assertEqual(config.comparison_mode, "text")
        self.assertEqual(config.max_attempts, 2)
        self.assertEqual(config.backoff_seconds, 0.25)
        self.assertEqual(len(config.monitor_key), 64)

    def test_rejects_non_http_url_and_invalid_numbers(self):
        with self.assertRaises(ConfigurationError):
            MonitorConfig.from_mapping(
                {"target_url": "file:///tmp/page.html", "css_selector": "body"}
            )

        with self.assertRaises(ConfigurationError):
            MonitorConfig.from_mapping(
                {
                    "target_url": "https://example.com",
                    "css_selector": "body",
                    "check_interval_seconds": 0,
                }
            )

        with self.assertRaises(ConfigurationError):
            MonitorConfig.from_mapping(
                {
                    "target_url": "https://example.com",
                    "css_selector": "body",
                    "max_attempts": 11,
                }
            )


class MonitorSuiteConfigTests(unittest.TestCase):
    def test_legacy_single_target_config_remains_supported(self):
        suite = MonitorSuiteConfig.from_mapping(
            {
                "target_url": "https://example.com/",
                "css_selector": "body",
                "check_interval_seconds": 45,
            }
        )

        self.assertEqual(len(suite.targets), 1)
        self.assertEqual(suite.targets[0].name, "default")
        self.assertEqual(suite.check_interval_seconds, 45.0)

    def test_multi_target_config_inherits_shared_defaults_and_isolates_state(self):
        suite = MonitorSuiteConfig.from_mapping(
            {
                "check_interval_seconds": 30,
                "request_timeout_seconds": 4,
                "max_attempts": 3,
                "backoff_seconds": 0.5,
                "user_agent": "WebMonitor-Suite/1.0",
                "targets": [
                    {
                        "name": "alpha",
                        "target_url": "https://example.com/a",
                        "css_selector": "#a",
                    },
                    {
                        "name": "beta",
                        "target_url": "https://example.com/b",
                        "css_selector": "#b",
                        "max_attempts": 2,
                    },
                ],
            }
        )

        self.assertEqual([target.name for target in suite.targets], ["alpha", "beta"])
        self.assertEqual(suite.targets[0].state_file, ".webmonitor/alpha.json")
        self.assertEqual(suite.targets[1].state_file, ".webmonitor/beta.json")
        self.assertEqual(suite.targets[0].max_attempts, 3)
        self.assertEqual(suite.targets[1].max_attempts, 2)
        self.assertEqual(suite.targets[0].request_timeout_seconds, 4.0)

    def test_multi_target_rejects_duplicate_names_or_state_files(self):
        with self.assertRaises(ConfigurationError):
            MonitorSuiteConfig.from_mapping(
                {
                    "targets": [
                        {
                            "name": "same",
                            "target_url": "https://example.com/a",
                            "css_selector": "body",
                        },
                        {
                            "name": "same",
                            "target_url": "https://example.com/b",
                            "css_selector": "body",
                        },
                    ]
                }
            )

        with self.assertRaises(ConfigurationError):
            MonitorSuiteConfig.from_mapping(
                {
                    "targets": [
                        {
                            "name": "alpha",
                            "target_url": "https://example.com/a",
                            "css_selector": "body",
                            "state_file": ".webmonitor/shared.json",
                        },
                        {
                            "name": "beta",
                            "target_url": "https://example.com/b",
                            "css_selector": "body",
                            "state_file": ".webmonitor/shared.json",
                        },
                    ]
                }
            )

    def test_multi_target_interval_is_process_level(self):
        with self.assertRaises(ConfigurationError):
            MonitorSuiteConfig.from_mapping(
                {
                    "targets": [
                        {
                            "name": "alpha",
                            "target_url": "https://example.com/a",
                            "css_selector": "body",
                            "check_interval_seconds": 10,
                        }
                    ]
                }
            )


class WebMonitorTests(unittest.TestCase):
    def _config(self, state_file: str, **overrides):
        payload = {
            "target_url": "https://example.com/monitor",
            "css_selector": ".item",
            "comparison_mode": "text",
            "check_interval_seconds": 60,
            "request_timeout_seconds": 7,
            "state_file": state_file,
            "user_agent": "WebMonitor-Test/1.0",
            "max_attempts": 1,
            "backoff_seconds": 0,
            "notification": {"title": "Changed", "message": "Content changed"},
        }
        payload.update(overrides)
        return MonitorConfig.from_mapping(payload)

    def test_first_check_creates_baseline_without_notification_or_raw_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = str(Path(temp_dir) / "state.json")
            notifications = []
            session = FakeSession([FakeResponse('<div class="item">private value</div>')])
            monitor = WebMonitor(
                self._config(state_file),
                notifier=lambda title, message: notifications.append((title, message)),
                session=session,
            )

            result = monitor.check_once()

            self.assertEqual(result.status, "baseline")
            self.assertEqual(result.matched_elements, 1)
            self.assertEqual(notifications, [])
            state_text = Path(state_file).read_text(encoding="utf-8")
            state_payload = json.loads(state_text)
            self.assertNotIn("private value", state_text)
            self.assertEqual(state_payload["version"], 1)
            self.assertEqual(len(state_payload["sha256"]), 64)
            self.assertEqual(len(state_payload["monitor_key"]), 64)

    def test_unchanged_check_does_not_notify(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = str(Path(temp_dir) / "state.json")
            notifications = []
            session = FakeSession(
                [
                    FakeResponse('<div class="item">same</div>'),
                    FakeResponse('<div class="item">same</div>'),
                ]
            )
            monitor = WebMonitor(
                self._config(state_file),
                notifier=lambda title, message: notifications.append((title, message)),
                session=session,
            )

            self.assertEqual(monitor.check_once().status, "baseline")
            self.assertEqual(monitor.check_once().status, "unchanged")
            self.assertEqual(notifications, [])

    def test_changed_check_updates_state_and_notifies_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = str(Path(temp_dir) / "state.json")
            notifications = []
            session = FakeSession(
                [
                    FakeResponse('<div class="item">before</div>'),
                    FakeResponse('<div class="item">after</div>'),
                ]
            )
            monitor = WebMonitor(
                self._config(state_file),
                notifier=lambda title, message: notifications.append((title, message)),
                session=session,
            )

            monitor.check_once()
            result = monitor.check_once()

            self.assertEqual(result.status, "changed")
            self.assertEqual(notifications, [("Changed", "Content changed")])

    def test_retries_transient_http_failures_with_exponential_backoff(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            sleeps = []
            session = FakeSession(
                [
                    FakeResponse("busy", status_code=503),
                    FakeResponse("busy", status_code=503),
                    FakeResponse('<div class="item">ok</div>'),
                ]
            )
            monitor = WebMonitor(
                self._config(
                    str(Path(temp_dir) / "state.json"),
                    max_attempts=3,
                    backoff_seconds=0.5,
                ),
                session=session,
                sleeper=sleeps.append,
            )

            responses = list(session.responses)
            result = monitor.check_once()

            self.assertTrue(all(response.closed for response in responses))
            self.assertEqual(result.status, "baseline")
            self.assertEqual(len(session.calls), 3)
            self.assertEqual(sleeps, [0.5, 1.0])

    def test_monitored_url_redirect_is_not_followed_or_saved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "state.json"
            response = FakeResponse("", status_code=302)
            session = FakeSession([response])
            monitor = WebMonitor(self._config(str(path)), session=session)
            with self.assertRaisesRegex(MonitorError, "redirect") as context:
                monitor.check_once()
            self.assertNotIn(monitor.config.target_url, str(context.exception))
            self.assertTrue(response.closed)
            self.assertFalse(path.exists())
            self.assertEqual(len(session.calls), 1)
            self.assertEqual(session.calls[0][1]["allow_redirects"], False)

    def test_non_retryable_http_status_fails_immediately(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            sleeps = []
            session = FakeSession(
                [
                    FakeResponse("missing", status_code=404),
                    FakeResponse('<div class="item">should not run</div>'),
                ]
            )
            monitor = WebMonitor(
                self._config(
                    str(Path(temp_dir) / "state.json"),
                    max_attempts=3,
                    backoff_seconds=0.5,
                ),
                session=session,
                sleeper=sleeps.append,
            )

            failed_response = session.responses[0]
            with self.assertRaises(MonitorError) as context:
                monitor.check_once()

            self.assertTrue(failed_response.closed)
            self.assertEqual(len(session.calls), 1)
            self.assertEqual(sleeps, [])
            self.assertIn("404", str(context.exception))
            self.assertIn("1 attempt", str(context.exception))

    def test_config_identity_change_creates_new_baseline(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = str(Path(temp_dir) / "state.json")
            notifications = []
            first_monitor = WebMonitor(
                self._config(state_file, css_selector=".item"),
                notifier=lambda title, message: notifications.append((title, message)),
                session=FakeSession(
                    [FakeResponse('<div class="item">first</div><div class="other">second</div>')]
                ),
            )
            second_monitor = WebMonitor(
                self._config(state_file, css_selector=".other"),
                notifier=lambda title, message: notifications.append((title, message)),
                session=FakeSession(
                    [FakeResponse('<div class="item">first</div><div class="other">second</div>')]
                ),
            )

            self.assertEqual(first_monitor.check_once().status, "baseline")
            self.assertEqual(second_monitor.check_once().status, "baseline")
            self.assertEqual(notifications, [])

    def test_legacy_state_rebaselines_without_notification(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            state_path.write_text(
                json.dumps({"sha256": "a" * 64}),
                encoding="utf-8",
            )
            notifications = []
            monitor = WebMonitor(
                self._config(str(state_path)),
                notifier=lambda title, message: notifications.append((title, message)),
                session=FakeSession([FakeResponse('<div class="item">current</div>')]),
            )

            self.assertEqual(monitor.check_once().status, "baseline")
            self.assertEqual(notifications, [])
            self.assertIn("monitor_key", json.loads(state_path.read_text(encoding="utf-8")))

    def test_html_mode_detects_attribute_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_file = str(Path(temp_dir) / "state.json")
            session = FakeSession(
                [
                    FakeResponse('<a class="item" href="/before">Label</a>'),
                    FakeResponse('<a class="item" href="/after">Label</a>'),
                ]
            )
            monitor = WebMonitor(
                self._config(state_file, comparison_mode="html"),
                session=session,
            )

            monitor.check_once()
            self.assertEqual(monitor.check_once().status, "changed")

    def test_selector_must_match_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            monitor = WebMonitor(
                self._config(str(Path(temp_dir) / "state.json")),
                session=FakeSession([FakeResponse("<main>content</main>")]),
            )

            with self.assertRaises(MonitorError) as context:
                monitor.check_once()

            self.assertIn("selector", str(context.exception).lower())

    def test_invalid_selector_is_reported_as_monitor_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            monitor = WebMonitor(
                self._config(
                    str(Path(temp_dir) / "state.json"),
                    css_selector="div[",
                ),
                session=FakeSession([FakeResponse("<div>content</div>")]),
            )

            with self.assertRaises(MonitorError) as context:
                monitor.check_once()

            self.assertEqual(str(context.exception), "Configured CSS selector is invalid")

    def test_oversized_response_is_rejected_before_parsing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = FakeSession(
                [FakeResponse('<div class="item">too large</div>', headers={"Content-Length": "9999"})]
            )
            monitor = WebMonitor(
                self._config(
                    str(Path(temp_dir) / "state.json"),
                    max_response_bytes=1024,
                ),
                session=session,
            )

            response = session.responses[0]
            with self.assertRaises(MonitorError) as context:
                monitor.check_once()

            self.assertTrue(response.closed)
            self.assertIn("size limit", str(context.exception))

    def test_streamed_response_is_bounded_even_without_content_length(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = FakeSession([FakeResponse('<div class="item">' + ('x' * 2000) + '</div>')])
            monitor = WebMonitor(
                self._config(
                    str(Path(temp_dir) / "state.json"),
                    max_response_bytes=1024,
                ),
                session=session,
            )

            response = session.responses[0]
            with self.assertRaises(MonitorError) as context:
                monitor.check_once()

            self.assertTrue(response.closed)
            self.assertIn("size limit", str(context.exception))

    def test_body_failures_close_response_and_preserve_baseline(self):
        from unittest.mock import Mock

        for failure in (requests.ConnectionError("private response"),
                        requests.exceptions.ChunkedEncodingError("private response")):
            response = FakeResponse("")
            def chunks():
                yield b""
                yield b"<main>partial"
                raise failure
            response.iter_content = lambda **kwargs: chunks()
            store = Mock()
            monitor = WebMonitor(self._config("unused"),
                                 session=FakeSession([response]), store=store)
            with self.subTest(failure=type(failure)), self.assertRaises(MonitorError) as error:
                monitor.check_once()
            self.assertTrue(response.closed)
            self.assertNotIn("private response", str(error.exception))
            store.save_digest.assert_not_called()

    def test_invalid_charset_isolated_from_next_target(self):
        import contextlib
        import io
        from unittest.mock import Mock
        from main import run_checks

        for encoding in ("unknown-test-charset", "base64_codec"):
            response = FakeResponse("")
            response.encoding = encoding
            response.iter_content = lambda **kwargs: iter([b"<div class='item'>private</div>"])
            broken = WebMonitor(self._config("unused"),
                                session=FakeSession([response]), store=Mock())
            healthy = WebMonitor(self._config("unused", name="healthy"),
                                 session=FakeSession([FakeResponse('<div class="item">ok</div>')]),
                                 store=Mock(load_digest=Mock(return_value=None)))
            stderr = io.StringIO()
            with self.subTest(encoding=encoding), contextlib.redirect_stderr(stderr), \
                    contextlib.redirect_stdout(io.StringIO()):
                failures, records = run_checks([broken, healthy], True)
            self.assertEqual(failures, 1)
            self.assertEqual([record.status for record in records], ["error", "baseline"])
            self.assertTrue(response.closed)
            self.assertNotIn("private", stderr.getvalue())
            self.assertNotIn(broken.config.target_url, stderr.getvalue())

    def test_request_timeout_and_user_agent_are_applied(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = FakeSession([FakeResponse('<div class="item">ok</div>')])
            monitor = WebMonitor(
                self._config(str(Path(temp_dir) / "state.json")),
                session=session,
            )

            monitor.check_once()

            _url, kwargs = session.calls[0]
            self.assertEqual(kwargs["timeout"], 7.0)
            self.assertEqual(kwargs["headers"]["User-Agent"], "WebMonitor-Test/1.0")

    def test_http_error_message_does_not_echo_target_url(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = self._config(str(Path(temp_dir) / "state.json"))
            session = FakeSession([FakeResponse("error", status_code=503)])
            monitor = WebMonitor(config, session=session)

            with self.assertRaises(MonitorError) as context:
                monitor.check_once()

            message = str(context.exception)
            self.assertIn("503", message)
            self.assertNotIn(config.target_url, message)

    def test_invalid_state_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            state_path.write_text("not-json", encoding="utf-8")

            with self.assertRaises(MonitorError):
                SnapshotStore(str(state_path)).load_digest()


if __name__ == "__main__":
    unittest.main()
