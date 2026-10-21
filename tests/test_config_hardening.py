import tempfile
import unittest
from pathlib import Path

from web_monitor import ConfigurationError, MonitorConfig, MonitorSuiteConfig, MonitorError, SnapshotStore


class ConfigHardeningTests(unittest.TestCase):
    def test_target_url_rejects_embedded_credentials(self):
        with self.assertRaises(ConfigurationError):
            MonitorConfig.from_mapping({
                "target_url": "https://user:secret@example.com/page",
                "css_selector": "body",
            })

    def test_numeric_fields_reject_boolean_and_non_finite_values(self):
        cases = (
            ("check_interval_seconds", True),
            ("request_timeout_seconds", "nan"),
            ("backoff_seconds", "inf"),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value), self.assertRaises(ConfigurationError):
                MonitorConfig.from_mapping({
                    "target_url": "https://example.com/",
                    "css_selector": "body",
                    field: value,
                })

        with self.assertRaises(ConfigurationError):
            MonitorConfig.from_mapping({
                "target_url": "https://example.com/",
                "css_selector": "body",
                "notification": {"timeout_seconds": float("inf")},
            })

    def test_malformed_target_and_webhook_urls_fail_without_echo(self):
        from notifications import WebhookNotifier

        for url in ("https://[broken", "https://example.test:invalid", "https://:80",
                    "https://user:synthetic-password@example.test"):
            for build in (lambda: MonitorConfig.from_mapping({"target_url": url,
                                                              "css_selector": "body"}),
                          lambda: WebhookNotifier(url, "test", 1)):
                with self.subTest(url=url), self.assertRaises(ConfigurationError) as error:
                    build()
                self.assertNotIn(url, str(error.exception))
                self.assertNotIn("synthetic-password", str(error.exception))

    def test_state_and_health_paths_cannot_collide(self):
        with tempfile.TemporaryDirectory() as directory:
            state = str(Path(directory) / "state.json")
            alias = str(Path(directory) / "nested" / ".." / "state.json")
            target = {"name": "one", "target_url": "http://127.0.0.1/",
                      "css_selector": "body", "state_file": state}
            for health in (state, alias, state + ".tmp"):
                for payload in (dict(target, health_file=health),
                                {"targets": [target], "health_file": health}):
                    with self.subTest(health=health), self.assertRaises(ConfigurationError):
                        MonitorSuiteConfig.from_mapping(payload)
            for other_state in (alias, state + ".tmp"):
                with self.subTest(other_state=other_state), self.assertRaises(ConfigurationError):
                    MonitorSuiteConfig.from_mapping({"targets": [target,
                        dict(target, name="two", state_file=other_state)]})

    def test_output_cannot_overwrite_source_configuration(self):
        import json

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            for field in ("health_file", "state_file"):
                payload = {"target_url": "http://127.0.0.1/", "css_selector": "main",
                           field: str(path)}
                original = json.dumps(payload)
                path.write_text(original)
                with self.subTest(field=field), self.assertRaises(ConfigurationError):
                    MonitorSuiteConfig.from_file(str(path))
                self.assertEqual(path.read_text(), original)

    def test_invalid_utf8_configuration_and_state_are_controlled(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            path.write_bytes(b"\xff")
            with self.assertRaises(ConfigurationError):
                MonitorSuiteConfig.from_file(str(path))
            with self.assertRaises(MonitorError):
                SnapshotStore(str(path)).load_digest()


if __name__ == "__main__":
    unittest.main()
