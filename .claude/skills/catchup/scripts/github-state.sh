#!/bin/bash
# GitHub state: survey issues, PRs, branches, releases, and failed actions
# Designed for large context windows — fetches full bodies and error logs
# Requires: gh CLI, authenticated, in a git repo with a GitHub remote

set -e

# Check prerequisites
if ! command -v gh &>/dev/null; then
    echo "ERROR: gh CLI not installed"
    exit 1
fi

if ! gh auth status &>/dev/null 2>&1; then
    echo "ERROR: gh not authenticated (run 'gh auth login')"
    exit 1
fi

# Detect repo
REPO=$(gh repo view --json nameWithOwner -q '.nameWithOwner' 2>/dev/null) || {
    echo "ERROR: not a GitHub repository"
    exit 1
}

CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo "detached")

echo "=== GitHub State for $REPO ==="
echo "Current branch: $CURRENT_BRANCH"
echo ""

# --- Open Issues (full bodies) ---
echo "=== Open Issues ==="
TOTAL_ISSUES=$(gh issue list --state open --json number -q 'length' --limit 200 2>/dev/null || echo "?")
echo "Total open: $TOTAL_ISSUES"
echo ""

echo "--- High Priority (bug/critical/urgent/P0/P1) ---"
gh issue list --state open --label "bug" --limit 10 --json number,title,labels,updatedAt,body \
    -q '.[] | "### #\(.number) \(.title)\nupdated: \(.updatedAt[:10])\n\(.body[:500])\n"' 2>/dev/null || true
gh issue list --state open --label "critical,urgent,P0,P1" --limit 10 --json number,title,labels,updatedAt,body \
    -q '.[] | "### #\(.number) \(.title)\nupdated: \(.updatedAt[:10])\n\(.body[:500])\n"' 2>/dev/null || true
echo ""

echo "--- Recent Issues (last 20) ---"
gh issue list --state open --limit 20 --json number,title,labels,createdAt,body \
    -q '.[] | "### #\(.number) \(.title) [created: \(.createdAt[:10])]\n\(.body[:300])\n"' 2>/dev/null || echo "(none)"
echo ""

# --- Open PRs (full bodies + review comments) ---
echo "=== Open Pull Requests ==="
PR_NUMBERS=$(gh pr list --state open --limit 20 --json number -q '.[].number' 2>/dev/null || echo "")

if [ -n "$PR_NUMBERS" ]; then
    for pr in $PR_NUMBERS; do
        echo "--- PR #$pr ---"
        gh pr view "$pr" --json number,title,author,baseRefName,headRefName,createdAt,updatedAt,reviewDecision,isDraft,body,comments,reviews \
            -q '"#\(.number) \(.title)\n← \(.headRefName) → \(.baseRefName) by \(.author.login)\ncreated: \(.createdAt[:10]), updated: \(.updatedAt[:10])\nreview: \(.reviewDecision // "PENDING"), draft: \(.isDraft)\n\n\(.body[:1000])\n\nReview comments (\(.reviews | length)):\n" + ([.reviews[] | select(.body != "") | "  [\(.state)] \(.author.login): \(.body[:300])"] | join("\n")) + "\n\nComments (\(.comments | length)):\n" + ([.comments[] | "  \(.author.login): \(.body[:300])"] | join("\n"))' \
            2>/dev/null || echo "(failed to fetch)"
        echo ""
    done
else
    echo "(none)"
fi
echo ""

# --- Active Branches ---
echo "=== Active Branches (remote, last 14 days) ==="
git fetch --prune origin 2>/dev/null || true
git for-each-ref --sort=-committerdate --format='%(refname:short) %(committerdate:short) %(committerdate:relative)' refs/remotes/origin/ 2>/dev/null | \
    head -20 | \
    while read -r branch date relative; do
        [ "$branch" = "origin/HEAD" ] && continue
        branch_epoch=$(date -j -f "%Y-%m-%d" "$date" "+%s" 2>/dev/null || date -d "$date" "+%s" 2>/dev/null || echo "0")
        cutoff_epoch=$(date -v-14d "+%s" 2>/dev/null || date -d "14 days ago" "+%s" 2>/dev/null || echo "0")
        if [ "$branch_epoch" -ge "$cutoff_epoch" ] 2>/dev/null; then
            echo "  $branch ($date, $relative)"
        fi
    done
