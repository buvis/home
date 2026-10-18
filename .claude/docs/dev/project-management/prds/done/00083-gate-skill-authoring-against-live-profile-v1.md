# 00083 - Gate skill authoring against the live permission/hook profile

## Problem

The 2026-07-19 authoring audit (dev/local/audit-results/2026-07-19-authoring-efficiency-audit.md) found ~14 confirmed cases of layer self-sabotage: skills instructing commands our own hooks deny (bare grep, pipes to head/tail, find, cd-chains, shell-variable assignments), and two playbooks that assumed a persistent shell and could not work at all. Every case shipped because nothing checks a skill's commands against the environment they will run in. The defects were fixed by hand; the class is still open.

## Goal

A skill cannot ship (new or edited) with commands the live profile would block. Authoring-time gate, not runtime recovery.

## Requirements

- R1: create-skill gains a "dry-run under the live profile" step: every fenced `bash` command in the SKILL.md is checked against (a) aegis prefer_tools deny patterns (grep/find/cat/head/tail incl. pipes, chains, subshells), (b) shell-variable-assignment prefixes, (c) `cd` chains, (d) bare-path invocations whose first token is not an allowlisted permission prefix (compare against ~/.claude/settings.json allow list), (e) `$VAR` placeholders outside a documented substitution rule.
- R2: The check is code, not model judgment: extend the create-skill validator (the canonical copy) with these lints; violations are ERRORs with the replacement named (rg -n, rg --files, uv run --directory, python3 prefix, inline-the-path).
- R3: create-skill's authoring flow and extract-plugin's phase 8 both run the extended validator; extract-plugin documents the vendored-copy re-sync rule (vendor from create-skill at extraction time, never edit the vendored copy).
- R4: brush gains a "promote load-bearing memories" step: scan the project's auto-memory for feedback/project entries that name a skill or its scripts, and propose promoting the operational fact into the skill body (the audit found three such stragglers: bare-repo review fallback, codex exit-4 salvage, gemini -d symlink flag - all promoted by hand today).
- R5: autoclaude exports CLAUDE_UNATTENDED=1 (alongside WARDEN_UNATTENDED) so the shared unattended contract (skills/run-autopilot/references/unattended-contract.md, created 2026-07-19) has its detection signal wired; document the requirement for any future headless launcher (cron, /schedule).

## Acceptance

- A SKILL.md containing `foo | head -5`, `F=/tmp/x` + `rm -rf $F`, `cd x && y`, or a bare unallowlisted script path fails validation with the named replacement.
- All 36 existing personal skills pass the extended validator (fix any stragglers the new lints surface).
- brush run on ~/.claude proposes zero promotions immediately after this PRD lands (steady state).
- `rg -n "CLAUDE_UNATTENDED" ~/.config/bash/plugins/development.plugin.bash` hits in the autoclaude function.

## Out of scope

- Plugin-side validator/release changes (claude-checkup PRD 00001 in that repo).
- Rewriting skills beyond what the new lints flag.

## Notes

Audit report section "Omitted edges, Tier 1" items E1/E3/E4/E5-personal. E2 (audit-authoring dimensions) is claude-checkup product work.
