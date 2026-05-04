"""PreToolUse Bash hook: validate `git commit -m` messages.

Replaces ~/.claude/hooks/validate-commit-msg.sh. Enforces conventional commit
format (`<type>(<scope>): <description>`) and rejects Co-Authored-By and other
generated-by boilerplate.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import allow, block, read_input  # noqa: E402

CONVENTIONAL_RE = re.compile(
    r"^(fix|feat|perf|refactor|style|test|docs|build|ops|chore)"
    r"(\([a-zA-Z0-9_./-]+\))?!?: [a-z]"
)
BOILERPLATE_RE = re.compile(
    r"co-authored-by|signed-off-by|generated-by|generated with",
    re.IGNORECASE,
)
HEREDOC_RE = re.compile(
    r"<<['\"]?EOF['\"]?\s*\n(.*?)\n[ \t]*EOF\b",
    re.DOTALL,
)
# Detect a real heredoc command-substitution (`$(cat <<DELIM ... DELIM)`),
# tolerating whitespace between `$(`, `cat`, and `<<`. Matching only the
# bare substring `"$(cat <<"` would miss `$( cat <<DELIM ... )`.
HEREDOC_TRIGGER_RE = re.compile(r"\$\(\s*cat\s*<<")
DOUBLE_QUOTE_RE = re.compile(r'-m "([^"]*)"')
SINGLE_QUOTE_RE = re.compile(r"-m '([^']*)'")

NOT_CONVENTIONAL_TEMPLATE = """\
BLOCKED: commit message does not follow conventional commit format.
  Got: "{subject}"
  Expected: <type>(<scope>): <lowercase description>
  Types: fix|feat|perf|refactor|style|test|docs|build|ops|chore
  Rules: imperative present tense, no capital, no period, one line"""

TRAILING_PERIOD_TEMPLATE = """\
BLOCKED: commit message must not end with a period.
  Got: "{subject}\""""

BOILERPLATE_MSG = (
    "BLOCKED: commit message contains forbidden boilerplate "
    "(Co-Authored-By, Signed-Off-By, etc). Per CLAUDE.md: do not include "
    "generated-by or co-authored-by boilerplate."
)


def extract_message(command: str) -> str | None:
    """Pull the commit message body out of a `git commit -m ...` command.

    Returns None when the message can't be parsed (e.g. unquoted, complex
    shell construction). The bash original allows through in this case.
    """
    # Detect a real heredoc command-substitution (`$(cat <<DELIM ... DELIM)`),
    # tolerating whitespace inside `$(`. A bare `"cat <<" in command` check
    # would false-positive on literal commit messages that mention the syntax
    # (e.g. `-m "fix: cat << pipes"`).
    if HEREDOC_TRIGGER_RE.search(command):
        match = HEREDOC_RE.search(command)
        if match:
            return match.group(1)
        # Heredoc with non-EOF delimiter — bash original returned empty,
        # which the caller treats as "allow". Don't fall through to the
        # quote regexes (they'd capture `$(cat <<DELIMITER` and false-block).
        return ""
    match = DOUBLE_QUOTE_RE.search(command)
    if match:
        return match.group(1)
    match = SINGLE_QUOTE_RE.search(command)
    if match:
        return match.group(1)
    return None


def main() -> None:
    data = read_input()
    command = (data.get("tool_input") or {}).get("command") or ""
    if not command.lstrip().startswith("git commit"):
        allow()
    if "-m " not in command:
        allow()
    msg = extract_message(command)
    if msg is None:
        allow()
    if BOILERPLATE_RE.search(msg):
        block(BOILERPLATE_MSG)
    subject = next(
        (line.strip() for line in msg.splitlines() if line.strip()),
        "",
    )
    if not subject:
        allow()
    if not CONVENTIONAL_RE.match(subject):
        block(NOT_CONVENTIONAL_TEMPLATE.format(subject=subject))
    if subject.endswith("."):
        block(TRAILING_PERIOD_TEMPLATE.format(subject=subject))
    allow()


if __name__ == "__main__":
    main()
