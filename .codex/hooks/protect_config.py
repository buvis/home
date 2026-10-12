"""PreToolUse hook: block Edit/Write to linter and formatter config files.

The policy is to fix the source code rather than weaken the linter. Replaces
~/.claude/hooks/protect-config.sh.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import allow, block, read_input  # noqa: E402

PROTECTED_BASENAMES: frozenset[str] = frozenset({
    # eslint
    ".eslintrc",
    ".eslintrc.js",
    ".eslintrc.cjs",
    ".eslintrc.json",
    ".eslintrc.yml",
    ".eslintrc.yaml",
    "eslint.config.js",
    "eslint.config.mjs",
    "eslint.config.cjs",
    "eslint.config.ts",
    "eslint.config.mts",
    "eslint.config.cts",
    # prettier
    ".prettierrc",
    ".prettierrc.js",
    ".prettierrc.cjs",
    ".prettierrc.json",
    ".prettierrc.yml",
    ".prettierrc.yaml",
    "prettier.config.js",
    "prettier.config.cjs",
    "prettier.config.mjs",
    # biome
    "biome.json",
    "biome.jsonc",
    # ruff
    ".ruff.toml",
    "ruff.toml",
    # shellcheck
    ".shellcheckrc",
    # stylelint
    ".stylelintrc",
    ".stylelintrc.json",
    ".stylelintrc.yml",
    # markdownlint
    ".markdownlint.json",
    ".markdownlint.yaml",
    ".markdownlintrc",
    # clippy
    "clippy.toml",
    ".clippy.toml",
    # swiftlint
    ".swiftlint.yml",
    ".swiftlint.yaml",
})


def main() -> None:
    data = read_input()
    file_path = (data.get("tool_input") or {}).get("file_path") or ""
    if not file_path:
        allow()
    basename = os.path.basename(file_path)
    if basename in PROTECTED_BASENAMES:
        block(
            f"BLOCKED: editing {basename} is not allowed. "
            "Fix the source code instead of weakening linter/formatter config."
        )
    allow()


if __name__ == "__main__":
    main()
