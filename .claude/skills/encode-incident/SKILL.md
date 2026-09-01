---
name: encode-incident
description: Use when turning an incident just survived, or an old memory that never got its guard decision, into an invariant - causal chain, a memory, and a guard argued to a bar. Run it with /encode-incident; it never fires on its own.
disable-model-invocation: true
compatibility: "Claude-specific; sweeps Claude's own hook surface (settings.json, hooks/dispatch.py ROUTES, plugin hooks.json, warden.yaml) and writes to the Claude auto-memory plane. Porting: no."
---

# Encode an Incident as an Invariant

One incident in, one package out: a causal chain, a memory (always), and a guard
proposal that either clears a written bar or is dropped with its reason recorded.

Scope v1: meta and loop incidents - the autopilot stack, the hooks, the wrapper,
the machine. Manual only. Guards are proposed, never installed.

## Dependencies

- `~/.claude/rules-library/rationalizations.md` - appended to when the gap was
  discipline; read by `~/.claude/hooks/cartographer-echo.py` (see Step 5 for what
  that hook does and does not surface).
- `~/.claude/projects/<project>/memory/` plus its `MEMORY.md` - the memory plane.
  Homed and committed per `~/.claude/rules/memory.md`; the frontmatter shape
  comes from the bundled template and the live memory files, not from that rules
  file.
- `~/.buvis` bare repo (work-tree `$HOME`) - where the `rationalizations.md` edit
  is committed.

## Step 1: Reconstruct the chain

Build five links from facts this session already established: trigger ->
mechanism -> missing check -> why it was missing -> root cause. Reconstruct; do
not interview.

Mark the **least confident** link - usually the one whose answer is history
rather than evidence (why a check was never added, what an earlier decision
assumed). Ask exactly one question, about that link, and nothing else.

If the task text already answers that link, or the session is unattended, skip
the question and say which link went unverified. Then proceed.

## Step 2: Sweep the hook locations

Read `${CLAUDE_SKILL_DIR}/references/hook-locations.md` and run the enumeration
command each of its six locations carries. Output: the set of locations that
exist right now.

If a command fails, say so and let any guard proposal that would have named that
location fail. Never name a location you did not read.

## Step 3: Argue the guard, or drop it

A proposal is presented only if it answers all four:

1. What does it catch that a memory cannot?
2. What does it cost on every call?
3. What is its own failure mode?
4. Does it fail open or closed?

Missing one answer: not presented. Reject before presenting when the proposal
names a location outside the Step 2 set, or relies on `PostToolUse` to gate -
`PostToolUse` exit 2 cannot block. `PreToolUse` and `Stop` both can.

Where the incident is testable, offer a failing repro test with the proposal; it
stays optional - mandatory ceremony is what stops the ritual being performed at
all.

Whether proposed or dropped, the verdict and its one-line reason go into the
memory in Step 4.

## Step 4: Write the memory (always)

Every run writes a memory, guard or no guard. Fill
`${CLAUDE_SKILL_DIR}/assets/incident-memory-template.md`.

- **Where**: the memory directory the harness names for the current session.
  Never compute the project hash by hand - the encoder replaces `.` as well as
  `/`, and hand-encoding it is what produced 13 phantom directories nothing ever
  read. A meta or loop incident encoded from another repo belongs in the
  `~/.claude` project store, not that repo's.
- **Filename**: `feedback_<snake_case_slug>.md`, matching the plane's convention.
- **Type**: `feedback` - guidance with a why. Never `project`; `distil-memory`
  owns that type and neither skill rewrites the other's.
- **Body**: the compact chain (marking the least confident link) and the
  guard-verdict line. The root cause, not the narrative. A few lines, readable
  without opening another file.
- **Pointer**: append to `MEMORY.md` as
  `- [feedback_<slug>.md](feedback_<slug>.md) — <one-line hook>`, matching the
  filename-as-link-text form 69 of 70 entries use.

Write these without asking - one reversible file each - then commit them to the
cellar repo (`~/git/src/github.com/buvis/cellar`, which `~/.claude/projects`
symlinks into). Nothing else is written without approval.

## Step 5: Record a rationalization, if the gap was discipline

Only when the incident happened because a known step was skipped, not because a
mechanism was missing.

Insert one entry into `~/.claude/rules-library/rationalizations.md`, immediately
**before** the `## Synonyms-to-grep` heading so it stays inside `## Excuses`:

```markdown
### "the excuse, in the voice that used it"

- **Why it's wrong**: <what the excuse costs, concretely>
- **Counter-action**: <the specific thing to do instead>
- **Triggers**: <comma-separated terms that substring-match the symbol names this excuse shows up around>
```

Then commit it to the home repo, staging by explicit absolute path (never
`commit -a`, which sweeps the user's dirty files):

```bash
git --git-dir=$HOME/.buvis --work-tree=$HOME add ':(top).claude/rules-library/rationalizations.md'
git --git-dir=$HOME/.buvis --work-tree=$HOME commit -m "docs(rules): record <excuse> rationalization"
```

The entry is live on arrival: Echo's deny messages cite the first catalog entry
(file order) whose **Triggers** terms match a duplicate symbol, so an appended
entry is reachable through its own triggers with no code change (PRD 00157).
An entry without a Triggers bullet is still read by humans and `/architect`
prompts but is never auto-cited - always include the bullet.

## Retroactive mode

Given an existing memory file instead of a session: same package, same steps.
The input memory is **updated in place** - chain and guard verdict inserted above
the existing `**Why:**` line. No second file. `MEMORY.md` changes only if the
description changed. Refresh `metadata.modified` if the file carries it.

Leave the existing `metadata.type` alone, including a `project` memory's:
appending a chain does not make it this skill's memory.

One memory at a time. Never a bulk pass over the plane - that produces exactly
the guard proliferation the bar exists to prevent.

If the memory already carries a rejected-guard line, the rerun **is** the
recurrence marker: re-propose the guard and record the second occurrence.

## Invariant

No auto-fire: this skill is absent from `~/.claude/hooks/dispatch.py` `ROUTES`
and from every plugin `hooks.json`, and carries `disable-model-invocation: true`.
Keep it that way.
