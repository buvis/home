#!/usr/bin/env bash
# ~/.claude/hooks/validate-commit-msg.sh
# PreToolUse hook: validates git commit messages against conventional commit format.
# Exit 0 = allow, Exit 2 = block.

payload="$(cat)"
command="$(printf '%s' "$payload" | jq -r '.tool_input.command // empty')"

# Only validate git commit commands
case "$command" in
  git\ commit*) ;;
  *) exit 0 ;;
esac

# Skip commits with no inline message (e.g. --amend with editor, -F file)
if ! printf '%s' "$command" | grep -q '\-m '; then
  exit 0
fi

# Extract commit message - handle both direct -m and HEREDOC $(cat <<'EOF'...)
if printf '%s' "$command" | grep -q 'cat <<'; then
  # HEREDOC: extract lines between <<'EOF' (or <<EOF) and EOF
  msg="$(printf '%s' "$command" | sed -n "/<<['\"]\\{0,1\\}EOF['\"]\\{0,1\\}/,/^[[:space:]]*EOF/{//d;p;}")"
else
  # Direct -m: extract quoted string after -m
  msg="$(printf '%s' "$command" | sed -n 's/.*-m "\(.*\)"/\1/p')"
  if [ -z "$msg" ]; then
    msg="$(printf '%s' "$command" | sed -n "s/.*-m '\(.*\)'/\1/p")"
  fi
  if [ -z "$msg" ]; then
    # Unquoted or unparseable - let git handle it
    exit 0
  fi
fi

# Get first non-empty line (the subject)
subject="$(printf '%s' "$msg" | sed '/^[[:space:]]*$/d' | head -1 | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')"

if [ -z "$subject" ]; then
  exit 0
fi

# Check for forbidden boilerplate anywhere in the message
if printf '%s' "$msg" | grep -qi 'co-authored-by\|signed-off-by\|generated-by\|generated with'; then
  echo "BLOCKED: commit message contains forbidden boilerplate (Co-Authored-By, Signed-Off-By, etc). Per CLAUDE.md: do not include generated-by or co-authored-by boilerplate." >&2
  exit 2
fi

# Validate conventional commit format: <type>(<scope>): <description>
# Scope is optional, ! for breaking changes is optional
pattern='^(fix|feat|perf|refactor|style|test|docs|build|ops|chore)(\([a-zA-Z0-9_./-]+\))?!?: [a-z]'
if ! printf '%s' "$subject" | grep -qE "$pattern"; then
  echo "BLOCKED: commit message does not follow conventional commit format." >&2
  echo "  Got: \"$subject\"" >&2
  echo "  Expected: <type>(<scope>): <lowercase description>" >&2
  echo "  Types: fix|feat|perf|refactor|style|test|docs|build|ops|chore" >&2
  echo "  Rules: imperative present tense, no capital, no period, one line" >&2
  exit 2
fi

# Check for trailing period
if printf '%s' "$subject" | grep -qE '\.$'; then
  echo "BLOCKED: commit message must not end with a period." >&2
  echo "  Got: \"$subject\"" >&2
  exit 2
fi

exit 0
