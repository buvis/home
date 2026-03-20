#!/bin/bash
# List dependency update PRs across all repos the authenticated user has access to
# Detects by author (renovate[bot], dependabot[bot]) and title patterns

set -e

# Get all repos for user's orgs and personal account
REPOS=$(gh repo list --limit 200 --json nameWithOwner --jq '.[].nameWithOwner' 2>/dev/null)

if [ -z "$REPOS" ]; then
    echo "No repos found or gh not authenticated"
    exit 1
fi

echo "=== Dependency Update PRs ==="
echo ""

for REPO in $REPOS; do
    PRS=$(gh pr list --repo "$REPO" --state open --json number,title,author,labels,createdAt,url \
        --jq '.[] | select(
            (.author.login == "renovate[bot]" or .author.login == "dependabot[bot]") or
            (.title | test("^(chore\\(deps\\)|bump |update |\\[security\\])"; "i")) or
            (.title | test("^fix\\(deps\\)"; "i"))
        )' 2>/dev/null) || continue

    if [ -n "$PRS" ]; then
        echo "--- $REPO ---"
        echo "$PRS"
        echo ""
    fi
done
