#!/usr/bin/env python3
"""
Validate a Claude Code skill directory.

Checks SKILL.md structure, frontmatter fields, naming conventions,
and resource organization.

Usage:
    validate_skill.py <path/to/skill-folder>
"""

import re
import sys
from pathlib import Path

import yaml

MAX_SKILL_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
RECOMMENDED_DESCRIPTION_LENGTH = 250
MAX_SKILL_MD_LINES = 500

# All fields recognized by Claude Code or the Agent Skills open standard
ALLOWED_FIELDS = {
    # Core
    "name",
    "description",
    # Invocation control
    "disable-model-invocation",
    "user-invocable",
    # Execution control
    "allowed-tools",
    "model",
    "effort",
    "context",
    "agent",
    # Scoping
    "paths",
    "argument-hint",
    # Advanced
    "hooks",
    "shell",
    # Open standard
    "license",
    "compatibility",
    "metadata",
}

EFFORT_VALUES = {"low", "medium", "high", "max"}
SHELL_VALUES = {"bash", "powershell"}

# --- Live-profile lints (PRD 00083) ---------------------------------------
# Every fenced bash command a SKILL.md tells the agent to run is checked
# against the environment it will actually run in: the aegis prefer_tools deny
# set, warden/permission conventions, and the no-persistent-shell contract.
# These are ERRORs (not model judgment) because each one is a command our own
# hooks deny or a pattern that cannot work in a fresh Bash call.

# aegis prefer_tools.py DENY binaries, mirrored (the hook blocks these even
# though the permission allowlist lists some of them).
AEGIS_DENY = {
    "grep": "use `rg -n`",
    "find": "use `rg --files` (add `-g <glob>`) or the Explore agent",
    "cat": "use the Read tool, or pass the filename straight to the next tool",
    "head": "run the command bare (Bash truncates) or redirect to a file and Read it",
    "tail": "run the command bare (Bash truncates) or redirect to a file and Read it",
}
# Binaries the settings.json permission allowlist recognizes as a prefix. A
# bare path first-token whose basename is not one of these relies on the exec
# bit + shebang and trips the permission gate; invoke via an interpreter.
PERMISSION_BINARIES = {
    "git", "rm", "gh", "cargo", "node", "python", "python3", "pip", "npm",
    "pnpm", "npx", "yarn", "uv", "uvx", "ruff", "mypy", "pytest", "showboat",
    "zdb", "ast-grep", "mdbook", "codex", "copilot", "claude", "mise", "curl",
    "ls", "bash", "pwd", "cat", "echo", "rg", "wc", "sort", "diff", "tree",
    "which", "xxd", "test", "timeout", "lsof", "dig", "ffmpeg", "ffprobe",
    "mkdocs", "rmdir", "shellcheck", "rustc", "gpgconf", "ddb", "cp", "mv",
    "mkdir", "touch", "sed", "awk", "kill", "pkill", "docker", "kubectl",
    "sqlite3", "jq", "stat", "du",
}
# $VAR names that ARE a documented substitution or an always-set env var; every
# other $NAME in a fenced block is an author variable that a fresh Bash call
# leaves unset (shell state never persists between calls).
ALLOWED_SUBST = {
    "CLAUDE_SKILL_DIR", "CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR",
    "CLAUDE_CONFIG_DIR", "ARGUMENTS", "HOME", "PWD", "USER", "PATH", "SHELL",
    "TMPDIR",
}

_QUOTED_RE = re.compile(r"'[^']*'|\"[^\"]*\"")
_SEGMENT_RE = re.compile(r"\|\|?|&&|;|\$\(|`")
_SUBSHELL_OPEN_RE = re.compile(r"^\s*(\$\(|`)\s*")
_WRAPPERS = {"xargs", "time", "nice", "sudo", "command", "env"}
_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_VAR_RE = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")
_BASH_FENCE_RE = re.compile(r"```(?:bash|sh|shell)\n(.*?)```", re.DOTALL)


def _first_token(segment: str) -> str:
    """First real token of a segment, peeling subshell openers, env-assignment
    prefixes, and wrappers (mirrors aegis prefer_tools.first_meaningful_token)."""
    seg = segment.strip()
    while True:
        m = _SUBSHELL_OPEN_RE.match(seg)
        if not m:
            break
        seg = seg[m.end():].lstrip()
    tokens = re.split(r"\s+", seg) if seg else []
    i = 0
    while i < len(tokens) and _ASSIGN_RE.match(tokens[i]):
        i += 1
    while i < len(tokens) and tokens[i] in _WRAPPERS:
        i += 1
        while i < len(tokens) and tokens[i].startswith("-"):
            i += 1
    return tokens[i] if i < len(tokens) else ""


