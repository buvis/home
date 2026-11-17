"""AGENTS.md must fit the Codex instruction limit.

Codex reads at most `project_doc_max_bytes` (default 32768) of the global
instructions and drops the rest without a warning. The file is shared by all
agents, so its end must not be lost.
"""

from pathlib import Path

CODEX_DEFAULT_LIMIT = 32768


def test_agents_md_fits_the_codex_default_limit() -> None:
    size = (Path.home() / ".claude" / "AGENTS.md").stat().st_size
    assert size < CODEX_DEFAULT_LIMIT, (
        f"AGENTS.md is {size} bytes; Codex drops everything after "
        f"{CODEX_DEFAULT_LIMIT}. Move Claude-specific material to "
        "~/.claude/rules/claude-environment.md."
    )
