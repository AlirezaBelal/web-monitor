"""Regression cases reproduced during Mission 06's targeted review."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import requests
from notifications import (
    MAX_ACK_BYTES,
    NotificationDeliveryError,
    TelegramNotifier,
    WebhookNotifier,
)
from web_monitor import (
    ConfigurationError,
    MonitorConfig,
    MonitorSuiteConfig,
    MonitorError,
    SnapshotStore,
    WebMonitor,
)
from main import build_monitors, main


class HardeningTests(unittest.TestCase):
    def test_notification_responses_close_on_success_rejection_and_body_failure(self):
        for backend in ("webhook", "telegram"):
            for outcome in (
                "success",
                "http",
                "redirect",
                "body",
                "large",
                "invalid",
                "negative",
            ):
                response = Mock(status_code=302 if outcome == "redirect" else 200)
                response.iter_content.return_value = iter([b'{"ok":true}'])
                if outcome == "http":
                    response.raise_for_status.side_effect = requests.HTTPError(
                        "synthetic-secret"
                    )
                if outcome == "body":
                    response.iter_content.side_effect = requests.ConnectionError(
                        "synthetic-secret"
                    )
                if outcome == "large":
                    response.iter_content.return_value = iter(
                        [b"x" * (MAX_ACK_BYTES + 1)]
                    )
                if outcome == "invalid":
                    response.iter_content.return_value = iter([b"[]"])
                if outcome == "negative":
                    response.iter_content.return_value = iter([b'{"ok":false}'])
                session = Mock(post=Mock(return_value=response))
                notifier = (
                    WebhookNotifier("http://127.0.0.1/hook", "one", 1, session)
                    if backend == "webhook"
                    else TelegramNotifier("synthetic-secret", "one", "one", 1, session)
                )
                fails = outcome in ("http", "redirect") or (
                    backend == "telegram" and outcome != "success"
                )
                with self.subTest(backend=backend, outcome=outcome):
                    if fails:
                        with self.assertRaises(NotificationDeliveryError) as error:
                            notifier("title", "message")
                        self.assertNotIn("synthetic-secret", str(error.exception))
                    else:
                        notifier("title", "message")
                    response.close.assert_called_once()
                    self.assertTrue(session.post.call_args.kwargs["stream"])
                    self.assertFalse(session.post.call_args.kwargs["allow_redirects"])
                    if backend == "webhook":
                        response.iter_content.assert_not_called()

    def test_numeric_overflow_and_oversized_integer_strings_are_controlled(self):
        for field, value in [
            ("request_timeout_seconds", 10**1000),
            ("max_attempts", "9" * 5000),
        ]:
            with self.subTest(field=field), self.assertRaises(ConfigurationError):
                MonitorConfig.from_mapping(
                    {
                        "target_url": "http://127.0.0.1/",
                        "css_selector": "main",
                        field: value,
                    }
                )

    def test_deep_json_is_controlled_in_config_and_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            for content in ("[" * 2000 + "0" + "]" * 2000, '{"n":' + "9" * 5000 + "}"):
                path.write_text(content)
                with self.assertRaises(ConfigurationError):
                    MonitorSuiteConfig.from_file(str(path))
                with self.assertRaises(MonitorError):
                    SnapshotStore(str(path)).load_digest()

    def test_output_file_cannot_also_be_another_output_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            state = str(Path(directory) / "state.json")
            for health in (
                str(Path(state) / "health.json"),
                str(Path(state + ".tmp") / "health.json"),
            ):
                with self.subTest(health=health), self.assertRaises(ConfigurationError):
                    MonitorSuiteConfig.from_mapping(
                        {
                            "target_url": "http://127.0.0.1/",
                            "css_selector": "main",
                            "state_file": state,
                            "health_file": health,
                        }
                    )

    def test_owned_sessions_close_but_injected_sessions_remain_caller_owned(self):
        config = MonitorConfig.from_mapping(
            {"target_url": "http://127.0.0.1/", "css_selector": "main"}
        )
        for make in (
            lambda session: WebMonitor(config, session=session),
            lambda session: WebhookNotifier("http://127.0.0.1/hook", "one", 1, session),
            lambda session: TelegramNotifier("fictional", "one", "one", 1, session),
        ):
            with patch("requests.Session") as factory:
                owned = make(None)
                owned.close()
                factory.return_value.close.assert_called_once()
            external = Mock()
            make(external).close()
            external.close.assert_not_called()

    def test_partial_initialization_closes_already_built_monitors(self):
        suite = MonitorSuiteConfig.from_mapping(
            {
                "targets": [
                    {
                        "name": n,
                        "target_url": "http://127.0.0.1/",
                        "css_selector": "main",
                    }
                    for n in ("one", "two")
                ]
            }
        )
        monitor = Mock()
        with patch(
            "main.WebMonitor", side_effect=[monitor, ConfigurationError("failure")]
        ):
            with self.assertRaises(ConfigurationError):
                build_monitors(suite, False)
        monitor.close.assert_called_once()

    def test_cli_closes_resources_on_once_and_keyboard_shutdown(self):
        suite = MonitorSuiteConfig.from_mapping(
            {"target_url": "http://127.0.0.1/", "css_selector": "main"}
        )
        for once in (True, False):
            monitor = Mock(config=suite.targets[0])
            monitor.check_once.return_value = Mock(
                status="baseline", matched_elements=1
            )
            with (
                patch("sys.argv", ["main.py"] + (["--once"] if once else [])),
                patch("main.MonitorSuiteConfig.from_file", return_value=suite),
                patch("main.build_monitors", return_value=[monitor]),
                patch("main.time.sleep", side_effect=KeyboardInterrupt),
            ):
                self.assertEqual(main(), 0)
            monitor.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