def _iter_bash_commands(content: str):
    """Yield (command_line) for each executable line in a ```bash fenced block,
    joining backslash-continued lines and dropping comments/blank lines."""
    for block in _BASH_FENCE_RE.findall(content):
        buf = ""
        for raw in block.splitlines():
            line = raw.rstrip()
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                if not buf:
                    continue
            if buf:
                line = buf + " " + line.strip()
                buf = ""
            if line.rstrip().endswith("\\"):
                buf = line.rstrip()[:-1].rstrip()
                continue
            cmd = line.strip()
            if cmd and not cmd.startswith("#"):
                yield cmd


def lint_bash_commands(content: str) -> list[str]:
    """Return ERROR strings for fenced bash commands the live profile rejects."""
    errors: list[str] = []
    for cmd in _iter_bash_commands(content):
        scan = _QUOTED_RE.sub("", cmd)
        segments = _SEGMENT_RE.split(scan)
        # (a) aegis-denied binaries in any segment (incl. pipes/subshells)
        for seg in segments:
            tok = _first_token(seg)
            if tok in AEGIS_DENY:
                errors.append(f"bash `{cmd}`: `{tok}` is denied by aegis prefer_tools - {AEGIS_DENY[tok]}")
                break
        first = _first_token(segments[0]) if segments else ""
        # (b) STANDALONE shell-variable assignment (whole command is NAME=value).
        # A self-contained env-prefix (`FOO=bar cmd`) is left alone - it does not
        # rely on shell state surviving to the next call, which is the anti-pattern.
        if _ASSIGN_RE.match(scan.strip()) and len(scan.strip().split()) == 1:
            errors.append(f"bash `{cmd}`: standalone shell-variable assignment - shell state does not persist between Bash calls; inline the value at each use site")
        # (c) cd chain
        for seg in segments:
            if _first_token(seg) == "cd" and len(segments) > 1:
                errors.append(f"bash `{cmd}`: `cd` chain - cwd persists across Bash calls and breaks hooks; use absolute paths, no `cd`")
                break
        # (d) bare unallowlisted script path invoked directly. A skill invoking a
        # helper under a skills dir is the documented pattern (warden allows
        # ~/.claude/skills/**), so those are exempt; a stray path elsewhere is not.
        if ("/" in first or first.startswith("./")) and Path(first).name not in PERMISSION_BINARIES:
            skill_helper = any(m in first for m in (
                "/.claude/skills/", "${CLAUDE_SKILL_DIR}", "${CLAUDE_PLUGIN_ROOT}", "${CLAUDE_CONFIG_DIR}"))
            if not skill_helper and re.search(r"\.(py|sh|mjs|js|rb|pl)$", first):
                errors.append(f"bash `{cmd}`: bare script path `{first}` relies on the exec bit; invoke via its interpreter (e.g. `python3 {first}`)")
        # (e) undocumented $VAR
        for name in _VAR_RE.findall(scan):
            if name not in ALLOWED_SUBST and not name.isdigit():
                errors.append(f"bash `{cmd}`: `${name}` is an author shell variable a fresh Bash call leaves unset; inline the path or use ${{CLAUDE_SKILL_DIR}}")
                break
    return errors


