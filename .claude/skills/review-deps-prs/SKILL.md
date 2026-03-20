---
name: review-deps-prs
description: Review dependency update PRs across all repos. Lists open dependency PRs (Renovate, Dependabot, manual), groups by severity, and supports individual or batch merge. Triggers on "review deps", "review dependency prs", "check dep updates", "dependency prs", "dep updates".
---

# Review Dependency PRs

List, triage, and act on dependency update PRs across all accessible repos.

## Workflow

### 1. Gather PRs

Run the discovery script:

```bash
~/.claude/skills/review-deps-prs/scripts/list-dep-prs.sh
```

This discovers repos via `gh repo list` and finds dependency PRs by:
- **Author**: renovate[bot], dependabot[bot]
- **Title pattern**: starts with "chore(deps):", "fix(deps):", "bump", "update", "[security]"

### 2. Classify into tiers

Group each PR into one of three tiers:

| Tier | Criteria | Priority |
|------|----------|----------|
| **Security** | Has "security" label, CVE in title, or "[security]" prefix | Highest — review first |
| **Major** | Semver major version bump (title contains major version change) | Medium — breaking changes possible |
| **Minor/patch** | Everything else | Lowest — usually safe |

### 3. Present summary

Present grouped results to the user:

```
## Security (N PRs)
- [repo] #123: title (age)

## Major (N PRs)
- [repo] #456: title (age)

## Minor/Patch (N PRs)
- [repo] #789: title (age)
```

Include PR age (days since created) to highlight stale PRs.

If no dependency PRs found, say so and stop.

### 4. Offer actions

After presenting the summary, offer:

1. **Merge individual** — "merge [repo]#123"
2. **Batch merge by tier** — "merge all minor/patch" or "merge all security"
3. **Approve individual** — "approve [repo]#123"
4. **Skip** — move on without action

### 5. Execute actions

For each merge:
```bash
gh pr merge --repo {repo} {number} --squash
```

For each approve:
```bash
gh pr review --repo {repo} {number} --approve
```

Report results (success/failure) for each action.

## Error Handling

| Situation | Action |
|-----------|--------|
| `gh` not authenticated | Stop with message |
| No repos found | Stop with message |
| PR merge fails (CI not passing, conflicts) | Report failure, continue with remaining |
| Rate limited | Report and stop |
