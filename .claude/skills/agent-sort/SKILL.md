---
name: agent-sort
description: Use when a project needs a trimmed Claude install instead of the full global setup, sorting skills/rules/hooks into DAILY vs LIBRARY with repo evidence. Triggers on "agent sort", "trim skills for repo", "daily vs library", "project install plan".
---

# Agent Sort

Use this skill when a repo needs a project-specific surface instead of the default full global install.

The goal is not to guess what "feels useful." The goal is to classify components with evidence from the actual codebase.

## When to Use

- A project only needs a subset of the global setup and the full install is too noisy
- The repo stack is clear, but nobody wants to hand-curate skills one by one
- You need to separate always-loaded daily workflow surfaces from searchable library/reference surfaces
- A repo has drifted into the wrong language, rule, or hook set and needs cleanup

## Non-Negotiable Rules

- Use the current repository as the source of truth, not generic preferences
- Every DAILY decision must cite concrete repo evidence
- LIBRARY does not mean "delete"; it means "keep accessible without loading by default"
- Do not install hooks, rules, or scripts that the current repo cannot use
- Prefer the existing global install surface; do not introduce a second install system

## Outputs

Produce these artifacts in order:

1. DAILY inventory
2. LIBRARY inventory
3. install plan
4. verification report
5. optional `skill-library` router if the project wants one

## Classification Model

Use two buckets only:

- `DAILY`
  - should load every session for this repo
  - strongly matched to the repo's language, framework, workflow, or operator surface
- `LIBRARY`
  - useful to retain, but not worth loading by default
  - should remain reachable through search, router skill, or selective manual use

## Evidence Sources

Use repo-local evidence before making any classification:

- file extensions
- package managers and lockfiles
- framework configs
- CI and hook configs
- build/test scripts
- imports and dependency manifests
- repo docs that explicitly describe the stack

Useful commands include:

```bash
rg --files
rg -n "typescript|react|next|supabase|django|spring|flutter|swift"
cat package.json
cat pyproject.toml
cat Cargo.toml
cat pubspec.yaml
cat go.mod
```

## Parallel Review Passes

Dispatch parallel subagents (Agent tool with subagent_type=Explore) to split the review into these passes:

1. Skills — classify entries under `~/.claude/skills/` and any plugin-provided skills
2. Commands — classify entries under `~/.claude/commands/`
3. Rules — classify entries under `~/.claude/rules/`
4. Hooks and scripts — classify hook surfaces in `settings.json`, MCP health checks, helper scripts in `~/.claude/hooks/`
5. Extras — classify MCP configs, templates, and reference docs in `~/.claude/dev/local/`

If subagents are not available, run the same passes sequentially.

## Core Workflow

### 1. Read the repo

Establish the real stack before classifying anything:

- languages in use
- frameworks in use
- primary package manager
- test stack
- lint/format stack
- deployment/runtime surface
- operator integrations already present

### 2. Build the evidence table

For every candidate surface, record:

- component path
- component type
- proposed bucket
- repo evidence
- short justification

Use this format:

```text
skills/frontend-patterns | skill | DAILY   | 84 .svelte files, svelte.config.js | core frontend stack
skills/python-patterns   | skill | LIBRARY | no .py files, no pyproject.toml    | not active in this repo
rules/web/*              | rules | DAILY   | package.json + svelte.config.js    | active web repo
rules/rust/*             | rules | LIBRARY | zero Rust source files              | keep accessible only
```

### 3. Decide DAILY vs LIBRARY

Promote to `DAILY` when:

- the repo clearly uses the matching stack
- the component is general enough to help every session
- the repo already depends on the corresponding runtime or workflow

Demote to `LIBRARY` when:

- the component is off-stack
- the repo might need it later, but not every day
- it adds context overhead without immediate relevance

### 4. Build the install plan

Translate the classification into action:

- DAILY skills → keep enabled in `~/.claude/skills/`, or symlink/copy into the project's `.claude/skills/`
- DAILY rules → reference only matching language/framework rule sets in CLAUDE.md
- DAILY hooks/scripts → keep only compatible ones in `settings.json`
- LIBRARY surfaces → keep accessible through search, on-demand invocation, or a `skill-library` router

If the project already has a `.claude/` directory with selective installs, update that plan instead of creating another system.

### 5. Create the optional library router

If the project wants a searchable library surface, create:

- `.claude/skills/skill-library/SKILL.md`

That router should contain:

- a short explanation of DAILY vs LIBRARY
- grouped trigger keywords
- where the library references live

Do not duplicate every skill body inside the router.

### 6. Verify the result

After the plan is applied, verify:

- every DAILY file exists where expected
- stale language rules were not left active
- incompatible hooks were not installed
- the resulting install actually matches the repo stack

Return a compact report with:

- DAILY count
- LIBRARY count
- removed stale surfaces
- open questions

## Handoffs

If the next step is interactive settings/hook installation, hand off to:

- `update-config`

If the next step is overlap cleanup or catalog review, hand off to:

- `audit-skills`

If the next step is broader context trimming, hand off to:

- `audit-context`

## Output Format

Return the result in this order:

```text
STACK
- language/framework/runtime summary

DAILY
- always-loaded items with evidence

LIBRARY
- searchable/reference items with evidence

INSTALL PLAN
- what should be installed, removed, or routed

VERIFICATION
- checks run and remaining gaps
```
