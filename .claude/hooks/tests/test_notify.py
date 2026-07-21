"""Tests for hooks/notify.py."""

import json
import os
import tempfile
import time
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
                        notify.send_ntfy("T", "M")
                    urlopen.assert_called_once()


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


class TestMainSuppression(unittest.TestCase):
    def _run_main(self, payload: dict, env: dict) -> list[str]:
        logs: list[str] = []
        with patch.dict("os.environ", env, clear=True):
            with patch("notify.read_input", return_value=payload):
                with patch("notify.log_line", side_effect=logs.append):
                    with patch("notify.send_ntfy") as send:
                        with patch("notify.show_desktop_notification") as show:
                            with patch("notify.dispatched_by_agent", return_value=False), patch("notify.read_idle_seconds", return_value=0):
                                with patch("notify.screensaver_active", return_value=False):
                                    with patch("notify.lid_closed", return_value=False):
                                        notify.main()
                            self._send = send
                            self._show = show
        return logs

    def test_stop_suppressed_when_loop_active(self) -> None:
        logs = self._run_main(
            {"hook_event_name": "Stop", "cwd": "/x/proj"},
            {"_AUTOPILOT_LOOP": str(os.getpid())},
        )
        self.assertTrue(any("Suppressed" in line for line in logs))
        self._send.assert_not_called()
        self._show.assert_not_called()

    def test_stop_notifies_when_loop_inactive(self) -> None:
        logs = self._run_main(
            {"hook_event_name": "Stop", "cwd": "/x/proj"},
            {},  # no _AUTOPILOT_LOOP → not in a loop
        )
        self.assertFalse(any("Suppressed" in line for line in logs))
        # User present (idle=0, no screensaver, lid open) → desktop path.
        self._show.assert_called_once()
        self._send.assert_not_called()

    def test_idle_prompt_suppressed_when_loop_active(self) -> None:
        # The bug this fixes: a parked-on-background-task idle ping mid-loop.
        logs = self._run_main(
            {
                "hook_event_name": "Notification",
                "cwd": "/x/proj",
                "message": "Claude is waiting for your input",
                "notification_type": "idle_prompt",
            },
            {"_AUTOPILOT_LOOP": str(os.getpid())},
        )
        self.assertTrue(any("Suppressed" in line for line in logs))
        self._show.assert_not_called()
        self._send.assert_not_called()

    def test_permission_prompt_fires_when_loop_active(self) -> None:
        # A real "needs you" must still page even inside a live loop.
        logs = self._run_main(
            {
                "hook_event_name": "Notification",
                "cwd": "/x/proj",
                "message": "Claude needs your permission",
                "notification_type": "permission_prompt",
            },
            {"_AUTOPILOT_LOOP": str(os.getpid())},
        )
        self.assertFalse(any("Suppressed" in line for line in logs))
        self._show.assert_called_once()

    def test_idle_prompt_fires_when_loop_inactive(self) -> None:
        self._run_main(
            {
                "hook_event_name": "Notification",
                "cwd": "/x/proj",
                "message": "Claude is waiting for your input",
                "notification_type": "idle_prompt",
            },
            {},  # not in a loop → normal interactive session, page as usual
        )
        self._show.assert_called_once()