def validate_skill(skill_path: Path) -> tuple[list[str], list[str]]:
    """Validate a skill directory. Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []

    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        errors.append("SKILL.md not found")
        return errors, warnings

    content = skill_md.read_text()

    # Check frontmatter exists
    if not content.startswith("---"):
        errors.append("No YAML frontmatter found (must start with ---)")
        return errors, warnings

    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        errors.append("Invalid frontmatter format (missing closing ---)")
        return errors, warnings

    frontmatter_text = match.group(1)

    try:
        frontmatter = yaml.safe_load(frontmatter_text)
        if not isinstance(frontmatter, dict):
            errors.append("Frontmatter must be a YAML dictionary")
            return errors, warnings
    except yaml.YAMLError as e:
        errors.append(f"Invalid YAML in frontmatter: {e}")
        return errors, warnings

    # Check for unexpected fields
    unexpected_keys = set(frontmatter.keys()) - ALLOWED_FIELDS
    if unexpected_keys:
        errors.append(
            f"Unknown frontmatter field(s): {', '.join(sorted(unexpected_keys))}. "
            f"Allowed: {', '.join(sorted(ALLOWED_FIELDS))}"
        )

    # Validate name
    name = frontmatter.get("name", "")
    if name:
        if not isinstance(name, str):
            errors.append(f"name must be a string, got {type(name).__name__}")
        else:
            name = name.strip()
            if not re.match(r"^[a-z0-9-]+$", name):
                errors.append(
                    f"name '{name}' must be hyphen-case "
                    "(lowercase letters, digits, and hyphens only)"
                )
            elif name.startswith("-") or name.endswith("-") or "--" in name:
                errors.append(
                    f"name '{name}' cannot start/end with hyphen "
                    "or contain consecutive hyphens"
                )
            if len(name) > MAX_SKILL_NAME_LENGTH:
                errors.append(
                    f"name is too long ({len(name)} chars, max {MAX_SKILL_NAME_LENGTH})"
                )
            if name != skill_path.name:
                warnings.append(
                    f"name '{name}' does not match directory name '{skill_path.name}'"
                )

    # Validate description
    description = frontmatter.get("description", "")
    if not description:
        warnings.append("Missing description - this is the primary trigger mechanism")
    elif not isinstance(description, str):
        errors.append(f"description must be a string, got {type(description).__name__}")
    else:
        description = description.strip()
        if len(description) > MAX_DESCRIPTION_LENGTH:
            errors.append(
                f"description is too long ({len(description)} chars, max {MAX_DESCRIPTION_LENGTH})"
            )
        elif len(description) > RECOMMENDED_DESCRIPTION_LENGTH:
            warnings.append(
                f"description is {len(description)} chars; "
                f"only first {RECOMMENDED_DESCRIPTION_LENGTH} are visible in context listing"
            )
        if description.startswith("TODO"):
            errors.append("description still contains TODO placeholder")

    # Validate boolean fields
    for field in ("disable-model-invocation", "user-invocable"):
        value = frontmatter.get(field)
        if value is not None and not isinstance(value, bool):
            errors.append(f"{field} must be a boolean, got {type(value).__name__}")

    # Validate effort
    effort = frontmatter.get("effort")
    if effort is not None:
        if not isinstance(effort, str) or effort not in EFFORT_VALUES:
            errors.append(f"effort must be one of {sorted(EFFORT_VALUES)}, got '{effort}'")

    # Validate context
    context = frontmatter.get("context")
    if context is not None and context != "fork":
        errors.append(f"context must be 'fork', got '{context}'")

    # Validate shell
    shell = frontmatter.get("shell")
    if shell is not None:
        if not isinstance(shell, str) or shell not in SHELL_VALUES:
            errors.append(f"shell must be one of {sorted(SHELL_VALUES)}, got '{shell}'")

    # Validate allowed-tools
    allowed_tools = frontmatter.get("allowed-tools")
    if allowed_tools is not None:
        if not isinstance(allowed_tools, (str, list)):
            errors.append(
                f"allowed-tools must be a string or list, got {type(allowed_tools).__name__}"
            )

    # Validate paths
    paths = frontmatter.get("paths")
    if paths is not None:
        if not isinstance(paths, (str, list)):
            errors.append(f"paths must be a string or list, got {type(paths).__name__}")

    # Check body
    body = content[match.end():].strip()
    if not body:
        warnings.append("SKILL.md body is empty - add instructions")
    elif re.search(r"^TODO:", body, re.MULTILINE):
        # Match the template's leftover line (init_skill.py), not prose that
        # merely names TODO as a marker (create-prd's guess-density gate does).
        warnings.append("SKILL.md body still contains TODO placeholders")

    # Check line count
    line_count = content.count("\n") + 1
    if line_count > MAX_SKILL_MD_LINES:
        warnings.append(
            f"SKILL.md is {line_count} lines (recommended max {MAX_SKILL_MD_LINES}). "
            "Consider splitting content into references/"
        )

    # Check for broken references (skip inline code spans and fenced blocks
    # so that examples like `[Author, Date](URL)` are not treated as links)
    scannable = re.sub(r"```.*?```", "", content, flags=re.DOTALL)
    scannable = re.sub(r"~~~.*?~~~", "", scannable, flags=re.DOTALL)
    scannable = re.sub(r"``[^`\n]+``", "", scannable)
    scannable = re.sub(r"`[^`\n]+`", "", scannable)
    ref_pattern = re.compile(r"\[.*?\]\(((?!https?://)[^)]+)\)")
    for ref_match in ref_pattern.finditer(scannable):
        ref_path = ref_match.group(1)
        full_path = skill_path / ref_path
        if not full_path.exists():
            errors.append(f"Broken reference: [{ref_path}] - file not found")

    # Check for empty resource directories
    for resource_dir in ("scripts", "references", "assets"):
        dir_path = skill_path / resource_dir
        if dir_path.is_dir() and not any(dir_path.iterdir()):
            warnings.append(f"{resource_dir}/ is empty - add content or remove it")

    # Live-profile lints: fenced bash commands must survive the environment
    # they will run in (aegis deny set, permission allowlist, no shell state).
    errors.extend(lint_bash_commands(content))

    return errors, warnings


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: validate_skill.py <path/to/skill-folder>")
        sys.exit(1)

    skill_path = Path(sys.argv[1]).resolve()

    if not skill_path.exists():
        print(f"[ERROR] Path not found: {skill_path}")
        sys.exit(1)

    if not skill_path.is_dir():
        print(f"[ERROR] Path is not a directory: {skill_path}")
        sys.exit(1)

    print(f"Validating skill: {skill_path.name}\n")

    errors, warnings = validate_skill(skill_path)

    for warning in warnings:
        print(f"[WARN] {warning}")

    for error in errors:
        print(f"[ERROR] {error}")

    if not errors and not warnings:
        print("[OK] Skill is valid!")
    elif not errors:
        print(f"\n[OK] Valid with {len(warnings)} warning(s)")
    else:
        print(f"\n[FAIL] {len(errors)} error(s), {len(warnings)} warning(s)")

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
