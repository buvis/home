"""Checks for ~/bin/warrant: no approval means no execution, and an approval binds to one exact operation.

Run: /opt/homebrew/bin/python3 -m unittest discover -s ~/bin/tests -t ~/bin/tests -p test_warrant.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch

WARRANT = Path(__file__).resolve().parent.parent / "warrant"
_spec = importlib.util.spec_from_loader(
    "warrant",
    SourceFileLoader("warrant", str(WARRANT)),
)
warrant = importlib.util.module_from_spec(_spec)
sys.modules["warrant"] = warrant
_spec.loader.exec_module(warrant)

PIN = "4821"


def quiet(_line: str) -> None:
    pass


def no_ping(_req: dict) -> bool:
    return True


class WarrantCase(unittest.TestCase):
    def setUp(self) -> None:
        cheap_kdf = patch.object(warrant, "SCRYPT", {**warrant.SCRYPT, "n": 2**10})
        cheap_kdf.start()
        self.addCleanup(cheap_kdf.stop)
        self.tmp = Path(tempfile.mkdtemp(prefix="warrant-test-"))
        self.agentw = self.tmp / "agentw"
        self.agentw.mkdir()
        self.cfg = self.tmp / "cfg"
        self.cfg.mkdir(mode=0o700)
        config = {
            "agent_writable_roots": [str(self.agentw)],
            "agent_writable_globs": [str(self.tmp / "gl" / "claude*")],
            "exec_path": "/usr/bin:/bin",
            "inherit_env": [],
            "request_ttl_sec": 900,
            "exec_timeout_sec": 30,
        }
        self.site = warrant.Site(self.tmp / "spool", self.cfg, config)
        warrant.set_pin(self.site, lambda _prompt: PIN)
        self.marker = self.tmp / "ran"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def touch_cmd(self, marker: Path | None = None) -> list[str]:
        return ["sh", "-c", f"touch {marker or self.marker}"]

    def submit(self, argv: list[str], **override: object) -> tuple[Path, dict]:
        req = warrant.build_request(argv, self.tmp, {}, "test")
        req.update(override)
        return warrant.submit(self.site, req), req

    def request(self, argv: list[str], **kwargs: object) -> int:
        kwargs.setdefault("timeout", 0.3)
        return warrant.request(
            self.site,
            argv,
            self.tmp,
            {},
            "t",
            out=quiet,
            poll=0.05,
            notify=no_ping,
            **kwargs,
        )

    def approve(self, path: Path, secret: str = PIN, **kwargs: object) -> int:
        return warrant.approve_one(
            self.site,
            path,
            lambda _prompt: secret,
            quiet,
            **kwargs,
        )

    def result(self, rid: str) -> dict:
        return json.loads((self.site.results / f"{rid}.json").read_text())

    def decisions(self) -> list[str]:
        if not self.site.ledger.exists():
            return []
        return [
            json.loads(line)["decision"]
            for line in self.site.ledger.read_text().splitlines()
        ]

    def last_entry(self) -> dict:
        return json.loads(self.site.ledger.read_text().splitlines()[-1])

    def pending(self) -> list[Path]:
        return list(self.site.requests.glob("*.json"))

    # --- no approval, no execution ---

    def test_no_verdict_means_no_execution_and_request_stays_pending(self) -> None:
        self.assertEqual(self.request(self.touch_cmd()), warrant.EXIT_NO_VERDICT)
        self.assertFalse(self.marker.exists())
        self.assertEqual(len(self.pending()), 1)

    def test_empty_pin_rejects_without_executing(self) -> None:
        path, req = self.submit(self.touch_cmd())
        self.assertEqual(self.approve(path, secret=""), 0)
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.result(req["id"])["status"], "rejected")
        self.assertEqual(self.decisions(), ["attempt", "rejected"])

    def test_pin_mismatch_is_logged_and_does_not_block_the_id(self) -> None:
        path, req = self.submit(self.touch_cmd())
        with patch.object(warrant.time, "sleep"):
            self.assertEqual(self.approve(path, secret="0000"), 2)
        self.assertFalse(self.marker.exists())
        self.assertTrue(path.exists())
        self.assertFalse((self.site.results / f"{req['id']}.json").exists())
        self.assertEqual(self.decisions(), ["attempt", "mismatch"])
        self.assertEqual(self.approve(path), 0)
        self.assertTrue(self.marker.exists())
        self.assertEqual(self.decisions()[-1], "executed")

    def test_three_pin_misses_lock_approvals_for_the_window(self) -> None:
        path, _ = self.submit(self.touch_cmd())
        with patch.object(warrant.time, "sleep"):
            for _ in range(3):
                self.assertEqual(self.approve(path, secret="0000"), 2)
        asked: list[str] = []

        def spy(prompt: str) -> str:
            asked.append(prompt)
            return PIN

        self.assertEqual(warrant.approve_one(self.site, path, spy, quiet), 2)
        self.assertEqual(asked, [])
        self.assertFalse(self.marker.exists())
        later = time.time() + warrant.LOCKOUT_WINDOW_SEC + 1
        self.assertEqual(self.approve(path, now=lambda: later), 0)
        self.assertTrue(self.marker.exists())

    def test_guess_is_not_checked_when_the_ledger_cannot_be_written(self) -> None:
        path, _ = self.submit(self.touch_cmd())
        self.cfg.chmod(0o500)
        self.addCleanup(self.cfg.chmod, 0o700)
        asked: list[str] = []

        def spy(prompt: str) -> str:
            asked.append(prompt)
            return PIN

        self.assertEqual(warrant.approve_one(self.site, path, spy, quiet), 2)
        self.assertEqual(asked, [])
        self.assertFalse(self.marker.exists())
        self.assertTrue(path.exists())

    def test_expired_request_is_refused(self) -> None:
        path, req = self.submit(self.touch_cmd(), created=time.time() - 901)
        self.assertEqual(self.approve(path), warrant.EXIT_REFUSED)
        self.assertFalse(self.marker.exists())
        self.assertIn("expired", self.result(req["id"])["reason"])

    def test_replayed_id_is_refused(self) -> None:
        path, req = self.submit(self.touch_cmd())
        self.assertEqual(self.approve(path), 0)
        self.marker.unlink()
        again = warrant.submit(self.site, req)
        self.assertEqual(self.approve(again), warrant.EXIT_REFUSED)
        self.assertFalse(self.marker.exists())
        self.assertIn("already decided", self.result(req["id"])["reason"])

    # --- the approval binds to one exact operation ---

    def test_pin_executes_exact_argv_and_records_ledger(self) -> None:
        path, req = self.submit(
            ["sh", "-c", f"touch {self.marker}; echo out; echo err >&2; exit 3"],
        )
        self.assertEqual(self.approve(path), 0)
        self.assertTrue(self.marker.exists())
        res = self.result(req["id"])
        self.assertEqual(
            (res["status"], res["exit"], res["stdout"], res["stderr"]),
            ("executed", 3, "out\n", "err\n"),
        )
        self.assertFalse(path.exists())
        entry = self.last_entry()
        self.assertEqual(
            (entry["decision"], entry["exit"], entry["argv"]),
            ("executed", 3, req["argv"]),
        )

    def test_requester_receives_verdict_end_to_end(self) -> None:
        codes: list[int] = []
        worker = threading.Thread(
            target=lambda: codes.append(
                self.request(["sh", "-c", "exit 7"], timeout=10),
            ),
        )
        worker.start()
        deadline = time.time() + 5
        while not self.pending() and time.time() < deadline:
            time.sleep(0.02)
        [path] = self.pending()
        self.assertEqual(self.approve(path), 0)
        worker.join(5)
        self.assertEqual(codes, [7])

    def test_wait_reattaches_to_a_pending_request(self) -> None:
        self.assertEqual(self.request(["sh", "-c", "exit 5"], wait=False), 0)
        [path] = self.pending()
        self.assertEqual(self.approve(path), 0)
        code = warrant.wait_for(self.site, path.stem, timeout=1, out=quiet, poll=0.05)
        self.assertEqual(code, 5)

    def test_wait_on_unknown_request_fails(self) -> None:
        code = warrant.wait_for(self.site, "0" * 32, timeout=1, out=quiet, poll=0.05)
        self.assertEqual(code, 2)

    def test_request_file_edited_after_load_is_ignored(self) -> None:
        path, req = self.submit(self.touch_cmd())
        other = self.tmp / "other"

        def swap(_prompt: str) -> str:
            path.write_text(json.dumps({**req, "argv": self.touch_cmd(other)}))
            return PIN

        self.assertEqual(warrant.approve_one(self.site, path, swap, quiet), 0)
        self.assertTrue(self.marker.exists())
        self.assertFalse(other.exists())

    def test_file_argument_changed_after_review_is_refused(self) -> None:
        note = self.agentw / "note.txt"
        note.write_text("one")
        path, req = self.submit(["cat", str(note)])

        def tamper(_prompt: str) -> str:
            note.write_text("two")
            return PIN

        self.assertEqual(
            warrant.approve_one(self.site, path, tamper, quiet),
            warrant.EXIT_REFUSED,
        )
        res = self.result(req["id"])
        self.assertEqual(res["status"], "refused")
        self.assertIn("changed after review", res["reason"])

    def test_file_argument_unchanged_executes(self) -> None:
        note = self.agentw / "note.txt"
        note.write_text("one")
        path, req = self.submit(["cat", str(note)])
        self.assertEqual(self.approve(path), 0)
        self.assertEqual(self.result(req["id"])["stdout"], "one")

    def test_cwd_symlink_repointed_after_review_runs_the_reviewed_dir(self) -> None:
        evil_ran = self.tmp / "evil-ran"
        for name, target in (("good", self.marker), ("bad", evil_ran)):
            (self.agentw / name).mkdir()
            (self.agentw / name / "run.sh").write_text(f"touch {target}\n")
        cwd = self.agentw / "cwd"
        cwd.symlink_to(self.agentw / "good")
        path, req = self.submit(["sh", "run.sh"], cwd=str(cwd))

        def repoint(_prompt: str) -> str:
            cwd.unlink()
            cwd.symlink_to(self.agentw / "bad")
            return PIN

        self.assertEqual(warrant.approve_one(self.site, path, repoint, quiet), 0)
        self.assertTrue(self.marker.exists())
        self.assertFalse(evil_ran.exists())

    def test_cwd_component_swapped_after_review_is_refused(self) -> None:
        evil_ran = self.tmp / "evil-ran"
        real = self.agentw / "real"
        real.mkdir()
        (real / "run.sh").write_text(f"touch {self.marker}\n")
        bad = self.agentw / "bad"
        bad.mkdir()
        (bad / "run.sh").write_text(f"touch {evil_ran}\n")
        path, req = self.submit(["sh", "run.sh"], cwd=str(real))

        def swap(_prompt: str) -> str:
            real.rename(self.agentw / "moved")
            real.symlink_to(bad)
            return PIN

        self.assertEqual(
            warrant.approve_one(self.site, path, swap, quiet),
            warrant.EXIT_REFUSED,
        )
        self.assertFalse(evil_ran.exists())
        self.assertIn("changed after review", self.result(req["id"])["reason"])

    def test_file_argument_created_after_review_is_refused(self) -> None:
        evil_ran = self.tmp / "evil-ran"
        path, req = self.submit(["sh", "late.sh"], cwd=str(self.agentw))

        def plant(_prompt: str) -> str:
            (self.agentw / "late.sh").write_text(f"touch {evil_ran}\n")
            return PIN

        self.assertEqual(
            warrant.approve_one(self.site, path, plant, quiet),
            warrant.EXIT_REFUSED,
        )
        self.assertFalse(evil_ran.exists())
        self.assertIn("changed after review", self.result(req["id"])["reason"])

    def test_small_agent_writable_file_head_is_shown(self) -> None:
        shown = self.agentw / "patch.diff"
        shown.write_text("line one\nline two\n")
        hidden = self.tmp / "trusted.txt"
        hidden.write_text("secret sauce\n")
        path, _ = self.submit(["cat", str(shown), str(hidden)])
        lines: list[str] = []
        warrant.approve_one(self.site, path, lambda _prompt: "", lines.append)
        text = "\n".join(lines)
        self.assertIn("| line one", text)
        self.assertIn("AGENT-WRITABLE", text)
        self.assertNotIn("secret sauce", text)

    def test_executable_in_agent_writable_root_is_refused(self) -> None:
        evil = self.agentw / "evil.sh"
        evil.write_text(f"#!/bin/sh\ntouch {self.marker}\n")
        evil.chmod(0o755)
        path, req = self.submit([str(evil)])
        self.assertEqual(self.approve(path), warrant.EXIT_REFUSED)
        self.assertFalse(self.marker.exists())
        self.assertIn("agent-writable", self.result(req["id"])["reason"])

    def test_executable_matching_agent_writable_glob_is_refused(self) -> None:
        glob_dir = self.tmp / "gl"
        glob_dir.mkdir()
        exe = glob_dir / "claude-x"
        exe.write_text(f"#!/bin/sh\ntouch {self.marker}\n")
        exe.chmod(0o755)
        path, _ = self.submit([str(exe)])
        self.assertEqual(self.approve(path), warrant.EXIT_REFUSED)
        self.assertFalse(self.marker.exists())

    def test_symlink_in_agent_writable_root_runs_the_reviewed_target(self) -> None:
        link = self.agentw / "sh"
        link.symlink_to("/bin/sh")
        evil = self.agentw / "evil.sh"
        evil.write_text(f"#!/bin/sh\ntouch {self.tmp / 'evil-ran'}\n")
        evil.chmod(0o755)
        path, _ = self.submit([str(link), "-c", f"touch {self.marker}"])

        def swap(_prompt: str) -> str:
            link.unlink()
            link.symlink_to(evil)
            return PIN

        self.assertEqual(warrant.approve_one(self.site, path, swap, quiet), 0)
        self.assertTrue(self.marker.exists())
        self.assertFalse((self.tmp / "evil-ran").exists())

    def test_loader_env_keys_are_refused(self) -> None:
        path, req = self.submit(
            self.touch_cmd(),
            env={"DYLD_INSERT_LIBRARIES": "/x.dylib"},
        )
        self.assertEqual(self.approve(path), warrant.EXIT_REFUSED)
        self.assertFalse(self.marker.exists())
        self.assertIn("DYLD_INSERT_LIBRARIES", self.result(req["id"])["reason"])

    def test_command_env_is_minimal_plus_declared(self) -> None:
        path, req = self.submit(["env"], env={"WARRANT_DECLARED": "yes"})
        with patch.dict(os.environ, {"WARRANT_LEAK": "1"}):
            self.assertEqual(self.approve(path), 0)
        out = self.result(req["id"])["stdout"]
        self.assertIn("WARRANT_DECLARED=yes", out)
        self.assertNotIn("WARRANT_LEAK", out)
        self.assertIn("PATH=/usr/bin:/bin\n", out)

    # --- the human gets told ---

    def test_submit_pings_the_notify_hook(self) -> None:
        hook = self.tmp / "notify.py"
        hook.write_text("")
        req = warrant.build_request(["git", "push"], self.tmp, {}, "ship it")
        with (
            patch.object(warrant, "NOTIFY_HOOK", hook),
            patch.object(warrant.subprocess, "run") as run,
        ):
            run.return_value.returncode = 0
            self.assertTrue(warrant.notify_human(req))
        argv = run.call_args.args[0]
        self.assertEqual(argv[1:3], [str(hook), "--send"])
        self.assertIn(req["id"], argv[4])
        self.assertIn("git push", argv[4])
        self.assertIn("ship it", argv[4])

    def test_missing_notify_hook_reports_false(self) -> None:
        req = warrant.build_request(["true"], self.tmp, {}, "")
        with patch.object(warrant, "NOTIFY_HOOK", self.tmp / "absent.py"):
            self.assertFalse(warrant.notify_human(req))

    # --- trusted components stay outside agent-writable paths ---

    def test_preflight_refuses_agent_writable_config_dir(self) -> None:
        inside = warrant.Site(self.site.spool, self.agentw / "cfg", self.site.config)
        with self.assertRaises(warrant.Refused):
            warrant.preflight(inside)

    def test_preflight_accepts_this_layout(self) -> None:
        warrant.preflight(self.site)

    def test_init_accepts_only_four_to_eight_digits(self) -> None:
        fresh = warrant.Site(self.site.spool, self.tmp / "cfg2", self.site.config)
        for bad in ("123", "123456789", "12a4", "abcd", "٤٨٢١"):
            with self.assertRaises(ValueError):
                warrant.set_pin(fresh, lambda _prompt, bad=bad: bad)
        self.assertFalse(fresh.passphrase_file.exists())
        warrant.set_pin(fresh, lambda _prompt: "12345678")
        self.assertTrue(warrant.verify_pin(fresh, "12345678"))
        self.assertFalse(warrant.verify_pin(fresh, "12345679"))

    def test_spool_must_be_private_and_owned(self) -> None:
        self.site.spool.mkdir(mode=0o755)
        self.site.spool.chmod(0o755)
        with self.assertRaises(warrant.Refused):
            warrant.submit(
                self.site,
                warrant.build_request(["true"], self.tmp, {}, "t"),
            )


if __name__ == "__main__":
    unittest.main()