class TestBackgroundTaskSuppression(unittest.TestCase):
    """Regression (2026-07-19): Stop fires per-turn, and a fan-out job's turn
    ends while its subagents keep running — notify.py sent "done" 4 times in
    one job. The Stop payload's background_tasks array is the authoritative
    "still working" signal; only a Stop with none running is a real done."""

    def _run_main(self, payload: dict, env: dict) -> list[str]:
        logs: list[str] = []
        with patch.dict("os.environ", env, clear=True):
            with patch("notify.read_input", return_value=payload):
                with patch("notify.log_line", side_effect=logs.append):
                    with patch("notify.send_ntfy") as send:
                        with patch("notify.show_desktop_notification") as show:
                            with patch("notify.dispatched_by_agent", return_value=False), patch("notify.read_idle_seconds", return_value=0):
                                with patch("notify.screensaver_active", return_value=False):
                                    with patch("notify.lid_closed", return_value=False):
                                        notify.main()
                            self._send = send
                            self._show = show
        return logs

    def test_stop_suppressed_while_tasks_running(self) -> None:
        logs = self._run_main(
            {
                "hook_event_name": "Stop",
                "cwd": "/x/proj",
                "background_tasks": [
                    {"id": "a1", "type": "subagent", "status": "running"},
                    {"id": "a2", "type": "subagent", "status": "completed"},
                ],
            },
            {},
        )
        self.assertTrue(any("Suppressed" in line for line in logs))
        self._send.assert_not_called()
        self._show.assert_not_called()

    def test_stop_notifies_when_tasks_empty(self) -> None:
        logs = self._run_main(
            {"hook_event_name": "Stop", "cwd": "/x/proj", "background_tasks": []},
            {},
        )
        self.assertFalse(any("Suppressed" in line for line in logs))
        self._show.assert_called_once()

    def test_stop_notifies_when_all_tasks_terminal(self) -> None:
        self._run_main(
            {
                "hook_event_name": "Stop",
                "cwd": "/x/proj",
                "background_tasks": [
                    {"id": "a1", "type": "subagent", "status": "completed"},
                    {"id": "b1", "type": "shell", "status": "failed"},
                ],
            },
            {},
        )
        self._show.assert_called_once()


class TestNotifyQuiet(unittest.TestCase):
    """Regression (2026-07-19): sonnet-run.sh unsets _AUTOPILOT_LOOP for nested
    claude reviewers (the coverage hook gates on it), which re-enabled their
    Stop "done" pings mid-batch. The runner now exports _CLAUDE_NOTIFY_QUIET=1;
    notify.py must treat it like loop noise: silence Stop and idle_prompt,
    still page permission_prompt."""

    def _run_main(self, payload: dict, env: dict) -> list[str]:
        logs: list[str] = []
        with patch.dict("os.environ", env, clear=True):
            with patch("notify.read_input", return_value=payload):
                with patch("notify.log_line", side_effect=logs.append):
                    with patch("notify.send_ntfy") as send:
                        with patch("notify.show_desktop_notification") as show:
                            with patch("notify.dispatched_by_agent", return_value=False), patch("notify.read_idle_seconds", return_value=0):
                                with patch("notify.screensaver_active", return_value=False):
                                    with patch("notify.lid_closed", return_value=False):
                                        notify.main()
                            self._send = send
                            self._show = show
        return logs

    def test_stop_suppressed_when_quiet(self) -> None:
        logs = self._run_main(
            {"hook_event_name": "Stop", "cwd": "/x/proj"},
            {"_CLAUDE_NOTIFY_QUIET": "1"},
        )
        self.assertTrue(any("Suppressed" in line for line in logs))
        self._send.assert_not_called()
        self._show.assert_not_called()

    def test_idle_prompt_suppressed_when_quiet(self) -> None:
        logs = self._run_main(
            {
                "hook_event_name": "Notification",
                "cwd": "/x/proj",
                "message": "Claude is waiting for your input",
                "notification_type": "idle_prompt",
            },
            {"_CLAUDE_NOTIFY_QUIET": "1"},
        )
        self.assertTrue(any("Suppressed" in line for line in logs))
        self._show.assert_not_called()

    def test_permission_prompt_fires_when_quiet(self) -> None:
        logs = self._run_main(
            {
                "hook_event_name": "Notification",
                "cwd": "/x/proj",
                "message": "Claude needs your permission",
                "notification_type": "permission_prompt",
            },
            {"_CLAUDE_NOTIFY_QUIET": "1"},
        )
        self.assertFalse(any("Suppressed" in line for line in logs))
        self._show.assert_called_once()


