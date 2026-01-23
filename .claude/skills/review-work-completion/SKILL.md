---
name: review-work-completion
description: Review completed work against PRD requirements and create follow-up tasks
---

# Review Work Completion

Multi-LLM review of completed tasks against PRD requirements.

## Prerequisites

**Stop immediately if any task is `in_progress`**. Review only after all active work is complete.

## Workflow

### 1. Check task status

Use `TaskList` to get all tasks. Output status table:

| ID | Title | Status |
|----|-------|--------|
| 1 | ... | done |

If ANY task is `in_progress`: **STOP**. Report which tasks are active and wait.

### 2. Read PRD source

Read all PRDs from `.local/prds/wip/`:

```bash
ls -1 .local/prds/wip/
```

Extract from each PRD:
- Success criteria
- Acceptance criteria per task
- Required features

### 3. Gather context for reviewers

Prepare review context:
- List of completed tasks with descriptions
- Relevant code changes (git diff against main/master)
- PRD requirements summary

Store in a temp file for agents:

```bash
# Create review context
cat > /tmp/review-context.md << 'EOF'
## Completed Tasks
{task list with descriptions}

## Code Changes
{git diff summary or key files changed}

## PRD Requirements
{extracted requirements}
EOF
```

### 4. Run three-agent review

Launch **Alice**, **Bob**, and **Carl** in parallel using `Task` tool.

#### Alice (Claude)

```
Task tool with subagent_type=general-purpose:

Review the completed work in this codebase against the PRD requirements.

Context: {review-context.md contents}

Check each dimension:
- Plan compliance: Does implementation match task descriptions?
- PRD coverage: Are all requirements addressed?
- Code quality: Follows patterns, readable, maintainable?
- Tests: Adequate coverage, edge cases?
- Security: No obvious vulnerabilities?

Output format - list issues as:
[ALICE] [{severity}] {description} | File: {path} | Task: {ID}

Severity: Critical, High, Medium, Low
```

#### Bob (Codex)

```bash
./scripts/codex-run.sh "Review the completed work against these requirements:

{review-context.md contents}

Check: plan compliance, PRD coverage, code quality, tests, security.

Output each issue as:
[BOB] [{severity}] {description} | File: {path} | Task: {ID}

Severity: Critical, High, Medium, Low"
```

If Codex fails (non-zero exit or auth error):
- Log: `⚠️ Bob (Codex) unavailable: {error}`
- Continue with remaining agents

#### Carl (Copilot)

```bash
copilot "Review the completed work against these requirements:

{review-context.md contents}

Check: plan compliance, PRD coverage, code quality, tests, security.

Output each issue as:
[CARL] [{severity}] {description} | File: {path} | Task: {ID}

Severity: Critical, High, Medium, Low"
```

If Copilot fails:
- Log: `⚠️ Carl (Copilot) unavailable: {error}`
- Continue with remaining agents

### 5. Consolidate findings

Parse all agent outputs and merge:

1. **Normalize issues** - Match similar issues across agents by file+description similarity
2. **Score by consensus**:
   - 🔴 **3 agents** - highest priority
   - 🟠 **2 agents** - high priority
   - 🟡 **1 agent** - normal priority
3. **Deduplicate** - Keep best description, note which agents found it

Output consolidated table:

| Priority | Severity | Issue | File | Found By |
|----------|----------|-------|------|----------|
| 🔴 | Critical | XSS in input handler | src/input.ts | Alice, Bob, Carl |
| 🟠 | High | Missing null check | src/api.ts | Alice, Bob |
| 🟡 | Medium | No test coverage | src/utils.ts | Carl |

### 6. Document findings

For each consolidated issue:

```
- [{consensus-priority}] [{severity}] {description}
  - File: {path}
  - Task: {task ID}
  - PRD ref: {section if applicable}
  - Found by: {agent list}
```

### 7. Create follow-up tasks

Create tasks using `TaskCreate`, prioritizing multi-agent consensus:

**Rules**:
- Process 🔴 (3-agent) issues first
- Then 🟠 (2-agent) issues
- Then 🟡 (1-agent) issues
- Max 10 tasks (batch overflow into "Misc fixes")
- Group by theme
- Tag complexity: `(S)` small, `(M)` medium, `(L)` large

**Task description format**:
```
Fix: {issue summary}

Issues addressed:
- {issue 1}
- {issue 2}

Found by: {agents}
Consensus: {🔴/🟠/🟡}

Acceptance criteria:
- [ ] {criterion 1}
- [ ] {criterion 2}
```

### 8. Save review PRD

If follow-up tasks created:
- Location: `.local/prds/wip/{original-prd-name}-review01.txt`
- Increment number for subsequent reviews
- Include agent availability status

## Output Format

```
## Review Summary

Reviewed: {N} completed tasks
PRDs checked: {list}

### Agent Status
- Alice (Claude): ✅ Available
- Bob (Codex): ✅ Available | ⚠️ Unavailable: {reason}
- Carl (Copilot): ✅ Available | ⚠️ Unavailable: {reason}

## Consolidated Findings

### 🔴 Multi-Agent Consensus (3/3)
- [Critical] {issue} | {file} | Found by: Alice, Bob, Carl

### 🟠 Partial Consensus (2/3)
- [High] {issue} | {file} | Found by: Alice, Bob

### 🟡 Single Agent
- [Medium] {issue} | {file} | Found by: Carl

## Follow-up Tasks Created

1. {task title} (S/M/L) - 🔴 consensus - addresses X, Y
2. {task title} (S/M/L) - 🟠 consensus - addresses Z
```

## Reference Files

- `references/review-dimensions.md` - Detailed review checklist
- `references/issue-template.md` - Issue documentation format
- `references/agent-prompts.md` - Full prompts for each agent
