#!/usr/bin/env bash
# ~/.claude/hooks/protect-config.sh
# PreToolUse hook: blocks Edit/Write to linter/formatter config files.
# Exit 0 = allow, Exit 2 = block.

payload="$(cat)"
file_path="$(printf '%s' "$payload" | jq -r '.tool_input.file_path // empty')"

if [ -z "$file_path" ]; then
  exit 0
fi

basename="$(basename "$file_path")"

case "$basename" in
  .eslintrc|.eslintrc.js|.eslintrc.cjs|.eslintrc.json|.eslintrc.yml|.eslintrc.yaml|\
  eslint.config.js|eslint.config.mjs|eslint.config.cjs|eslint.config.ts|eslint.config.mts|eslint.config.cts|\
  .prettierrc|.prettierrc.js|.prettierrc.cjs|.prettierrc.json|.prettierrc.yml|.prettierrc.yaml|\
  prettier.config.js|prettier.config.cjs|prettier.config.mjs|\
  biome.json|biome.jsonc|\
  .ruff.toml|ruff.toml|\
  .shellcheckrc|\
  .stylelintrc|.stylelintrc.json|.stylelintrc.yml|\
  .markdownlint.json|.markdownlint.yaml|.markdownlintrc|\
  clippy.toml|.clippy.toml|\
  .swiftlint.yml|.swiftlint.yaml)
    echo "BLOCKED: editing $basename is not allowed. Fix the source code instead of weakening linter/formatter config." >&2
    exit 2
    ;;
esac

exit 0