echo ""

# --- Releases ---
echo "=== Releases ==="
gh release list --limit 3 --json tagName,publishedAt,isDraft,isPrerelease \
    -q '.[] | "\(.tagName) (published: \(.publishedAt[:10]), draft: \(.isDraft), prerelease: \(.isPrerelease))"' \
    2>/dev/null || echo "(none)"
echo ""

LATEST_TAG=$(gh release list --limit 1 --json tagName -q '.[0].tagName' 2>/dev/null || echo "")
if [ -n "$LATEST_TAG" ]; then
    UNRELEASED=$(git rev-list "$LATEST_TAG"..origin/master --count 2>/dev/null || echo "?")
    echo "Unreleased commits on master since $LATEST_TAG: $UNRELEASED"
else
    echo "No releases found"
fi
echo ""

# --- Failed Actions (with error logs) ---
echo "=== Failed Workflow Runs ==="

# Get recent failure run IDs on master
echo "--- master failures ---"
MASTER_FAIL_IDS=$(gh run list --branch master --status failure --limit 5 --json databaseId,workflowName,createdAt,headSha \
    -q '.[] | "\(.databaseId) \(.workflowName) \(.createdAt[:10]) \(.headSha[:8])"' 2>/dev/null || echo "")

if [ -n "$MASTER_FAIL_IDS" ]; then
    echo "$MASTER_FAIL_IDS" | while read -r run_id workflow date sha; do
        echo "Run $run_id: $workflow — $date commit:$sha"
    done
    echo ""

    # Fetch error logs for the most recent failure
    LATEST_FAIL_ID=$(echo "$MASTER_FAIL_IDS" | head -1 | awk '{print $1}')
    if [ -n "$LATEST_FAIL_ID" ]; then
        echo "--- Error log for most recent master failure (run $LATEST_FAIL_ID) ---"
        gh run view "$LATEST_FAIL_ID" --log-failed 2>/dev/null | tail -100 || echo "(could not fetch logs)"
        echo ""
    fi
else
    echo "(none)"
fi
echo ""

# Failures on current branch
if [ "$CURRENT_BRANCH" != "master" ] && [ "$CURRENT_BRANCH" != "detached" ]; then
    echo "--- $CURRENT_BRANCH failures ---"
    BRANCH_FAIL_IDS=$(gh run list --branch "$CURRENT_BRANCH" --status failure --limit 5 --json databaseId,workflowName,createdAt,headSha \
        -q '.[] | "\(.databaseId) \(.workflowName) \(.createdAt[:10]) \(.headSha[:8])"' 2>/dev/null || echo "")

    if [ -n "$BRANCH_FAIL_IDS" ]; then
        echo "$BRANCH_FAIL_IDS" | while read -r run_id workflow date sha; do
            echo "Run $run_id: $workflow — $date commit:$sha"
        done
        echo ""

        LATEST_BRANCH_FAIL_ID=$(echo "$BRANCH_FAIL_IDS" | head -1 | awk '{print $1}')
        if [ -n "$LATEST_BRANCH_FAIL_ID" ]; then
            echo "--- Error log for most recent $CURRENT_BRANCH failure (run $LATEST_BRANCH_FAIL_ID) ---"
            gh run view "$LATEST_BRANCH_FAIL_ID" --log-failed 2>/dev/null | tail -100 || echo "(could not fetch logs)"
            echo ""
        fi
    else
        echo "(none)"
    fi
    echo ""
fi

# Overall latest runs
echo "--- Latest workflow runs ---"
gh run list --limit 5 --json workflowName,status,conclusion,headBranch,createdAt \
    -q '.[] | "\(.workflowName) on \(.headBranch): \(.status)/\(.conclusion // "running") (\(.createdAt[:10]))"' \
    2>/dev/null || echo "(none)"
echo ""
