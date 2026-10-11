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
sys.path.insert(0,str(pathlib.Path(os.environ["TEST_DRIVER"]).parent))
import driver
cwd = pathlib.Path.cwd()
ap = cwd / "docs/dev/project-management/autopilot"
path = ap / "state.json"
prompt = sys.stdin.read()
with (ap / "invocations.jsonl").open("a") as f:
    f.write(json.dumps({"pid":os.getpid(),"argv":sys.argv,"prompt":prompt})+"\n")
if "--print" in sys.argv:
    print(json.dumps({"type":"result","is_error":False,"result":prompt}))
    raise SystemExit(0)
current = state.load(path)[0]
phase = current["next_phase"]
if phase == "build":
    state.transaction(path, lambda s: transitions.apply(s,"tasks_done"))
elif phase == "review":
    evidence = ap / "implementation.jsonl"
    evidence.write_text(json.dumps({"model":"gpt-6.1-sol"}))
    reports = ap / "reports"
    reports.mkdir(exist_ok=True)
    audit = {"snapshot":driver.implementation_snapshot(current),"fingerprint":driver.implementation_fingerprint(current),"evidence":[{"task":"1","role":"implementation","model":"gpt-6.1-sol","path":str(evidence.relative_to(cwd)),"line":1,"sha256":hashlib.sha256(evidence.read_bytes()).hexdigest()}]}
    (reports / "00001-demo-implementation-models.json").write_text(json.dumps(audit))
    parts = ["provider_review_guard: satisfied", "codex_rung_guard: not fired"]
    for lens in ("alice", "blake", "bob"):
        prompt_path = ap / (lens+"-prompt.md")
        prompt_path.write_text("\n".join(rule+": pass" for rule in driver.review_rules(lens)))
        output = ap / (lens+".md")
        subprocess.run([sys.executable,os.environ["TEST_DRIVER"],"--cd",str(cwd),"reviewer","--lens",lens,"-f",str(prompt_path),"-o",str(output)],check=True,stdout=subprocess.DEVNULL)
        parts += ["autocodex_"+lens+"_anthropic_receipt: " + str(output) + ".receipt.json"]
    for lens in ("alice", "blake", "bob"):
        parts += ["## " + lens.title(), (ap/(lens+".md")).read_text()]
    parts += ["Verdict: converged","Tests: 1 passed (synthetic fixture)"]
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
    ap = repo / "docs/dev/project-management/autopilot"
    ap.mkdir(parents=True)
    (ap / "state.json").write_text(
        json.dumps(
            {
                "phase": "build",
                "next_phase": "build",
                "prd": "00001-demo.md",
                "cycle": 1,
                "tasks": [
                    {
                        "id": "1",
                        "status": "completed",
                        "attempts": [{"actual_model": "gpt-6.1-sol"}],
                    }
                ],
            }
        )
    )
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
    assert "gpt-6.1-sol/low" in result.stdout
    assert "gpt-6.1-sol/low" in result.stdout
    assert "claude-sonnet" not in result.stdout
    assert "claude-opus" not in result.stdout
    launches = [json.loads(line) for line in (ap / "invocations.jsonl").read_text().splitlines()]
    assert len(launches) == 6
    assert len({launch["pid"] for launch in launches}) == 6
    assert "gpt-6.1-sol" in launches[0]["argv"]
    assert "gpt-6.1-sol" in launches[1]["argv"]
    assert "opus" in launches[2]["argv"]
    assert "--print" in launches[2]["argv"]
    assert "gpt-6.1-sol" in launches[5]["argv"]
    assert not (ap / "state.json").exists()
    archived = list((ap / "reports").glob("autocodex-*-state-final.json"))
    assert len(archived) == 1
    assert json.loads(archived[0].read_text())["next_phase"] == ""
    from adapter import review_gap

    completed = json.loads(archived[0].read_text())
    assert review_gap(completed, driver.skill_root(), repo, 1) is None
    completed.update(phase="review", next_phase="review", cycle=2)
    completed["tasks"].append({"id": "2", "attempts": []})
    assert review_gap(completed, driver.skill_root(), repo, 1) is None
    completed["phase"] = "done"
    assert "implementation changed" in review_gap(completed, driver.skill_root(), repo, 1)

    assert len(list((ap / "autocodex-sessions").glob("*.jsonl"))) == 3
    metrics = [
        json.loads(line) for line in (ap / "autocodex-metrics.jsonl").read_text().splitlines()
    ]
    assert [row["effort"] for row in metrics] == ["low", "low", "low"]
    assert [row["signal"] for row in metrics] == ["continue", "continue", "done"]
    assert len(list((tmp_path / "registry").glob("*.json"))) == 0


def test_fast_track_handoff_scope_runs_once_without_task_state(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    handoff = repo / "docs/dev/project-management/plans/fast-track-handoffs/00004/rework-11.md"
    handoff.parent.mkdir(parents=True)
    handoff.write_text("# Standalone repair handoff\n")
    fake = tmp_path / "fake-codex"
    fake.write_text(
        f"#!{sys.executable}\n"
        "import json,sys\n"
        "sys.stdin.read()\n"
        "print(json.dumps({'type':'turn.completed'}))\n"
    )
    fake.chmod(0o700)
    sysctl = tmp_path / "sysctl"
    sysctl.write_text("#!/bin/sh\nprintf '1\\n'\n")
    sysctl.chmod(0o700)
    env = dict(
        os.environ,
        AUTOCODEX_BIN=str(fake),
        AUTOCODEX_SKILL_ROOT=str(driver.skill_root()),
        _AUTOPILOT_LOOPS_DIR=str(tmp_path / "registry"),
        PATH=f"{tmp_path}:{os.environ['PATH']}",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(driver.HERE / "driver.py"),
            "--cd",
            str(repo),
            "--scope",
            str(handoff),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "fast-track handoff detected" in result.stdout
    assert (
        len(
            list(
                (repo / "docs/dev/project-management/autopilot/autocodex-sessions").glob("*.jsonl")
            )
        )
        == 1
    )
    assert not (repo / "docs/dev/project-management/autopilot/state.json").exists()
    assert "autoclaude:" not in result.stdout + result.stderr
