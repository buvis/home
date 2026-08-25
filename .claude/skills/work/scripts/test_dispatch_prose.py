"""Tests binding the live text of ~/.claude/skills/work/SKILL.md — Suite 3 of
the PRD 00093 test debt.

PRD 00093 shipped four prose-only fixes to the dispatch steps (each persona
rendered through render_prompt.py, no dispatch step authoring prompt text by
hand, task-authored prose always crossing the shell via --set-file) with no
test at all, so a revert of that prose would go undetected with every other
suite green. Mirrors run-autopilot/scripts/test_fablectl.py's pattern for
pinning a skill file's prose: resolve the path relative to this file, read it
once, and assert on short, reword-resistant substrings (a filename, a flag
spelling), each with a failure message naming what drifted and where to look.
"""

from __future__ import annotations

from pathlib import Path

_SKILL_MD = Path(__file__).resolve().parent.parent / "SKILL.md"
_TEXT = _SKILL_MD.read_text()


def test_tess_dispatch_is_rendered_through_render_prompt_py() -> None:
    # Step 2.7 must dispatch Tess via render_prompt.py naming tess-prompt.md,
    # never author her prompt text inline.
    needle = "render_prompt.py ~/.claude/skills/work/references/tess-prompt.md"

    assert needle in _TEXT, (
        f"{_SKILL_MD}: expected the Tess dispatch (step 2.7) to invoke "
        f"render_prompt.py naming tess-prompt.md — did not find {needle!r}. "
        "The Tess persona render call appears to have drifted or been removed."
    )


def test_ivan_dispatch_is_rendered_through_render_prompt_py() -> None:
    # Step 3 (and its step-5.5/7 retries) must dispatch Ivan via
    # render_prompt.py naming agents/ivan.md, never author his prompt by hand.
    needle = "render_prompt.py ~/.claude/agents/ivan.md"

    assert needle in _TEXT, (
        f"{_SKILL_MD}: expected an Ivan dispatch to invoke render_prompt.py "
        f"naming agents/ivan.md — did not find {needle!r}. The Ivan persona "
        "render call appears to have drifted or been removed."
    )


def test_pat_dispatch_is_rendered_through_render_prompt_py() -> None:
    # Step 5.7's per-task reviewer must dispatch Pat via render_prompt.py
    # naming agents/pat.md, never author his prompt by hand.
    needle = "render_prompt.py ~/.claude/agents/pat.md"

    assert needle in _TEXT, (
        f"{_SKILL_MD}: expected the step-5.7 reviewer dispatch to invoke "
        f"render_prompt.py naming agents/pat.md — did not find {needle!r}. "
        "The Pat persona render call appears to have drifted or been removed."
    )


def test_no_dispatch_step_instructs_authoring_the_code_quality_rules_block() -> None:
    # No dispatch step may tell the orchestrator to compose Ivan's
    # code-quality rules itself — the block is permanent in ivan.md.
    phrase = "code-quality rules block from"

    assert phrase not in _TEXT, (
        f"{_SKILL_MD}: found the phrase {phrase!r} — this instructs the "
        "orchestrator to author prompt text itself instead of relying on "
        "ivan.md's permanent code-quality rules block. PRD 00093 removed "
        "this phrasing; it has regressed."
    )


def test_task_authored_prose_flags_never_cross_the_shell_via_set() -> None:
    # Task-authored prose (subject, description, acceptance criteria, file
    # paths) must always cross render_prompt.py via --set-file (a path), never
    # --set (a shell word) — backticks or $() in task text would otherwise be
    # expanded by the shell before render_prompt.py ever sees them.
    banned_flags = (
        "--set TASK_SUBJECT=",
        "--set TASK_DESCRIPTION=",
        "--set TASK_ACCEPTANCE_CRITERIA=",
        "--set FILE_PATHS=",
    )

    for flag in banned_flags:
        assert flag not in _TEXT, (
            f"{_SKILL_MD}: found {flag!r} — task-authored prose must be "
            "passed with --set-file, never --set, or task text containing "
            "backticks/$() silently corrupts the rendered prompt."
        )


def test_step_5_7_gives_in_task_medium_findings_one_retry_stamped_medium_retry() -> None:
    # Step 5.7: a MEDIUM inside the task's FILES_TOUCHED gets one Ivan retry
    # and a Pat re-run before step 6, stamped "medium-retry:<fixed|unfixed>";
    # other MEDIUMs and all LOWs keep today's note-and-proceed behaviour.
    start = _TEXT.index("### 5.7.")
    end = _TEXT.index("### 6.", start)
    section = _TEXT[start:end]

    assert "FILES_TOUCHED" in section, (
        f"{_SKILL_MD}: expected step 5.7 to name FILES_TOUCHED — not found."
    )
    assert "medium-retry:" in section, (
        f"{_SKILL_MD}: expected step 5.7 to stamp 'medium-retry:' — not found."
    )


def test_step_7_runs_the_style_limit_gate_and_declares_compute_mech_facts() -> None:
    # Step 7 must run check_style_limits.py before the full suite and stamp
    # style_gate: clean | fixed:<sha> | failed:<violations>; the function
    # walk must be declared as a cross-skill dependency on
    # compute_mech_facts.py, never a second ast walker.
    start = _TEXT.index("### 7.")
    end = _TEXT.index("## Reference Files", start)
    step_7 = _TEXT[start:end]

    for needle in ("check_style_limits.py", "style_gate: clean", "fixed:", "failed:"):
        assert needle in step_7, (
            f"{_SKILL_MD}: expected step 7 to contain {needle!r} — not found."
        )

    dep_start = _TEXT.index("## Dependencies")
    dep_end = _TEXT.index("\n## ", dep_start)
    dependencies = _TEXT[dep_start:dep_end]

    assert "compute_mech_facts.py" in dependencies, (
        f"{_SKILL_MD}: expected '## Dependencies' to name compute_mech_facts.py "
        "— not found."
    )
