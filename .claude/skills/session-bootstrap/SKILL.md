---
name: session-bootstrap
description: Generate and maintain per-repo "project capsules" — concise architecture summaries that seed new sessions with rich project context. Use when starting work on an unfamiliar or large repo, resuming after a long break, or when context feels thin. Triggers on "bootstrap session", "generate project capsule", "seed context", "project overview", "create capsule", "refresh capsule".
---

# Session Bootstrap

Generate and maintain per-repo project capsules — structured architecture summaries that prime sessions with rich project context.

## What is a Project Capsule

A concise (<500 lines) markdown file at `.local/project-capsule.md` that captures:

- What the project does and why
- Where things live (component map)
- Rules that must not be violated (invariants)
- How data and control flow through the system
- What's actively being worked on

A capsule is a summary, not a dump. It includes pointers to deeper docs, not the docs themselves.

## Workflow

### 1. Scan for architecture signals

Read these sources (skip any that don't exist):

1. `AGENTS.md` / `CLAUDE.md` / `GEMINI.md` — agent instructions
2. `agent_docs/` — detailed project docs
3. `README.md` — project overview
4. `.local/prds/wip/` — active work context
5. Key config files: `package.json`, `Cargo.toml`, `pyproject.toml`, `go.mod`, etc.
6. Directory structure (top 2 levels)
7. Domain model files (models/, types/, schemas/, entities/)

### 2. Produce capsule

Write `.local/project-capsule.md` with this structure:

```markdown
# Project Capsule: {project name}

Generated: {date}

## Purpose

{1-2 lines: what this project does and why it exists}

## Stack

{language, framework, database, key dependencies — bullet list}

## Component Map

{what lives where — table or indented list}
{focus on src/ organization, key directories, entry points}

## Key Invariants

{5-10 domain rules, boundaries, data flow constraints}
{things an agent most often gets wrong without}

## Data Flow

{how requests/data move through the system}
{integration points, external services, event flows}

## Active Work

{current branch purpose, PRDs in wip/, recent focus areas}

## Deeper Docs

{pointers to agent_docs/, architecture docs, schema files}
{not the content — just where to find it}
```

### 3. Validate

- Capsule is < 500 lines
- Every section has content (or is explicitly marked N/A)
- Invariants are concrete rules, not vague principles
- Component map matches actual directory structure

### 4. Report

Summarize what was captured and flag any gaps (missing architecture docs, unclear boundaries, etc.).

## Refreshing a Capsule

When `.local/project-capsule.md` already exists:

1. Read existing capsule
2. Check what changed: new files, modified structure, different active PRDs
3. Update only stale sections
4. Bump the `Generated:` date

## Loading a Capsule

At session start, if `.local/project-capsule.md` exists, read it to prime context. No special action needed — just reading the file is enough.
