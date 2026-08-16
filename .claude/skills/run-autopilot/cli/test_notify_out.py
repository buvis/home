"""Tests for cli/pause.py and cli/notify_out.py (PRD 00106)."""

from __future__ import annotations

from pathlib import Path

from cli.notify_out import notify
from cli.pause import consume_pause


def test_consume_pause_removes_the_marker_and_reports_it(tmp_path):
    (tmp_path / "pause-requested").touch()
    assert consume_pause(tmp_path) is True
    assert not (tmp_path / "pause-requested").exists()


def test_consume_pause_without_a_marker_is_false(tmp_path):
    assert consume_pause(tmp_path) is False


def _recording_script(tmp_path: Path) -> Path:
    out = tmp_path / "argv.txt"
    script = tmp_path / "fake_notify.py"
    script.write_text(
        f"import sys\nopen({str(out)!r}, 'a').write(repr(sys.argv[1:]) + '\\n')\n",
    )
    return script


def test_notify_shells_the_wrapper_command_shape(tmp_path):
    script = _recording_script(tmp_path)
    notify("autopilot ✅ repo", "Backlog drained.", script=script)
    recorded = (tmp_path / "argv.txt").read_text().strip()
    assert recorded == repr(["--send", "autopilot ✅ repo", "Backlog drained."])


def test_notify_swallows_a_failing_notifier(tmp_path):
    script = tmp_path / "boom.py"
    script.write_text("import sys\nsys.exit(3)\n")
    notify("t", "b", script=script)  # must not raise


def test_notify_swallows_a_missing_notifier(tmp_path):
    notify("t", "b", script=tmp_path / "absent.py")  # must not raise
