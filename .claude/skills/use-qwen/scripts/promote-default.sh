#!/bin/bash
# Automates eval-runbook.md's "phase 3" (see SKILL.md's "Onboarding a New
# Model" section, and references/onboarding-walkthrough.md for a worked
# example): promotes an already-qualified model id to the documented default
# across the three files test_qwen_run.sh (T19) ties together as one
# invariant. Refuses if the candidate is not yet in approved-models.txt -
# that qualification (scripts/run-eval.sh) is the one step this script will
# not skip.
set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
SKILL_MD="${QWEN_SKILL_MD:-$SCRIPT_DIR/../SKILL.md}"
INTEGRATION_MD="${QWEN_INTEGRATION_MD:-$CLAUDE_DIR/skills/work/references/qwen-integration.md}"
TEST_SH="${QWEN_TEST_SH:-$SCRIPT_DIR/test_qwen_run.sh}"
REGISTRY="${QWEN_APPROVED_REGISTRY:-$SCRIPT_DIR/approved-models.txt}"
DEFAULT_MODEL_FILE="${QWEN_DEFAULT_MODEL_FILE:-$SCRIPT_DIR/default-model.txt}"

NEW_ID="${1:-}"
if [ -z "$NEW_ID" ]; then
    echo "Usage: $0 <new-model-id>" >&2
    echo "" >&2
    echo "Promotes an already-qualified id (must already be an exact line in" >&2
    echo "$REGISTRY - run scripts/run-eval.sh --commit first) to the documented" >&2
    echo "default across SKILL.md, work/references/qwen-integration.md, and" >&2
    echo "scripts/test_qwen_run.sh's SHIPPED_DEFAULT_ID (test T19)." >&2
    exit 2
fi

if ! grep -qFx -- "$NEW_ID" "$REGISTRY"; then
    echo "ERROR: '$NEW_ID' is not an approved id in $REGISTRY yet. Run scripts/run-eval.sh --commit first - this script only promotes an already-qualified candidate." >&2
    exit 1
fi

OLD_ID="$(sed -n 's/^SHIPPED_DEFAULT_ID="\(.*\)"$/\1/p' "$TEST_SH")"
if [ -z "$OLD_ID" ]; then
    echo "ERROR: could not find SHIPPED_DEFAULT_ID in $TEST_SH - refusing to guess." >&2
    exit 1
fi
if [ "$OLD_ID" = "$NEW_ID" ]; then
    echo "'$NEW_ID' is already the documented default. Nothing to do."
    exit 0
fi

# Pull the qualification comment run-eval.sh wrote directly above NEW_ID, so
# the regenerated Default bullet states only facts already computed during
# eval - never a fabricated rationale (task domain, strengths) carried over
# from the OLD candidate onto a model that never earned it.
# The comment above an id can wrap across multiple lines (run-eval.sh writes
# two) - look back far enough to find the actual "# Qualified ..." line
# rather than assuming it's the single line directly above.
QUAL_LINE="$(grep -B20 -Fx -- "$NEW_ID" "$REGISTRY" | grep '^# Qualified' | tail -n1)"
QUAL_DATE="$(printf '%s' "$QUAL_LINE" | sed -n 's/^# Qualified \([0-9-]*\):.*/\1/p')"
QUAL_SCORE="$(printf '%s' "$QUAL_LINE" | grep -oE '[0-9]/6' | head -n1)"
[ -z "$QUAL_DATE" ] && QUAL_DATE="unknown-date"
[ -z "$QUAL_SCORE" ] && QUAL_SCORE="?/6"

