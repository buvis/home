# Depth Classification Guide

Classify every request across four dimensions. Each scores low, medium, or high.

## Dimensions

### 1. Requirement Clarity

How complete is the input?

| Score | Signal | Example |
|-------|--------|---------|
| Low | Just a pain point or aspiration | "I want better PRDs" |
| Medium | What + why stated, how unclear | "Add a hook that tracks costs per session using transcript data" |
| High | What + why + how + constraints | "Bash stop hook, reads transcript JSONL, sums tokens, appends to costs.jsonl" |

### 2. Scope Breadth

How many modules, files, or capabilities are affected?

| Score | Signal | Example |
|-------|--------|---------|
| Low | Single file or module | "Fix the cost calculation in track-cost.sh" |
| Medium | 2-4 modules, one capability area | "Add a new audit skill with hook and settings registration" |
| High | Cross-cutting, multiple capability areas | "Restructure how all skills share state" |

### 3. Codebase Impact

How much existing code is relevant?

| Score | Signal | Example |
|-------|--------|---------|
| Low | Greenfield, no existing code to integrate with | "Create a new standalone utility script" |
| Medium | Integrates with 1-2 existing components | "Add a skill that uses the existing autopilot state file" |
| High | Modifies multiple existing components or shared interfaces | "Change how skills communicate with hooks" |

### 4. Problem Complexity

Is the solution obvious, or are there competing approaches?

| Score | Signal | Example |
|-------|--------|---------|
| Low | Obvious solution, no real alternatives | "Add a .gitignore entry for dev/local/" |
| Medium | 2-3 viable approaches, tradeoffs are clear | "Monitor CI status - poll vs webhook vs GitHub Actions API" |
| High | Research needed, architectural implications, or no clear best path | "Integrate external development framework concepts into our pipeline" |

## Classification Rule

| Condition | Depth |
|-----------|-------|
| All four dimensions low | **Minimal** |
| Any dimension high | **Comprehensive** |
| Otherwise | **Standard** |

## Depth Summaries

### Minimal
- 0-2 questions, inline in conversation
- No brownfield analysis needed
- Output: ~30-line discovery doc
- Typical: clear single-capability features, bug fixes with known scope, config changes

### Standard
- 3-6 questions, stored in discovery file
- Brownfield analysis: scan for integration points and conventions
- Output: ~60-100-line discovery doc
- Typical: multi-capability features, skills that integrate with existing components

### Comprehensive
- 6-12 questions, stored in discovery file
- Full brownfield analysis: patterns, dependencies, conventions, integration surface
- Output: full discovery doc with codebase context and approach analysis
- Includes contradiction detection across answers
- Typical: architectural changes, vague/aspirational requests, framework integrations
