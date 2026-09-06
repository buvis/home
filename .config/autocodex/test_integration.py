from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import driver

FAKE = r"""
import hashlib,json,os,pathlib,re,subprocess,sys,time
root = pathlib.Path(os.environ["AUTOCODEX_SKILL_ROOT"])
sys.path.insert(0,str(root))
from cli import state, transitions
cwd = pathlib.Path.cwd()
ap = cwd / "dev/local/autopilot"
path = ap / "state.json"
prompt = sys.stdin.read()
with (ap / "invocations.jsonl").open("a") as f:
    f.write(json.dumps({"pid":os.getpid(),"argv":sys.argv,"prompt":prompt})+"\n")
if "--print" in sys.argv:
    print(json.dumps({"type":"result","is_error":False,"result":"\n".join(f"D{n}: pass" for n in range(1,6))}))
    raise SystemExit(0)
current = state.load(path)[0]
phase = current["next_phase"]
if phase == "build":
    state.transaction(path, lambda s: transitions.apply(s,"tasks_done"))
elif phase == "review":
    prompt_path = ap / "bob-prompt.md"
    prompt_path.write_text("synthetic review fixture")
    output = ap / "bob.md"
    subprocess.run([sys.executable,os.environ["TEST_DRIVER"],"--cd",str(cwd),"reviewer","-f",str(prompt_path),"-o",str(output)],check=True,stdout=subprocess.DEVNULL)
    parts = ["autocodex_bob_receipt: " + str(output) + ".receipt.json", "codex_rung_guard: not fired"]
    for name, rubric in [("Alice",root.parent / "review-work-completion/references/rubric.md"),("Blake",root.parent / "review-blindly/references/rubric.md")]:
        parts += ["## " + name]
        parts += [rule + ": pass" for rule in re.findall(r"^([RB]\d+):",rubric.read_text(),re.M)]
    parts += ["## Bob",output.read_text(),"Verdict: converged","Tests: 1 passed (synthetic fixture)"]
    review_path = ap / "review.md"
    review_path.write_text("\n".join(parts))
    doubts=[{"rule_id":f"D{n}","verdict":"pass"} for n in range(1,6)]
    state.transaction(path,lambda s:transitions.apply({**s,"doubts_rubric_verdicts":doubts,"review_cycles":[{"cycle":1,"review_file":str(review_path)}]},"converged"))
elif phase == "done":
    state.transaction(path,lambda s:transitions.apply(s,"drained"))
print(json.dumps({"type":"thread.started","thread_id":str(os.getpid())}))
print(json.dumps({"type":"turn.completed","usage":{"output_tokens":1}}))
"""


def test_cli_runs_fresh_phases_and_swaps_external_reviewer(tmp_path: Path) -> None:
    repo = tmp_path / "repo with spaces"
    ap = repo / "dev/local/autopilot"
    ap.mkdir(parents=True)
    (ap / "state.json").write_text(json.dumps({"phase": "build", "next_phase": "build"}))
    fake = tmp_path / "fake-agent"
    fake.write_text(f"#!{sys.executable}\n" + FAKE)
    fake.chmod(0o700)
    sysctl = tmp_path / "sysctl"
    sysctl.write_text("#!/bin/sh\nprintf '1\\n'\n")
    sysctl.chmod(0o700)
    env = dict(
        os.environ,
        AUTOCODEX_BIN=str(fake),
        AUTOCODEX_CLAUDE_BIN=str(fake),
        AUTOCODEX_SKILL_ROOT=str(driver.skill_root()),
        TEST_DRIVER=str(driver.HERE / "driver.py"),
        _AUTOPILOT_LOOPS_DIR=str(tmp_path / "registry"),
        PATH=f"{tmp_path}:{os.environ['PATH']}",
    )
    result = subprocess.run(
        [sys.executable, str(driver.HERE / "driver.py"), "--cd", str(repo)],
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    launches = [json.loads(line) for line in (ap / "invocations.jsonl").read_text().splitlines()]
    assert len(launches) == 4
    assert len({launch["pid"] for launch in launches}) == 4
    assert "gpt-5.6-sol" in launches[0]["argv"]
    assert "gpt-6-astra" in launches[1]["argv"]
    assert "opus" in launches[2]["argv"]
    assert "--print" in launches[2]["argv"]
    assert "gpt-5.6-sol" in launches[3]["argv"]
    assert not (ap / "state.json").exists()
    archived = list((ap / "reports").glob("autocodex-*-state-final.json"))
    assert len(archived) == 1
    assert json.loads(archived[0].read_text())["next_phase"] == ""
    assert len(list((ap / "autocodex-sessions").glob("*.jsonl"))) == 3
    assert len(list((tmp_path / "registry").glob("*.json"))) == 0
