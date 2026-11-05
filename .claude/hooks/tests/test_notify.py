"""Tests for hooks/notify.py."""

import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
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

    def test_emoji_title_is_header_safe(self) -> None:
        # Regression (2026-07-09 drain): the wrapper sends titles like
        # "autopilot ✅ repo"; urllib encodes headers as latin-1, so a raw
        # emoji title crashes urlopen with UnicodeEncodeError. The header
        # must be latin-1-encodable (RFC 2047 encoded-word for non-latin-1).
        req = notify.build_ntfy_request(
            "https://ntfy.example.com", "topic", "autopilot ✅ repo", "M", ""
        )
        title = req.headers["Title"]
        title.encode("latin-1")  # must not raise
        self.assertTrue(title.startswith("=?UTF-8?B?"))

    def test_plain_ascii_title_unchanged(self) -> None:
        req = notify.build_ntfy_request(
            "https://ntfy.example.com", "topic", "plain title", "M", ""
        )
        self.assertEqual(req.headers["Title"], "plain title")

    def test_crlf_title_is_rfc2047_encoded(self) -> None:
        # Header-injection shape: a bare CR/LF in a header value makes
        # urllib's http.client raise a raw ValueError ("Invalid header
        # value"), even though the request would be correctly rejected
        # rather than exploited. RFC-2047 encoding it here means the
        # notification still goes out, cleaned, instead of vanishing behind
        # an uncaught exception.
        value = "Claude [evil\r\nX-Agoge-Injected: yes]: waiting"
        req = notify.build_ntfy_request(
            "https://ntfy.example.com", "topic", value, "M", ""
        )
        title = req.headers["Title"]
        title.encode("latin-1")  # must not raise
        self.assertTrue(title.startswith("=?UTF-8?B?"))
        self.assertNotIn("\r", title)
        self.assertNotIn("\n", title)
        token = title[len("=?UTF-8?B?") : -len("?=")]
        self.assertEqual(base64.b64decode(token).decode("utf-8"), value)


class TestSendNtfy(unittest.TestCase):
    # SETTINGS_PATH is patched away so these stay hermetic: the machine's
    # real settings.json carries an env block that would satisfy the fallback.
    def test_skips_when_url_unset(self) -> None:
        with patch.dict("os.environ", {"NTFY_URL": "", "NTFY_TOPIC": "t"}, clear=False):
            with patch("notify.SETTINGS_PATH", Path("/nonexistent/settings.json")):
                with patch("notify.urllib.request.urlopen") as urlopen:
                    with patch("notify.log_line"):
                        notify.send_ntfy("title", "msg")
                    urlopen.assert_not_called()

    def test_skips_when_topic_unset(self) -> None:
        with patch.dict("os.environ", {"NTFY_URL": "https://x", "NTFY_TOPIC": ""}, clear=False):
            with patch("notify.SETTINGS_PATH", Path("/nonexistent/settings.json")):
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
                        result = notify.send_ntfy("T", "M")
                    urlopen.assert_called_once()
        # assertIs, not assertEqual/assertTrue: this pins the exact bool
        # singleton, so neither None (the pre-fix behavior) nor a truthy 1
        # passes.
        self.assertIs(result, True)

    def test_returns_false_on_url_error(self) -> None:
        env = {"NTFY_URL": "https://ntfy.x", "NTFY_TOPIC": "topic"}
        with patch.dict("os.environ", env, clear=False):
            with patch("notify.read_credentials", return_value=""):
                with patch(
                    "notify.urllib.request.urlopen",
                    side_effect=notify.urllib.error.URLError("unreachable"),
                ):
                    with patch("notify.log_line"):
                        result = notify.send_ntfy("T", "M")
        # assertIs, not assertEqual/assertFalse: this pins the exact bool
        # singleton, so neither None (the pre-fix behavior) nor a falsy 0
        # passes.
        self.assertIs(result, False)

    def test_returns_false_on_http_error(self) -> None:
        env = {"NTFY_URL": "https://ntfy.x", "NTFY_TOPIC": "topic"}
        with patch.dict("os.environ", env, clear=False):
            with patch("notify.read_credentials", return_value=""):
                with patch(
                    "notify.urllib.request.urlopen",
                    side_effect=notify.urllib.error.HTTPError(
                        "https://ntfy.x/topic", 500, "Internal Server Error", None, None
                    ),
                ):
                    with patch("notify.log_line"):
                        result = notify.send_ntfy("T", "M")
        # assertIs, not assertEqual/assertFalse: this pins the exact bool
        # singleton, so neither None (the pre-fix behavior) nor a falsy 0
        # passes.
        self.assertIs(result, False)

    def test_returns_false_on_urlopen_value_error(self) -> None:
        # Defense in depth: even with a header-safe title, urlopen raising a
        # bare ValueError (not just URLError/OSError) must not propagate past
        # send_ntfy - the widened except clause is the fix under test.
        env = {"NTFY_URL": "https://ntfy.x", "NTFY_TOPIC": "topic"}
        with patch.dict("os.environ", env, clear=False):
            with patch("notify.read_credentials", return_value=""):
                with patch(
                    "notify.urllib.request.urlopen",
                    side_effect=ValueError("Invalid header value"),
                ):
                    with patch("notify.log_line"):
                        result = notify.send_ntfy("T", "M")
        # assertIs, not assertEqual/assertFalse: this pins the exact bool
        # singleton, so neither None (the pre-fix behavior) nor a falsy 0
        # passes.
        self.assertIs(result, False)


