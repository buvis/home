#!/usr/bin/env python3
"""
Skill Initializer - Creates a new Claude Code skill from template.

Usage:
    init_skill.py <skill-name> --path <path> [--resources scripts,references,assets]

Examples:
    init_skill.py my-skill --path ~/.claude/skills
    init_skill.py my-skill --path .claude/skills --resources scripts,references
"""

import argparse
import re
import sys
from pathlib import Path

MAX_SKILL_NAME_LENGTH = 64
ALLOWED_RESOURCES = {"scripts", "references", "assets"}

SKILL_TEMPLATE = """---
name: {skill_name}
description: TODO - what this skill does and when to use it. Keep under 250 chars. Include trigger scenarios.
---

# {skill_title}

TODO: Instructions for using this skill. Use imperative form.

Structure options:
- Workflow-based (sequential steps)
- Task-based (different operations)
- Reference/guidelines (standards or specs)
- Capabilities-based (interrelated features)
"""


def normalize_skill_name(skill_name: str) -> str:
    """Normalize a skill name to lowercase hyphen-case."""
    normalized = skill_name.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = normalized.strip("-")
    normalized = re.sub(r"-{2,}", "-", normalized)
    return normalized


def title_case_skill_name(skill_name: str) -> str:
    """Convert hyphenated skill name to Title Case."""
    return " ".join(word.capitalize() for word in skill_name.split("-"))


def parse_resources(raw_resources: str) -> list[str]:
    if not raw_resources:
        return []
    resources = [item.strip() for item in raw_resources.split(",") if item.strip()]
    invalid = sorted({item for item in resources if item not in ALLOWED_RESOURCES})
    if invalid:
        allowed = ", ".join(sorted(ALLOWED_RESOURCES))
        print(f"[ERROR] Unknown resource type(s): {', '.join(invalid)}")
        print(f"   Allowed: {allowed}")
        sys.exit(1)
    seen: set[str] = set()
    deduped: list[str] = []
    for resource in resources:
        if resource not in seen:
            deduped.append(resource)
            seen.add(resource)
    return deduped


def init_skill(
    skill_name: str,
    path: str,
    resources: list[str],
) -> Path | None:
    """Initialize a new skill directory with template SKILL.md."""
    skill_dir = Path(path).resolve() / skill_name

    if skill_dir.exists():
        print(f"[ERROR] Skill directory already exists: {skill_dir}")
        return None

    try:
        skill_dir.mkdir(parents=True, exist_ok=False)
        print(f"[OK] Created skill directory: {skill_dir}")
    except Exception as e:
        print(f"[ERROR] Error creating directory: {e}")
        return None

    skill_title = title_case_skill_name(skill_name)
    skill_content = SKILL_TEMPLATE.format(skill_name=skill_name, skill_title=skill_title)

    skill_md_path = skill_dir / "SKILL.md"
    try:
        skill_md_path.write_text(skill_content)
        print("[OK] Created SKILL.md")
    except Exception as e:
        print(f"[ERROR] Error creating SKILL.md: {e}")
        return None

    for resource in resources:
        resource_dir = skill_dir / resource
        resource_dir.mkdir(exist_ok=True)
        print(f"[OK] Created {resource}/")

    print(f"\n[OK] Skill '{skill_name}' initialized at {skill_dir}")
    print("\nNext steps:")
    print("1. Edit SKILL.md: fill in description and instructions")
    if resources:
        print("2. Add resources to " + ", ".join(f"{r}/" for r in resources))
    print(f"3. Validate: ~/.claude/skills/skill-creator/scripts/validate_skill.py {skill_dir}")

    return skill_dir


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a new Claude Code skill directory with a SKILL.md template.",
    )
    parser.add_argument("skill_name", help="Skill name (normalized to hyphen-case)")
    parser.add_argument("--path", required=True, help="Output directory for the skill")
    parser.add_argument(
        "--resources",
        default="",
        help="Comma-separated list: scripts,references,assets",
    )
    args = parser.parse_args()

    raw_skill_name = args.skill_name
    skill_name = normalize_skill_name(raw_skill_name)
    if not skill_name:
        print("[ERROR] Skill name must include at least one letter or digit.")
        sys.exit(1)
    if len(skill_name) > MAX_SKILL_NAME_LENGTH:
        print(
            f"[ERROR] Skill name '{skill_name}' is too long ({len(skill_name)} chars). "
            f"Maximum is {MAX_SKILL_NAME_LENGTH}."
        )
        sys.exit(1)
    if skill_name != raw_skill_name:
        print(f"Note: Normalized skill name from '{raw_skill_name}' to '{skill_name}'.")

    resources = parse_resources(args.resources)
    path = args.path

    print(f"Initializing skill: {skill_name}")
    print(f"   Location: {path}")
    if resources:
        print(f"   Resources: {', '.join(resources)}")
    print()

    result = init_skill(skill_name, path, resources)
    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()
