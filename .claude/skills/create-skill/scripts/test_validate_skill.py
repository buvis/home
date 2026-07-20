"""Tests for validate_skill.py's live-profile bash lints (PRD 00083)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate_skill import lint_bash_commands


def block(*lines: str) -> str:
    body = "\n".join(lines)
    return f"# Skill\n\n```bash\n{body}\n```\n"


def test_aegis_denied_binaries_are_flagged():
    errs = lint_bash_commands(block("foo | head -5"))
    assert any("head" in e and "aegis" in e for e in errs)
    assert any("grep" in e for e in lint_bash_commands(block("grep x f")))
    assert any("find" in e for e in lint_bash_commands(block("find . -name '*.py'")))
    assert any("cat" in e for e in lint_bash_commands(block("cat f | jq .")))


def test_standalone_assignment_flagged_but_env_prefix_allowed():
    assert any("standalone shell-variable" in e for e in lint_bash_commands(block("F=/tmp/x")))
    # a self-contained env-prefix launch command is NOT the persistence anti-pattern
    assert lint_bash_commands(block('WARDEN_UNATTENDED=1 claude -p "/x"')) == []


def test_cd_chain_flagged():
    assert any("`cd` chain" in e for e in lint_bash_commands(block("cd sub && python3 x.py")))
    # a bare cd with no chain is not flagged by this rule
    assert not any("`cd` chain" in e for e in lint_bash_commands(block("cd sub")))


def test_bare_script_path_flagged_but_skill_helpers_exempt():
    assert any("bare script path" in e for e in lint_bash_commands(block("/tmp/deploy.sh --go")))
    assert any("bare script path" in e for e in lint_bash_commands(block("./run.py")))
    # a skill's own helper (warden allows ~/.claude/skills/**) is the documented pattern
    assert lint_bash_commands(block("~/.claude/skills/use-codex/scripts/codex-run.sh -f /tmp/p")) == []
    assert lint_bash_commands(block("python3 ${CLAUDE_SKILL_DIR}/scripts/run.py")) == []


def test_undocumented_shell_var_flagged_but_substitutions_allowed():
    assert any("$F" in e for e in lint_bash_commands(block("rm -rf $F")))
    for good in ("${CLAUDE_SKILL_DIR}", "$PWD", "$HOME", "$ARGUMENTS", "${CLAUDE_PLUGIN_ROOT}"):
        assert lint_bash_commands(block(f"ls {good}/x")) == [], good


def test_clean_block_has_no_findings():
    clean = block(
        "rg -n pattern file.txt",
        "python3 ${CLAUDE_SKILL_DIR}/scripts/run.py --json",
        "git --git-dir=$HOME/.buvis log",
        "uv run --with pytest python -m pytest x.py -q",
    )
    assert lint_bash_commands(clean) == []


def test_only_fenced_bash_is_scanned():
    # a $VAR mentioned in prose or a non-bash fence must not be flagged
    prose = "Use `$REPO/skills` carefully.\n\n```python\nx = grep\n```\n"
    assert lint_bash_commands(prose) == []


def test_all_personal_skills_pass():
    """Acceptance: every shipped personal skill survives the extended validator."""
    skills = sorted(Path("/Users/bob/.claude/skills").glob("*/SKILL.md"))
    assert len(skills) >= 30  # sanity: we actually found the corpus
    offenders = {s.parent.name: lint_bash_commands(s.read_text())
                 for s in skills if lint_bash_commands(s.read_text())}
    assert offenders == {}, offenders
