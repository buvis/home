"""Tests for validate_skill.py's live-profile bash lints (PRD 00083) and
Agent Skills standard conformance (agentskills.io/specification)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate_skill import lint_bash_commands, validate_skill


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


def make_skill(tmp_path: Path, dirname: str, frontmatter: str) -> Path:
    skill = tmp_path / dirname
    skill.mkdir()
    (skill / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n\n# {dirname}\n\nDo the thing.\n")
    return skill


def test_missing_name_and_description_are_errors(tmp_path):
    errors, _ = validate_skill(make_skill(tmp_path, "no-meta", "license: MIT"))
    assert any("required field 'name'" in e for e in errors)
    assert any("required field 'description'" in e for e in errors)


def test_name_must_match_directory(tmp_path):
    errors, _ = validate_skill(
        make_skill(tmp_path, "on-disk", "name: in-frontmatter\ndescription: Use when testing.")
    )
    assert any("does not match directory name" in e for e in errors)


def test_compatibility_capped_at_500_chars(tmp_path):
    fm = "name: compat\ndescription: Use when testing.\ncompatibility: " + "x" * 501
    errors, _ = validate_skill(make_skill(tmp_path, "compat", fm))
    assert any("compatibility is too long" in e for e in errors)


def test_metadata_must_map_strings_to_strings(tmp_path):
    fm = "name: meta\ndescription: Use when testing.\nmetadata:\n  version: 1.0\n"
    errors, _ = validate_skill(make_skill(tmp_path, "meta", fm))
    assert any("metadata must map string keys to string values" in e for e in errors)


def test_claude_code_fields_warn_about_portability(tmp_path):
    fm = 'name: ext\ndescription: Use when testing.\nargument-hint: "[path]"'
    errors, warnings = validate_skill(make_skill(tmp_path, "ext", fm))
    assert errors == []
    assert any("Claude Code-only frontmatter field(s): argument-hint" in w for w in warnings)


def test_standard_only_skill_is_clean(tmp_path):
    fm = ('name: clean\ndescription: Use when testing.\nlicense: MIT\n'
          'compatibility: Requires jq\nmetadata:\n  version: "1.0"\n')
    assert validate_skill(make_skill(tmp_path, "clean", fm)) == ([], [])


def test_all_personal_skills_pass():
    """Acceptance: every shipped personal skill survives the extended validator."""
    skills = sorted(Path("/Users/bob/.claude/skills").glob("*/SKILL.md"))
    assert len(skills) >= 30  # sanity: we actually found the corpus
    offenders = {s.parent.name: lint_bash_commands(s.read_text())
                 for s in skills if lint_bash_commands(s.read_text())}
    assert offenders == {}, offenders
