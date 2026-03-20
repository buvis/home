---
name: watch-ci
description: Monitor CI status after push or PR creation. Polls GitHub Actions until completion, summarizes failures, optionally triggers debugging. Triggers on "watch ci", "check ci", "ci status", "wait for ci", "are checks passing", "monitor build".
---

# Watch CI

Poll GitHub Actions after push/PR creation until completion. Summarize results.

## Workflow

### 1. Identify the run

Determine the relevant workflow run:

```bash
gh run list --branch $(git branch --show-current) --limit 5 --json databaseId,status,conclusion,workflowName,createdAt,headSha
```

Pick the most recent run matching the current branch HEAD:

```bash
git rev-parse HEAD
```

If no run found yet (just pushed), wait 10 seconds and retry once.

### 2. Poll until completion

Check status every 30 seconds:

```bash
gh run view {run-id} --json status,conclusion,workflowName
```

| Status | Action |
|--------|--------|
| `queued` / `in_progress` | wait 30s, poll again |
| `completed` | proceed to step 3 |

Timeout after 15 minutes. If still running, report status and stop polling.

### 3. Handle result

**On success (`conclusion: success`):**
- Report "CI passed" and move on

**On failure (`conclusion: failure`):**
1. Get failed jobs:
   ```bash
   gh run view {run-id} --json jobs --jq '.jobs[] | select(.conclusion == "failure") | {name, conclusion}'
   ```
2. Get failure logs:
   ```bash
   gh run view {run-id} --log-failed
   ```
3. Summarize: which jobs failed, key error lines
4. If `superpowers:systematic-debugging` is available, offer to invoke it on the failure

**On cancellation:**
- Report and stop

### 4. Notify (if configured)

If `NTFY_URL` and `NTFY_TOPIC` are set in environment, send notification:

```bash
curl -s -d "CI {conclusion} for {branch}" ${NTFY_URL}/${NTFY_TOPIC}
```

## Error Handling

| Situation | Action |
|-----------|--------|
| `gh` not authenticated | Stop with message |
| No GitHub remote | Stop with message |
| No workflow runs found | Report "no CI configured" |
| Rate limited | Increase poll interval to 60s |
| Timeout (15min) | Report current status, stop polling |