class TestSettingsEnvFallback(unittest.TestCase):
    """Regression (2026-07-12): autoclaude's loop-exit `--send` runs outside a
    Claude session, where the settings.json env block is not injected, so the
    death alert was skipped with "NTFY_URL or NTFY_TOPIC unset"."""

    @staticmethod
    def _response() -> MagicMock:
        resp = MagicMock()
        resp.status = 200
        resp.__enter__ = lambda s: s
        resp.__exit__ = lambda *a: None
        return resp

    def test_settings_env_reads_env_block(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            settings = Path(td) / "settings.json"
            settings.write_text(
                json.dumps({"env": {"NTFY_URL": "https://ntfy.s", "NTFY_TOPIC": "tp"}}),
                encoding="utf-8",
            )
            with patch("notify.SETTINGS_PATH", settings):
                self.assertEqual(notify._settings_env("NTFY_URL"), "https://ntfy.s")
                self.assertEqual(notify._settings_env("NTFY_TOPIC"), "tp")

    def test_settings_env_missing_file(self) -> None:
        with patch("notify.SETTINGS_PATH", Path("/nonexistent/settings.json")):
            self.assertEqual(notify._settings_env("NTFY_URL"), "")

    def test_settings_env_malformed_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            settings = Path(td) / "settings.json"
            settings.write_text("{nope", encoding="utf-8")
            with patch("notify.SETTINGS_PATH", settings):
                self.assertEqual(notify._settings_env("NTFY_URL"), "")

    def test_send_ntfy_falls_back_to_settings(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            settings = Path(td) / "settings.json"
            settings.write_text(
                json.dumps({"env": {"NTFY_URL": "https://ntfy.s", "NTFY_TOPIC": "tp"}}),
                encoding="utf-8",
            )
            resp = self._response()
            with patch.dict("os.environ", {"NTFY_URL": "", "NTFY_TOPIC": ""}, clear=False):
                with patch("notify.SETTINGS_PATH", settings):
                    with patch("notify.read_credentials", return_value=""):
                        with patch("notify.urllib.request.urlopen", return_value=resp) as urlopen:
                            with patch("notify.log_line"):
                                notify.send_ntfy("T", "M")
                            urlopen.assert_called_once()
                            req = urlopen.call_args[0][0]
                            self.assertEqual(req.full_url, "https://ntfy.s/tp")

    def test_env_wins_over_settings(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            settings = Path(td) / "settings.json"
            settings.write_text(
                json.dumps({"env": {"NTFY_URL": "https://ntfy.settings", "NTFY_TOPIC": "st"}}),
                encoding="utf-8",
            )
            resp = self._response()
            env = {"NTFY_URL": "https://ntfy.env", "NTFY_TOPIC": "et"}
            with patch.dict("os.environ", env, clear=False):
                with patch("notify.SETTINGS_PATH", settings):
                    with patch("notify.read_credentials", return_value=""):
                        with patch("notify.urllib.request.urlopen", return_value=resp) as urlopen:
                            with patch("notify.log_line"):
                                notify.send_ntfy("T", "M")
                            req = urlopen.call_args[0][0]
                            self.assertEqual(req.full_url, "https://ntfy.env/et")


class TestShowDesktopNotification(unittest.TestCase):
    def _run(self, returncode: int) -> list[str]:
        logs: list[str] = []
        proc = MagicMock()
        proc.returncode = returncode
        with patch("notify.shutil.which", return_value="/usr/bin/terminal-notifier"):
            with patch("notify.subprocess.run", return_value=proc):
                with patch("notify.log_line", side_effect=logs.append):
                    notify.show_desktop_notification("T", "M")
        return logs

    def test_logs_shown_on_success(self) -> None:
        logs = self._run(0)
        self.assertTrue(any("shown" in line for line in logs))
        self.assertFalse(any("ERROR" in line for line in logs))

    def test_logs_error_on_nonzero_exit(self) -> None:
        # terminal-notifier exit 0 means it ran, not that macOS displayed the
        # banner — but a non-zero exit is an unambiguous failure that must not
        # be logged as success.
        logs = self._run(1)
        self.assertTrue(any("ERROR" in line for line in logs))
        self.assertFalse(any("shown" in line for line in logs))

    def test_skips_when_not_installed(self) -> None:
        logs: list[str] = []
        with patch("notify.shutil.which", return_value=None):
            with patch("notify.log_line", side_effect=logs.append):
                notify.show_desktop_notification("T", "M")
        self.assertTrue(any("Skipped" in line for line in logs))

    def test_nonzero_exit_returns_false(self) -> None:
        proc = MagicMock()
        proc.returncode = 1
        with patch("notify.shutil.which", return_value="/usr/bin/terminal-notifier"):
            with patch("notify.subprocess.run", return_value=proc):
                with patch("notify.log_line"):
                    result = notify.show_desktop_notification("T", "M")
        # assertIs, not assertEqual/assertFalse: this pins the exact bool
        # singleton, so neither None (the pre-fix behavior) nor a falsy 0
        # passes.
        self.assertIs(result, False)

    def test_success_returns_true(self) -> None:
        proc = MagicMock()
        proc.returncode = 0
        with patch("notify.shutil.which", return_value="/usr/bin/terminal-notifier"):
            with patch("notify.subprocess.run", return_value=proc):
                with patch("notify.log_line"):
                    result = notify.show_desktop_notification("T", "M")
        # assertIs, not assertEqual/assertTrue: this pins the exact bool
        # singleton, so neither None (the pre-fix behavior) nor a truthy 1
        # passes.
        self.assertIs(result, True)

    def test_retries_without_image_when_sandbox_denies_attachment(self) -> None:
        # Under the run-agent Seatbelt profile, -contentImage fails with exit 5
        # ("Failed to move attachment file into data store"); plain text works.
        fail, ok = MagicMock(returncode=5), MagicMock(returncode=0)
        with patch("notify.shutil.which", return_value="/usr/bin/terminal-notifier"):
            with patch("notify.subprocess.run", side_effect=[fail, ok]) as run:
                with patch("notify.log_line"):
                    result = notify.show_desktop_notification("T", "M")
        self.assertIs(result, True)
        self.assertIn("-contentImage", run.call_args_list[0][0][0])
        self.assertNotIn("-contentImage", run.call_args_list[1][0][0])


class TestDispatch(unittest.TestCase):
    def test_returns_send_ntfy_result_when_user_away(self) -> None:
        with patch("notify.read_idle_seconds", return_value=301):
            with patch("notify.screensaver_active", return_value=False):
                with patch("notify.lid_closed", return_value=False):
                    with patch("notify.send_ntfy", return_value=False) as send:
                        with patch("notify.show_desktop_notification") as show:
                            result = notify.dispatch("T", "M")
        # assertIs, not assertEqual/assertFalse: this pins the exact bool
        # singleton, so neither None (the pre-fix behavior) nor a falsy 0
        # passes.
        self.assertIs(result, False)
        send.assert_called_once_with("T", "M")
        show.assert_not_called()

    def test_returns_desktop_notification_result_when_user_present(self) -> None:
        with patch("notify.read_idle_seconds", return_value=0):
            with patch("notify.screensaver_active", return_value=False):
                with patch("notify.lid_closed", return_value=False):
                    with patch("notify.send_ntfy") as send:
                        with patch(
                            "notify.show_desktop_notification", return_value=True
                        ) as show:
                            result = notify.dispatch("T", "M")
        self.assertTrue(result)
        show.assert_called_once_with("T", "M")
        send.assert_not_called()


class TestSendCli(unittest.TestCase):
    def test_exits_nonzero_when_delivery_fails(self) -> None:
        with patch("sys.argv", ["notify.py", "--send", "T", "M"]):
            with patch("notify.dispatch", return_value=False):
                with patch("notify.log_line"):
                    with self.assertRaises(SystemExit) as ctx:
                        notify.main()
        self.assertEqual(ctx.exception.code, 1)

    def test_no_exit_when_delivery_succeeds(self) -> None:
        with patch("sys.argv", ["notify.py", "--send", "T", "M"]):
            with patch("notify.dispatch", return_value=True):
                with patch("notify.log_line"):
                    notify.main()  # must not raise SystemExit


class TestAutopilotLoopActive(unittest.TestCase):
    def test_false_when_env_unset(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(notify.autopilot_loop_active())

    def test_false_when_not_a_pid(self) -> None:
        with patch.dict("os.environ", {"_AUTOPILOT_LOOP": "nope"}, clear=True):
            self.assertFalse(notify.autopilot_loop_active())

    def test_true_when_pid_alive(self) -> None:
        # Our own PID is guaranteed alive — os.kill(pid, 0) succeeds.
        with patch.dict("os.environ", {"_AUTOPILOT_LOOP": str(os.getpid())}, clear=True):
            self.assertTrue(notify.autopilot_loop_active())

    def test_false_when_pid_dead(self) -> None:
        with patch.dict("os.environ", {"_AUTOPILOT_LOOP": "424242"}, clear=True):
            with patch("notify.os.kill", side_effect=ProcessLookupError):
                self.assertFalse(notify.autopilot_loop_active())


class TestCountAgentAncestors(unittest.TestCase):
    """Regression (2026-07-21): codex's exec sandbox scrubs env, so nested
    `claude -p` parity probes lost _AUTOPILOT_LOOP/CLAUDE_NESTED and paged
    "done" mid-loop (/tmp/gate71). Process ancestry is the env-proof signal:
    the first agent CLI in the ppid chain is the session itself, a second
    one above it means nested dispatch."""

    PS_NESTED = (
        "  100     1 /sbin/launchd\n"
        "  200   100 /Applications/WezTerm.app/Contents/MacOS/wezterm-gui\n"
        "  300   200 -bash\n"
        "  400   300 /Users/x/.local/bin/claude\n"
        "  500   400 /bin/bash\n"
        "  600   500 /Users/x/.local/share/mise/installs/codex/1.0/bin/codex\n"
        "  700   600 /Users/x/.local/bin/claude\n"
    )
    PS_INTERACTIVE = (
        "  100     1 /sbin/launchd\n"
        "  200   100 /Applications/WezTerm.app/Contents/MacOS/wezterm-gui\n"
        "  300   200 -bash\n"
        "  400   300 /Users/x/.local/bin/claude\n"
    )

    def test_nested_probe_chain_counts_all_agents(self) -> None:
        # probe claude (700) ← codex (600) ← review claude (400)
        self.assertEqual(notify._count_agent_ancestors(self.PS_NESTED, 700), 3)

    def test_interactive_chain_counts_one(self) -> None:
        self.assertEqual(notify._count_agent_ancestors(self.PS_INTERACTIVE, 400), 1)

    def test_unknown_start_pid_counts_zero(self) -> None:
        self.assertEqual(notify._count_agent_ancestors(self.PS_INTERACTIVE, 999), 0)

    def test_garbage_ps_output_counts_zero(self) -> None:
        self.assertEqual(notify._count_agent_ancestors("nope\nx y\n", 400), 0)

    def test_login_shell_dash_prefix_not_an_agent(self) -> None:
        # "-bash" must not basename-match anything in AGENT_CLIS
        self.assertEqual(notify._count_agent_ancestors("  300     1 -bash\n", 300), 0)


class TestDispatchedByAgent(unittest.TestCase):
    def test_process_inspection_denied_returns_false(self) -> None:
        with patch("notify.subprocess.run", side_effect=PermissionError(1, "Operation not permitted", "ps")):
            self.assertFalse(notify.dispatched_by_agent())


if __name__ == "__main__":
    unittest.main()
