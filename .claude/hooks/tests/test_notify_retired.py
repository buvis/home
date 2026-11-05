"""Stale notification-hook registrations must be inert; Herdr owns alerts."""

import io
import json
import unittest
from unittest.mock import patch

import notify


class RetiredHookTests(unittest.TestCase):
    def test_stale_hook_events_have_no_side_effects(self) -> None:
        for event in ("Stop", "Notification"):
            with (
                self.subTest(event=event),
                patch("sys.argv", ["notify.py"]),
                patch("sys.stdin", io.StringIO(json.dumps({"hook_event_name": event}))),
                patch("notify.log_line", autospec=True) as log,
                patch("notify.send_ntfy", autospec=True) as phone,
                patch("notify.show_desktop_notification", autospec=True) as desktop,
                patch("notify.subprocess.run", autospec=True) as process,
            ):
                notify.main()
                log.assert_not_called()
                phone.assert_not_called()
                desktop.assert_not_called()
                process.assert_not_called()

    def test_stale_dispatcher_route_is_inert(self) -> None:
        with (
            patch("sys.argv", ["dispatch.py", "stop"]),
            patch("notify.log_line", autospec=True) as log,
            patch("notify.send_ntfy", autospec=True) as phone,
            patch("notify.show_desktop_notification", autospec=True) as desktop,
            patch("notify.subprocess.run", autospec=True) as process,
        ):
            self.assertEqual(notify.run({"hook_event_name": "Stop"}), (0, "", ""))
            log.assert_not_called()
            phone.assert_not_called()
            desktop.assert_not_called()
            process.assert_not_called()
