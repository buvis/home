# Unattended-Session Contract

Shared contract for skills that may run headless (autopilot, cron, any
`claude -p` launcher). Skills cite this file instead of restating the rules.

## Detection

- Unattended = the environment variable `CLAUDE_UNATTENDED=1` is set. Nothing
  else counts: never infer unattendedness from a missing TTY, the session
  name, or user silence. Attended is the default.
- `autoclaude` exports it for every loop session. Any other headless launcher
  (cron, /schedule, custom wrappers) MUST export it too, or the session is
  treated as attended and may deadlock on a question.
- `WARDEN_UNATTENDED=1` is the warden-specific analog (its ask-to-deny gate);
  autoclaude sets both.

## Rules (unattended sessions)

1. **Never ask.** Do not call `AskUserQuestion` or otherwise wait for a human.
2. **Take the documented default.** Every decision point a skill marks with a
   default takes that default; log it as `defaulted:<decision>` in the step's
   output, report, or review file so the human can audit the choices later.
3. **Retry cap.** A failing command or dispatch is retried at most 2 times.
   After the second failed retry, mark the step FAILED, quote the captured
   stderr in the report, and continue per the calling skill's failure path.
   Never loop "until it works".
4. **Scope questions stop the step, not the session.** A question that would
   change scope (ambiguous requirement, destructive choice with no documented
   default) is written verbatim into the report or stall artifact; the
   affected step ends as FAILED/stalled, and the session continues wherever
   the calling skill allows.
5. **Fail loud.** A defaulted decision, a skipped step, or a FAILED step must
   never read as a clean success (`rules/fail-loud.md`).

## For skill authors

Where your skill asks a question or retries a command, add one line:
"Unattended (`CLAUDE_UNATTENDED=1`): follow
`~/.claude/skills/run-autopilot/references/unattended-contract.md`" plus your
documented defaults. This contract governs the how; your skill owns which
defaults exist.
