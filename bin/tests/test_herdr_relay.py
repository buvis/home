"""Checks for ~/bin/herdr-relay: only display-only report methods reach herdr, nothing else.

Run: /opt/homebrew/bin/python3 -m unittest discover -s ~/bin/tests -t ~/bin/tests -p 'test_herdr_relay.py'
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import socket
import socketserver
import sys
import tempfile
import threading
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

RELAY = Path(__file__).resolve().parent.parent / "herdr-relay"
_spec = importlib.util.spec_from_loader(
    "herdr_relay", SourceFileLoader("herdr_relay", str(RELAY))
)
relay = importlib.util.module_from_spec(_spec)
sys.modules["herdr_relay"] = relay
_spec.loader.exec_module(relay)


class FakeHerdr(socketserver.ThreadingUnixStreamServer):
    """Records every request line it receives and answers each with an empty result."""

    daemon_threads = True

    def __init__(self, path: Path) -> None:
        self.seen: list[dict] = []
        server = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self) -> None:
                for line in self.rfile:
                    req = json.loads(line)
                    server.seen.append(req)
                    self.wfile.write(
                        json.dumps({"id": req["id"], "result": {}}).encode() + b"\n"
                    )

        super().__init__(str(path), Handler)


class RelayCase(unittest.TestCase):
    def setUp(self) -> None:
        # AF_UNIX paths cap at 104 bytes on macOS, so keep the temp dir short.
        self.tmp = Path(tempfile.mkdtemp(prefix="hr-", dir="/tmp"))
        self.herdr = FakeHerdr(self.tmp / "h.sock")
        self.relay = relay.Relay(self.tmp / "r" / "r.sock", self.tmp / "h.sock")
        for server in (self.herdr, self.relay):
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def send(self, payload: bytes) -> list[dict]:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(5)
            conn.connect(str(self.tmp / "r" / "r.sock"))
            conn.sendall(payload)
            conn.shutdown(socket.SHUT_WR)
            return [json.loads(line) for line in conn.makefile("rb")]

    def test_report_methods_reach_herdr_with_their_params(self) -> None:
        for method in sorted(relay.ALLOWED):
            reply = self.send(
                json.dumps(
                    {"id": method, "method": method, "params": {"pane_id": "p1"}}
                ).encode()
                + b"\n"
            )
            self.assertEqual(reply, [{"id": method, "result": {}}])
        self.assertEqual(
            [(r["method"], r["params"]) for r in self.herdr.seen],
            [(m, {"pane_id": "p1"}) for m in sorted(relay.ALLOWED)],
        )

    def test_pane_control_never_reaches_herdr(self) -> None:
        for method in (
            "pane.run",
            "pane.send_text",
            "pane.send_keys",
            "pane.split",
            "pane.list",
            "events.subscribe",
        ):
            reply = self.send(
                json.dumps({"id": "x", "method": method, "params": {}}).encode() + b"\n"
            )
            self.assertEqual(reply[0]["error"]["code"], "forbidden", method)
        self.assertEqual(self.herdr.seen, [])

    def test_each_line_is_judged_on_its_own(self) -> None:
        ok = json.dumps({"id": "a", "method": "pane.report_metadata", "params": {}})
        bad = json.dumps({"id": "b", "method": "pane.run", "params": {"command": "id"}})
        replies = self.send(f"{ok}\n{bad}\n".encode())
        self.assertEqual(
            [r.get("error", {}).get("code") for r in replies], [None, "forbidden"]
        )
        self.assertEqual(
            [r["method"] for r in self.herdr.seen], ["pane.report_metadata"]
        )

    def test_extra_fields_are_dropped_before_forwarding(self) -> None:
        self.send(
            json.dumps(
                {
                    "id": "a",
                    "method": "pane.report_agent",
                    "params": {},
                    "method2": "pane.run",
                }
            ).encode()
            + b"\n"
        )
        self.assertEqual(
            self.herdr.seen, [{"id": "a", "method": "pane.report_agent", "params": {}}]
        )

    def test_garbage_is_refused_without_forwarding(self) -> None:
        replies = self.send(b"not json\n[1, 2]\n")
        self.assertEqual(
            [r["error"]["code"] for r in replies], ["invalid_request", "forbidden"]
        )
        self.assertEqual(self.herdr.seen, [])

    def test_herdr_down_is_reported_not_raised(self) -> None:
        self.herdr.shutdown()
        self.herdr.server_close()
        (self.tmp / "h.sock").unlink()
        reply = self.send(
            json.dumps(
                {"id": "a", "method": "pane.report_agent", "params": {}}
            ).encode()
            + b"\n"
        )
        self.assertEqual(reply[0]["error"]["code"], "upstream_unavailable")


if __name__ == "__main__":
    unittest.main()