class TestIdlePromptWithLiveAgents(unittest.TestCase):
    """Regression (2026-07-19): after the Stop fix, the ~60s-later idle_prompt
    still pinged "waiting" while background agents ran. idle_prompt payloads
    carry no background_tasks; the disk proxy is a subagents/agent-*.jsonl
    written within the last <60s — only a live background agent writes after
    the turn ends (foreground agents finish before it)."""

    def _run_main(self, payload: dict) -> list[str]:
        logs: list[str] = []
        with patch.dict("os.environ", {}, clear=True):
            with patch("notify.read_input", return_value=payload):
                with patch("notify.log_line", side_effect=logs.append):
                    with patch("notify.send_ntfy") as send:
                        with patch("notify.show_desktop_notification") as show:
                            with patch("notify.dispatched_by_agent", return_value=False), patch("notify.read_idle_seconds", return_value=0):
                                with patch("notify.screensaver_active", return_value=False):
                                    with patch("notify.lid_closed", return_value=False):
                                        notify.main()
                            self._send = send
                            self._show = show
        return logs

    @staticmethod
    def _session(td: str, agent_age_sec: float | None) -> dict:
        transcript = Path(td) / "abc123.jsonl"
        transcript.write_text("{}\n", encoding="utf-8")
        if agent_age_sec is not None:
            subagents = Path(td) / "abc123" / "subagents"
            subagents.mkdir(parents=True)
            agent = subagents / "agent-deadbeef.jsonl"
            agent.write_text("{}\n", encoding="utf-8")
            mtime = time.time() - agent_age_sec
            os.utime(agent, (mtime, mtime))
        return {
            "hook_event_name": "Notification",
            "cwd": "/x/proj",
            "message": "Claude is waiting for your input",
            "notification_type": "idle_prompt",
            "transcript_path": str(transcript),
        }

    def test_suppressed_when_agent_wrote_recently(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            logs = self._run_main(self._session(td, agent_age_sec=5))
        self.assertTrue(any("Suppressed" in line for line in logs))
        self._show.assert_not_called()
        self._send.assert_not_called()

    def test_fires_when_agent_files_stale(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            logs = self._run_main(self._session(td, agent_age_sec=120))
        self.assertFalse(any("Suppressed" in line for line in logs))
        self._show.assert_called_once()

    def test_fires_when_no_subagents_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            logs = self._run_main(self._session(td, agent_age_sec=None))
        self.assertFalse(any("Suppressed" in line for line in logs))
        self._show.assert_called_once()


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


class TestDispatchedByAgentSuppression(unittest.TestCase):
    """main() must silence Stop/idle_prompt for a session nested under another
    agent CLI even with no env markers at all (the codex-scrubbed-env case)."""

    def _run_main(self, payload: dict, nested: bool) -> list[str]:
        logs: list[str] = []
        with patch.dict("os.environ", {}, clear=True):
            with patch("notify.read_input", return_value=payload):
                with patch("notify.log_line", side_effect=logs.append):
                    with patch("notify.send_ntfy") as send:
                        with patch("notify.show_desktop_notification") as show:
                            with patch("notify.dispatched_by_agent", return_value=nested), patch("notify.read_idle_seconds", return_value=0):
                                with patch("notify.screensaver_active", return_value=False):
                                    with patch("notify.lid_closed", return_value=False):
                                        notify.main()
                            self._send = send
                            self._show = show
        return logs

    def test_stop_suppressed_when_nested(self) -> None:
        logs = self._run_main({"hook_event_name": "Stop", "cwd": "/x/case1"}, nested=True)
        self.assertTrue(any("nested under agent CLI" in line for line in logs))
        self._send.assert_not_called()
        self._show.assert_not_called()

    def test_idle_prompt_suppressed_when_nested(self) -> None:
        logs = self._run_main(
            {
                "hook_event_name": "Notification",
                "cwd": "/x/case1",
                "message": "Claude is waiting for your input",
                "notification_type": "idle_prompt",
            },
            nested=True,
        )
        self.assertTrue(any("Suppressed" in line for line in logs))
        self._show.assert_not_called()

    def test_permission_prompt_fires_when_nested(self) -> None:
        logs = self._run_main(
            {
                "hook_event_name": "Notification",
                "cwd": "/x/case1",
                "message": "Claude needs your permission",
                "notification_type": "permission_prompt",
            },
            nested=True,
        )
        self.assertFalse(any("Suppressed" in line for line in logs))
        self._show.assert_called_once()

    def test_stop_fires_when_not_nested(self) -> None:
        logs = self._run_main({"hook_event_name": "Stop", "cwd": "/x/proj"}, nested=False)
        self.assertFalse(any("Suppressed" in line for line in logs))
        self._show.assert_called_once()


if __name__ == "__main__":
    unittest.main()
