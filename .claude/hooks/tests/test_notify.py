"""Tests for hooks/notify.py."""

import unittest
from unittest.mock import MagicMock, patch

import notify


class TestProjectName(unittest.TestCase):
    def test_basic_path(self) -> None:
        self.assertEqual(notify.project_name("/Users/bob/git/foo"), "foo")

    def test_trailing_slash(self) -> None:
        self.assertEqual(notify.project_name("/Users/bob/git/foo/"), "foo")

    def test_empty(self) -> None:
        self.assertEqual(notify.project_name(""), "")


class TestBuildEventStrings(unittest.TestCase):
    def test_stop_event(self) -> None:
        ev, title, msg = notify.build_event_strings(
            {"hook_event_name": "Stop", "cwd": "/x/proj"}
        )
        self.assertEqual(ev, "Stop")
        self.assertEqual(title, "Claude [proj]: done")
        self.assertEqual(msg, "Task complete")

    def test_notification_with_message(self) -> None:
        ev, title, msg = notify.build_event_strings(
            {"hook_event_name": "Notification", "cwd": "/x/proj", "message": "hi"}
        )
        self.assertEqual(ev, "Notification")
        self.assertEqual(title, "Claude [proj]: waiting")
        self.assertEqual(msg, "hi")

    def test_notification_default_message(self) -> None:
        _, _, msg = notify.build_event_strings(
            {"hook_event_name": "Notification", "cwd": "/x/proj"}
        )
        self.assertEqual(msg, "Awaiting input")

    def test_unknown_event(self) -> None:
        ev, title, msg = notify.build_event_strings(
            {"hook_event_name": "Custom", "cwd": "/x/proj"}
        )
        self.assertEqual(ev, "Custom")
        self.assertEqual(title, "Claude [proj]: Custom")
        self.assertEqual(msg, "Event triggered")

    def test_missing_event_and_cwd(self) -> None:
        ev, title, msg = notify.build_event_strings({})
        self.assertEqual(ev, "")
        self.assertEqual(title, "Claude []: ")
        self.assertEqual(msg, "Event triggered")


class TestParseIdleSeconds(unittest.TestCase):
    def test_parses_hidIdleTime(self) -> None:
        out = (
            '  | |   "HIDIdleTime" = 7500000000\n'
            '  | |   "HIDPointerAccel" = 0\n'
        )
        self.assertEqual(notify.parse_idle_seconds(out), 7)

    def test_no_match_returns_zero(self) -> None:
        self.assertEqual(notify.parse_idle_seconds("nothing relevant"), 0)

    def test_empty_returns_zero(self) -> None:
        self.assertEqual(notify.parse_idle_seconds(""), 0)

    def test_ignores_unparseable_value(self) -> None:
        self.assertEqual(notify.parse_idle_seconds('"HIDIdleTime" = abc'), 0)


class TestParseLidAngle(unittest.TestCase):
    def test_integer_output(self) -> None:
        self.assertEqual(notify.parse_lid_angle("90\n"), 90)

    def test_float_output(self) -> None:
        self.assertEqual(notify.parse_lid_angle("87.5\n"), 87)

    def test_zero(self) -> None:
        self.assertEqual(notify.parse_lid_angle("0"), 0)

    def test_empty_returns_none(self) -> None:
        self.assertIsNone(notify.parse_lid_angle(""))

    def test_garbage_returns_none(self) -> None:
        self.assertIsNone(notify.parse_lid_angle("oops"))


class TestShouldNotify(unittest.TestCase):
    def test_idle_above_threshold(self) -> None:
        self.assertTrue(notify.should_notify(301, False, False))

    def test_idle_at_threshold_is_false(self) -> None:
        self.assertFalse(notify.should_notify(300, False, False))

    def test_screensaver(self) -> None:
        self.assertTrue(notify.should_notify(0, True, False))

    def test_lid_closed(self) -> None:
        self.assertTrue(notify.should_notify(0, False, True))

    def test_user_present(self) -> None:
        self.assertFalse(notify.should_notify(10, False, False))


class TestBuildNtfyRequest(unittest.TestCase):
    def test_url_and_headers(self) -> None:
        req = notify.build_ntfy_request(
            "https://ntfy.example.com", "topic", "T", "M", "user:pw"
        )
        self.assertEqual(req.full_url, "https://ntfy.example.com/topic")
        self.assertEqual(req.method, "POST")
        self.assertEqual(req.data, b"M")
        self.assertEqual(req.headers["Title"], "T")
        self.assertEqual(req.headers["Tags"], "computer")
        self.assertTrue(req.headers["Authorization"].startswith("Basic "))
        # User-Agent must not be urllib's default — Cloudflare bot rules block
        # `Python-urllib/*` with HTTP 403 (error code 1010). See notify.py.
        ua = req.headers["User-agent"]
        self.assertTrue(ua and not ua.lower().startswith("python-urllib"))

    def test_strips_trailing_slash(self) -> None:
        req = notify.build_ntfy_request(
            "https://ntfy.example.com/", "topic", "T", "M", ""
        )
        self.assertEqual(req.full_url, "https://ntfy.example.com/topic")

    def test_no_auth_when_creds_empty(self) -> None:
        req = notify.build_ntfy_request(
            "https://ntfy.example.com", "topic", "T", "M", ""
        )
        self.assertNotIn("Authorization", req.headers)


class TestSendNtfy(unittest.TestCase):
    def test_skips_when_url_unset(self) -> None:
        with patch.dict("os.environ", {"NTFY_URL": "", "NTFY_TOPIC": "t"}, clear=False):
            with patch("notify.urllib.request.urlopen") as urlopen:
                with patch("notify.log_line"):
                    notify.send_ntfy("title", "msg")
                urlopen.assert_not_called()

    def test_skips_when_topic_unset(self) -> None:
        with patch.dict("os.environ", {"NTFY_URL": "https://x", "NTFY_TOPIC": ""}, clear=False):
            with patch("notify.urllib.request.urlopen") as urlopen:
                with patch("notify.log_line"):
                    notify.send_ntfy("title", "msg")
                urlopen.assert_not_called()

    def test_posts_when_configured(self) -> None:
        env = {"NTFY_URL": "https://ntfy.x", "NTFY_TOPIC": "topic"}
        resp = MagicMock()
        resp.status = 200
        resp.__enter__ = lambda s: s
        resp.__exit__ = lambda *a: None
        with patch.dict("os.environ", env, clear=False):
            with patch("notify.read_credentials", return_value=""):
                with patch("notify.urllib.request.urlopen", return_value=resp) as urlopen:
                    with patch("notify.log_line"):
                        notify.send_ntfy("T", "M")
                    urlopen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
