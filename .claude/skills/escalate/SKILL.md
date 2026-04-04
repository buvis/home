---
name: escalate
description: Escalate to Opus when Sonnet hits a known-hard task or struggle detection fires. Triggers on "/escalate", or when the enforce-escalation hook blocks you.
---

# Escalate to Opus

You are being asked to escalate a task to Opus. Dispatch an Opus subagent using the Agent tool.

## Required Input

Before dispatching, you MUST have:
1. **Trigger type** - one of the types below
2. **Objective** - what you are trying to accomplish
3. **Context** - relevant file paths, error messages, what you already tried

If you were blocked by the enforce-escalation hook, the block message contains the suggested trigger type and active signals. Use those.

## Trigger Types

### Take-over triggers (Opus does the work)

**planning** - Opus writes the implementation plan.
Prompt Opus: "You are writing an implementation plan. [objective]. [context]. Write the complete plan."

**brainstorming** - Opus runs the brainstorming/design process.
Prompt Opus: "You are designing a solution. [objective]. [context]. Explore approaches, propose a design, and present it."

**code-review** - Opus reviews code.
Prompt Opus: "You are reviewing code changes. [objective]. [context]. Review for correctness, security, performance, and maintainability. Report findings by severity."

**debugging** - Opus debugs and fixes the problem.
Prompt Opus: "You are debugging a problem. [objective]. [context]. Identify the root cause and implement the fix."

**struggle-repeated-failure** - Opus fixes what Sonnet couldn't.
Prompt Opus: "Sonnet was unable to complete this task after multiple attempts. [objective]. [context]. The following struggle signals were detected: [signals]. Analyze why previous attempts failed, identify the root cause, and implement the correct fix."

### Advisory triggers (Opus advises, Sonnet continues)

**architecture** - Opus analyzes architecture.
Prompt Opus: "You are analyzing the architecture of this codebase. [objective]. [context]. Provide analysis and specific, actionable guidance. Do not implement changes."

**struggle-no-progress** - Opus diagnoses the situation.
Prompt Opus: "Sonnet has been working on this task without making progress. [objective]. [context]. The following struggle signals were detected: [signals]. Diagnose what is going wrong and provide a corrected approach with specific steps to follow."

## How to Dispatch

Use the Agent tool with these parameters:
- `model`: `"opus"`
- `description`: Short description of what the Opus agent will do
- `prompt`: Built from the template above, with [objective], [context], and [signals] filled in

Example:

```
Agent tool call:
  model: "opus"
  description: "Debug failing auth test"
  prompt: "You are debugging a problem. Objective: fix the auth integration test that fails with 'token expired' after the session refactor. Context: The test at tests/auth/test_session.py::test_refresh_token has failed 3 times. Changes were made to src/auth/session.py (edited 4 times). Error: AssertionError - expected 200, got 401. Previous attempts tried extending token TTL and adding retry logic. Identify the root cause and implement the correct fix."
```

## After Opus Returns

- **Take-over triggers**: Accept the result. Continue your work from where Opus left off.
- **Advisory triggers**: Follow the guidance. Implement the suggested approach yourself.
