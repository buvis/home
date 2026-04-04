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
    elif "TODO" in body:
        warnings.append("SKILL.md body still contains TODO placeholders")

    # Check line count
    line_count = content.count("\n") + 1
    if line_count > MAX_SKILL_MD_LINES:
        warnings.append(
            f"SKILL.md is {line_count} lines (recommended max {MAX_SKILL_MD_LINES}). "
            "Consider splitting content into references/"
        )

    # Check for broken references
    ref_pattern = re.compile(r"\[.*?\]\(((?!https?://)[^)]+)\)")
    for ref_match in ref_pattern.finditer(content):
        ref_path = ref_match.group(1)
        full_path = skill_path / ref_path
        if not full_path.exists():
            errors.append(f"Broken reference: [{ref_path}] - file not found")

    # Check for empty resource directories
    for resource_dir in ("scripts", "references", "assets"):
        dir_path = skill_path / resource_dir
        if dir_path.is_dir() and not any(dir_path.iterdir()):
            warnings.append(f"{resource_dir}/ is empty - add content or remove it")

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
