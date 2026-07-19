"""Tests for detect_usage_limit.py.

The helper answers one question for the autoclaude wrapper: is the newest
session transcript for a given cwd stuck at the usage-limit banner, and if
so, when does the limit reset?

Ground truth (observed 2026-07-02/03): on a limit hit the session does NOT
exit. The transcript's last substantive entry is an assistant message with
isApiErrorMessage=true and text like
"You've hit your session limit · resets 8:10pm (Europe/Prague)", followed
only by metadata entries. No Stop hook fires; the TUI idles until input.
"""

import importlib.util
import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPTS_DIR = Path(__file__).parent
HELPER_PATH = SCRIPTS_DIR / "detect_usage_limit.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "detect_usage_limit_under_test", HELPER_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


helper = _load_module()

CWD = "/tmp/fake/repo.x"
MUNGED = "-tmp-fake-repo-x"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _limit_entry(ts: datetime, text: str) -> dict:
    return {
        "type": "assistant",
        "isApiErrorMessage": True,
        "timestamp": _iso(ts),
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
    }


def _assistant_entry(ts: datetime, text: str = "working") -> dict:
    return {
        "type": "assistant",
        "timestamp": _iso(ts),
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
    }


def _meta_tail() -> list[dict]:
    """Metadata entries the harness appends after the error (no timestamps)."""
    return [
        {"type": "system", "subtype": "turn_duration", "durationMs": 1},
        {"type": "last-prompt", "leafUuid": "x", "sessionId": "s"},
        {"type": "mode", "mode": "normal", "sessionId": "s"},
    ]


class DetectUsageLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.proj = self.root / MUNGED
        self.proj.mkdir(parents=True)

    def _write(
        self, name: str, entries: list[dict], mtime: float | None = None
    ) -> Path:
        p = self.proj / name
        p.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
        if mtime is not None:
            os.utime(p, (mtime, mtime))
        return p

    def _detect(self):
        return helper.detect(CWD, projects_root=self.root)

    # ── limit-stuck transcript → reset epoch ────────────────────────────────

    def test_limit_stuck_returns_next_reset_epoch(self) -> None:
        err_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        self._write(
            "a.jsonl",
            [
                _assistant_entry(err_at - timedelta(minutes=1)),
                _limit_entry(
                    err_at,
                    "You've hit your session limit · resets 8:10pm (Europe/Prague)",
                ),
                *_meta_tail(),
            ],
        )
        epoch = self._detect()
        self.assertIsNotNone(epoch)
        tz = ZoneInfo("Europe/Prague")
        anchor = err_at.astimezone(tz)
        expected = anchor.replace(hour=20, minute=10, second=0, microsecond=0)
        if expected <= anchor:
            expected += timedelta(days=1)
        self.assertEqual(epoch, int(expected.timestamp()))

    def test_12am_and_12pm_hours_parse_correctly(self) -> None:
        err_at = datetime.now(timezone.utc)
        self._write(
            "a.jsonl",
            [
                _limit_entry(
                    err_at,
                    "You've hit your session limit · resets 12:05am (Europe/Prague)",
                ),
            ],
        )
        epoch = self._detect()
        self.assertIsNotNone(epoch)
        tz = ZoneInfo("Europe/Prague")
        reset = datetime.fromtimestamp(epoch, tz)
        self.assertEqual((reset.hour, reset.minute), (0, 5))

    def test_unparseable_reset_time_falls_back_to_short_wait(self) -> None:
        """Limit text without a parseable time -> conservative ~15 min wait."""
        err_at = datetime.now(timezone.utc) - timedelta(minutes=2)
        self._write(
            "a.jsonl",
            [_limit_entry(err_at, "You've hit your session limit · try again later")],
        )
        epoch = self._detect()
        self.assertIsNotNone(epoch)
        self.assertAlmostEqual(epoch, int(time.time()) + 900, delta=60)

    # ── non-limited transcripts → None ──────────────────────────────────────

    def test_resumed_session_is_not_limited(self) -> None:
        """User typed past the error -> the record is history, not a live limit."""
        err_at = datetime.now(timezone.utc) - timedelta(hours=1)
        self._write(
            "a.jsonl",
            [
                _limit_entry(
                    err_at,
                    "You've hit your session limit · resets 8:10pm (Europe/Prague)",
                ),
                {
                    "type": "user",
                    "timestamp": _iso(err_at + timedelta(minutes=30)),
                    "message": {"role": "user", "content": "limit reset, continue"},
                },
                _assistant_entry(err_at + timedelta(minutes=31)),
            ],
        )
        self.assertIsNone(self._detect())

    def test_healthy_transcript_is_not_limited(self) -> None:
        self._write(
            "a.jsonl", [_assistant_entry(datetime.now(timezone.utc), "all good")]
        )
        self.assertIsNone(self._detect())

    def test_expired_limit_record_is_not_limited(self) -> None:
        """Reset time long past (relative to the error timestamp) -> stale
        record; a fresh session must not be reaped over it."""
        err_at = datetime.now(timezone.utc) - timedelta(hours=9)
        reset_txt = (err_at + timedelta(hours=3)).astimezone(ZoneInfo("Europe/Prague"))
        hour12 = reset_txt.strftime("%I:%M%p").lower().lstrip("0")
        text = (
            f"You've hit your session limit · resets {hour12} (Europe/Prague)"
        )
        self._write("a.jsonl", [_limit_entry(err_at, text)])
        self.assertIsNone(self._detect())

    def test_old_unparseable_limit_record_is_not_limited(self) -> None:
        err_at = datetime.now(timezone.utc) - timedelta(hours=9)
        self._write(
            "a.jsonl",
            [_limit_entry(err_at, "You've hit your session limit · try again later")],
        )
        self.assertIsNone(self._detect())

    def test_newest_file_wins_over_older_limited_one(self) -> None:
        """A fresh healthy session outranks yesterday's limit-stuck transcript."""
        now = time.time()
        err_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        self._write(
            "old.jsonl",
            [
                _limit_entry(
                    err_at,
                    "You've hit your session limit · resets 8:10pm (Europe/Prague)",
                )
            ],
            mtime=now - 600,
        )
        self._write(
            "new.jsonl",
            [_assistant_entry(datetime.now(timezone.utc))],
            mtime=now,
        )
        self.assertIsNone(self._detect())

    def test_missing_project_dir_is_not_limited(self) -> None:
        self.assertIsNone(helper.detect("/nowhere/at/all", projects_root=self.root))