BACKUP_DIR="$(mktemp -d)"
cp "$SKILL_MD" "$BACKUP_DIR/SKILL.md"
cp "$INTEGRATION_MD" "$BACKUP_DIR/qwen-integration.md"
cp "$TEST_SH" "$BACKUP_DIR/test_qwen_run.sh"
[ -f "$DEFAULT_MODEL_FILE" ] && cp "$DEFAULT_MODEL_FILE" "$BACKUP_DIR/default-model.txt"
restore() {
    cp "$BACKUP_DIR/SKILL.md" "$SKILL_MD"
    cp "$BACKUP_DIR/qwen-integration.md" "$INTEGRATION_MD"
    cp "$BACKUP_DIR/test_qwen_run.sh" "$TEST_SH"
    if [ -f "$BACKUP_DIR/default-model.txt" ]; then
        cp "$BACKUP_DIR/default-model.txt" "$DEFAULT_MODEL_FILE"
    else
        rm -f "$DEFAULT_MODEL_FILE"
    fi
}

# Literal substitution, `|`-delimited (ids may contain `/`, which would break
# the usual `/` delimiter). ponytail: ids are drawn from [A-Za-z0-9._:/-] -
# the only sed-special char among them is `.`, harmless here as a wildcard
# since these ids are unique enough in these files that nothing else could
# coincidentally match; escape properly if an id ever gains a `[`/`*`/`^`/`$`.
lit_replace() {
    local file="$1" from="$2" to="$3" from_esc to_esc
    from_esc="$(printf '%s' "$from" | sed -e 's/\\/\\\\/g' -e 's/|/\\|/g')"
    to_esc="$(printf '%s' "$to" | sed -e 's/\\/\\\\/g' -e 's/|/\\|/g' -e 's/&/\\&/g')"
    sed -i '' "s|$from_esc|$to_esc|g" "$file"
}

lit_replace "$SKILL_MD" "$OLD_ID" "$NEW_ID"
lit_replace "$INTEGRATION_MD" "$OLD_ID" "$NEW_ID"
lit_replace "$TEST_SH" "SHIPPED_DEFAULT_ID=\"$OLD_ID\"" "SHIPPED_DEFAULT_ID=\"$NEW_ID\""

# The resolution-level default: qwen-run.sh prefers this id whenever the
# resolved server lists it, so the promotion changes what actually gets
# dispatched, not just the docs (multi-model servers list every downloaded
# model - listing order must not decide).
cat > "$DEFAULT_MODEL_FILE" <<EOF
# Promoted default for qwen-run.sh resolution - written by promote-default.sh.
# One id: dispatch prefers it whenever the resolved server lists it
# (--approved-only additionally requires it to be approved).
$NEW_ID
EOF

# The Model Selection "Default: ..." bullet uses a hand-written shorthand
# name + rationale, not the literal id - lit_replace above cannot reach it.
# Regenerate fact-only from the qualification comment; add domain-specific
# rationale by hand afterward if useful.
NEW_BULLET="- **Default: \`$NEW_ID\`.** Qualified $QUAL_DATE ($QUAL_SCORE agentic eval, zero false claims - see \`references/eval-runbook.md\`)."
NEW_BULLET_ESC="$(printf '%s' "$NEW_BULLET" | sed -e 's/\\/\\\\/g' -e 's/|/\\|/g' -e 's/&/\\&/g')"
sed -i '' "s|^- \\*\\*Default:.*\$|$NEW_BULLET_ESC|" "$SKILL_MD"

echo "Running the regression suite to confirm the promotion is consistent..."
if bash "$TEST_SH" > "$BACKUP_DIR/test-output.txt" 2>&1; then
    echo "Promoted '$NEW_ID' to default (was '$OLD_ID'). Regression suite: PASS."
    echo "Changed: $SKILL_MD, $INTEGRATION_MD, $TEST_SH, $DEFAULT_MODEL_FILE"
    echo "The regenerated Default bullet in SKILL.md is fact-only by design - add domain-specific rationale (task types, observed strengths) by hand if useful."
    exit 0
else
    echo "ERROR: regression suite FAILED after promotion - rolling back all 3 files." >&2
    cat "$BACKUP_DIR/test-output.txt" >&2
    restore
    exit 1
fi
