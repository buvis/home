"""Verify presence probes and phone delivery without real notifications."""

import base64
import json
import subprocess
import unittest
import urllib.error
from unittest.mock import patch

import notifications


class NotificationTests(unittest.TestCase):
    def test_idle_nanoseconds_are_converted_to_seconds(self) -> None:
        with patch.object(notifications.subprocess, "run", autospec=True) as run:
            run.return_value.stdout = '"HIDIdleTime" = 301500000000'
            self.assertEqual(notifications.read_idle_seconds(), 301)
            self.assertEqual(run.call_args.args[0], ["ioreg", "-c", "IOHIDSystem"])

    def test_missing_idle_measurement_preserves_zero_fallback(self) -> None:
        self.assertEqual(notifications.parse_idle_seconds('"HIDIdleTime" = nope'), 0)

    def test_idle_timeout_preserves_zero_fallback(self) -> None:
        with patch.object(
            notifications.subprocess,
            "run",
            autospec=True,
            side_effect=subprocess.TimeoutExpired("ioreg", 5),
        ):
            self.assertEqual(notifications.read_idle_seconds(), 0)

    def test_screensaver_process_is_detected(self) -> None:
        with patch.object(notifications.subprocess, "run", autospec=True) as run:
            run.return_value.returncode = 0
            self.assertTrue(notifications.screensaver_active())
            self.assertEqual(
                run.call_args.args[0], ["pgrep", "-q", "ScreenSaverEngine"]
            )

    def test_missing_screensaver_tool_preserves_false_fallback(self) -> None:
        with patch.object(
            notifications.subprocess,
            "run",
            autospec=True,
            side_effect=FileNotFoundError,
        ):
            self.assertFalse(notifications.screensaver_active())

    def test_phone_delivery_reads_only_herdr_config(self) -> None:
        config = {
            "url": "https://ntfy.example/",
            "topic": "test",
            "credentials": "user:pass",
        }
        with (
            patch.object(
                notifications.Path,
                "read_text",
                autospec=True,
                return_value=json.dumps(config),
            ) as read,
            patch.dict(notifications.os.environ, {}, clear=True),
            patch.object(
                notifications.urllib.request, "urlopen", autospec=True
            ) as send,
        ):
            send.return_value.__enter__.return_value.status = 200
            self.assertTrue(notifications.send_ntfy("Title", "Message"))
            read.assert_called_once_with(notifications.CONFIG_PATH, encoding="utf-8")
            request = send.call_args.args[0]
            self.assertEqual(request.full_url, "https://ntfy.example/test")
            self.assertEqual(request.data, b"Message")
            self.assertEqual(request.get_header("Authorization"), "Basic dXNlcjpwYXNz")
            self.assertEqual(request.get_header("User-agent"), "herdr-pager/1.0")

    def test_environment_destination_override_is_preserved(self) -> None:
        with (
            patch.object(
                notifications.Path,
                "read_text",
                autospec=True,
                return_value=json.dumps(
                    {"url": "https://old.example", "topic": "old", "credentials": ""}
                ),
            ),
            patch.dict(
                notifications.os.environ,
                {"NTFY_URL": "https://new.example", "NTFY_TOPIC": "new"},
            ),
            patch.object(
                notifications.urllib.request, "urlopen", autospec=True
            ) as send,
        ):
            send.return_value.__enter__.return_value.status = 200
            self.assertTrue(notifications.send_ntfy("Title", "Message"))
            self.assertEqual(send.call_args.args[0].full_url, "https://new.example/new")

    def test_missing_private_config_does_not_send(self) -> None:
        with (
            patch.object(
                notifications.Path,
                "read_text",
                autospec=True,
                side_effect=FileNotFoundError,
            ),
            patch.object(
                notifications.urllib.request, "urlopen", autospec=True
            ) as send,
        ):
            self.assertFalse(notifications.send_ntfy("Title", "Message"))
            send.assert_not_called()

    def test_invalid_private_config_does_not_send(self) -> None:
        with (
            patch.object(
                notifications.Path,
                "read_text",
                autospec=True,
                return_value='{"url": null}',
            ),
            patch.object(
                notifications.urllib.request, "urlopen", autospec=True
            ) as send,
        ):
            self.assertFalse(notifications.send_ntfy("Title", "Message"))
            send.assert_not_called()

    def test_network_failure_returns_false(self) -> None:
        with (
            patch.object(
                notifications.Path,
                "read_text",
                autospec=True,
                return_value=json.dumps(
                    {"url": "https://ntfy.example", "topic": "test", "credentials": ""}
                ),
            ),
            patch.dict(notifications.os.environ, {}, clear=True),
            patch.object(
                notifications.urllib.request,
                "urlopen",
                autospec=True,
                side_effect=urllib.error.URLError("offline"),
            ),
        ):
            self.assertFalse(notifications.send_ntfy("Title", "Message"))

    def test_unicode_and_newlines_are_safe_in_titles(self) -> None:
        title = "Finished ✅\r\nHeader: injected"
        request = notifications.build_ntfy_request(
            "https://ntfy.example", "test", title, "M", ""
        )
        expected = base64.b64encode(title.encode()).decode()
        self.assertEqual(request.get_header("Title"), f"=?UTF-8?B?{expected}?=")


if __name__ == "__main__":
    unittest.main()