class DetectFromLogTests(unittest.TestCase):
    """--log mode (PRD 00014): the wrapper's teed last-session.log is the
    primary detection source; only the tail counts as live."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _log(self, text: str, mtime: float | None = None) -> Path:
        p = self.root / "last-session.log"
        p.write_text(text)
        if mtime is not None:
            os.utime(p, (mtime, mtime))
        return p

    def test_banner_in_log_tail_returns_reset_epoch(self) -> None:
        p = self._log(
            '{"type":"result","is_error":true,"result":'
            '"You\'ve hit your usage limit · resets 8:10pm (Europe/Prague)"}\n'
        )
        epoch = helper.detect_from_log(p)
        self.assertIsNotNone(epoch)
        tz = ZoneInfo("Europe/Prague")
        anchor = datetime.fromtimestamp(p.stat().st_mtime, tz)
        expected = anchor.replace(hour=20, minute=10, second=0, microsecond=0)
        if expected <= anchor:
            expected += timedelta(days=1)
        self.assertEqual(epoch, int(expected.timestamp()))

    def test_healthy_log_is_not_limited(self) -> None:
        p = self._log("HANDOFF: build -> review\n")
        self.assertIsNone(helper.detect_from_log(p))

    def test_missing_log_is_not_limited(self) -> None:
        self.assertIsNone(helper.detect_from_log(self.root / "absent.log"))

    def test_unparseable_reset_in_fresh_log_falls_back_to_short_wait(self) -> None:
        p = self._log("You've hit your usage limit · try again later\n")
        epoch = helper.detect_from_log(p)
        self.assertIsNotNone(epoch)
        self.assertAlmostEqual(epoch, int(time.time()) + 900, delta=60)

    def test_old_log_with_expired_reset_is_not_limited(self) -> None:
        old = time.time() - 9 * 3600
        reset_txt = datetime.fromtimestamp(old + 3 * 3600, ZoneInfo("Europe/Prague"))
        hour12 = reset_txt.strftime("%I:%M%p").lower().lstrip("0")
        p = self._log(
            f"You've hit your usage limit · resets {hour12} (Europe/Prague)\n",
            mtime=old,
        )
        self.assertIsNone(helper.detect_from_log(p))

    def test_banner_outside_tail_window_is_ignored(self) -> None:
        """A historical banner early in a long log is not a live limit."""
        filler = "x" * (helper.TAIL_BYTES + 4096)
        p = self._log(
            "You've hit your usage limit · resets 8:10pm (Europe/Prague)\n"
            + filler
            + "\nHANDOFF: done\n"
        )
        self.assertIsNone(helper.detect_from_log(p))

    # ── weekly limit (observed 2026-07-19): seven_day 429 kills the session ──

    def test_weekly_banner_in_log_tail_returns_reset_epoch(self) -> None:
        p = self._log(
            '{"type":"result","is_error":true,"result":'
            '"You\'ve hit your weekly limit · resets 11am (Europe/Prague)"}\n'
        )
        self.assertIsNotNone(helper.detect_from_log(p))

    def test_rejected_rate_limit_event_resets_at_wins_over_prose(self) -> None:
        """The stream-json rate_limit_event carries the exact reset epoch;
        it must win over the ambiguous clock-time prose parse."""
        resets_at = int(time.time()) + 4 * 3600
        p = self._log(
            '{"type":"rate_limit_event","rate_limit_info":{"status":"rejected",'
            f'"resetsAt":{resets_at},"rateLimitType":"seven_day"}}}}\n'
            '{"type":"result","is_error":true,"result":'
            '"You\'ve hit your weekly limit · resets 11am (Europe/Prague)"}\n'
        )
        self.assertEqual(helper.detect_from_log(p), resets_at)

    def test_stale_rejected_rate_limit_event_is_not_limited(self) -> None:
        """A rejected event whose reset already passed is history, not a
        live limit — the loop must not sleep over it."""
        old = time.time() - 9 * 3600
        resets_at = int(old) + 3600
        p = self._log(
            '{"type":"rate_limit_event","rate_limit_info":{"status":"rejected",'
            f'"resetsAt":{resets_at}}}}}\n'
            "HANDOFF: done\n",
            mtime=old,
        )
        self.assertIsNone(helper.detect_from_log(p))

    def test_allowed_rate_limit_event_is_not_limited(self) -> None:
        """Warning-status events during a healthy run must not trigger."""
        resets_at = int(time.time()) + 3600
        p = self._log(
            '{"type":"rate_limit_event","rate_limit_info":{"status":"allowed_warning",'
            f'"resetsAt":{resets_at}}}}}\n'
            "HANDOFF: build -> review\n"
        )
        self.assertIsNone(helper.detect_from_log(p))


if __name__ == "__main__":
    unittest.main()
