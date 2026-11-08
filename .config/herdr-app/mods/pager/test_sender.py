"""Presence and delivery regression tests; no real notifications are sent."""

import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import sender


class SenderTests(unittest.TestCase):
    def test_import_does_not_read_claude_files(self) -> None:
        probe = """
import sys
def reject_claude(event, args):
    if event == "open" and ".claude" in str(args[0]):
        raise RuntimeError("Claude file dependency")
sys.addaudithook(reject_claude)
sys.path.insert(0, sys.argv[1])
import sender
"""
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-c", probe, str(Path(__file__).parent)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_reads_angle_using_mise_installation(self) -> None:
        with patch.object(sender.subprocess, "run", autospec=True) as run:
            run.side_effect = [
                Mock(stdout="/tools/pybooklid/1.0.0\n"),
                Mock(stdout="31.0\n"),
            ]
            self.assertEqual(sender.read_lid_angle(), 31.0)
            self.assertEqual(
                run.call_args_list[0].args[0], ["mise", "where", "pipx:pybooklid"]
            )
            self.assertEqual(
                run.call_args_list[1].args[0][0],
                "/tools/pybooklid/1.0.0/pybooklid/bin/python",
            )

    def test_invalid_angle_is_not_silently_treated_as_open(self) -> None:
        for output in ("None", "nan", "-1", "361"):
            with (
                self.subTest(output=output),
                patch.object(sender.subprocess, "run", autospec=True) as run,
            ):
                run.side_effect = [
                    Mock(stdout="/tools/pybooklid/1.0.0\n"),
                    Mock(stdout=output),
                ]
                with self.assertRaises(RuntimeError):
                    sender.read_lid_angle()

    def test_routes_one_channel_using_original_presence_thresholds(self) -> None:
        cases = [
            (0, False, 90, False),
            (300, False, 90, False),
            (301, False, 90, True),
            (0, True, 90, True),
            (0, False, 31, True),
            (0, False, 69.9, True),
            (0, False, 70, False),
        ]
        for idle, screen, angle, phone in cases:
            with (
                self.subTest(idle=idle, screen=screen, angle=angle),
                patch.object(sender, "read_idle_seconds", return_value=idle),
                patch.object(sender, "screensaver_active", return_value=screen),
                patch.object(sender, "read_lid_angle", return_value=angle),
                patch.object(
                    sender, "send_ntfy", autospec=True, return_value=True
                ) as push,
                patch.object(sender.subprocess, "run", autospec=True) as desktop,
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                desktop.return_value.returncode = 0
                self.assertTrue(sender.deliver("Herdr test", "Test"))
                self.assertEqual(push.call_count, int(phone))
                self.assertEqual(desktop.call_count, int(not phone))
                diagnostic = json.loads(output.getvalue())
                self.assertEqual(diagnostic["channel"], "phone" if phone else "desktop")
                self.assertEqual(diagnostic["lid_closed"], angle < 70)
                self.assertEqual(diagnostic["lid_angle"], angle)

    def test_delivery_failure_stays_on_selected_channel(self) -> None:
        for closed in (False, True):
            with (
                self.subTest(closed=closed),
                patch.object(sender, "read_idle_seconds", return_value=0),
                patch.object(sender, "screensaver_active", return_value=False),
                patch.object(
                    sender, "read_lid_angle", return_value=31 if closed else 90
                ),
                patch.object(
                    sender, "send_ntfy", autospec=True, return_value=False
                ) as push,
                patch.object(sender.subprocess, "run", autospec=True) as desktop,
                contextlib.redirect_stdout(io.StringIO()) as output,
            ):
                desktop.return_value.returncode = 1
                self.assertFalse(sender.deliver("Herdr test", "Test"))
                self.assertEqual(push.call_count, int(closed))
                self.assertEqual(desktop.call_count, int(not closed))
                self.assertFalse(json.loads(output.getvalue())["accepted"])


if __name__ == "__main__":
    unittest.main()
