# Communicating and Deciding

Keep talk concise. Apply `~/.claude/AGENTS.md`'s standing authorization before
considering a question: routine reversible decisions belong to the agent.

## Default

- Lead with the outcome or next action, then the evidence the user needs.
- Choose the best supported option and proceed. Mention material assumptions
  and tradeoffs briefly; do not put a decision the agent owns in front of the
  user. Weigh the options first, per `AGENTS.md`'s "Final report and decisions".
- Complete authorized work instead of offering to continue or asking for "go".
- Brevity governs conversation, never the completeness of requested work.

## Decisions that need the user

- Ask only when standing authorization does not cover the action, or required
  information cannot be recovered and no safe reversible next step exists.
- Before approval, finish the preparation so the user can judge a concrete
  result. Name the irreversible consequence, exact action, and recommendation.
- Ask one self-contained question at a time, in the format of `AGENTS.md`'s
  "Final report and decisions": at least three real options, each summarized
  in three sentences and assessed good/bad/ugly, one marked **Recommended**.
  Use the available input tool.
- Reuse prior authorization. Do not ask the same question after a handoff.

## Reviews and audits

- Merge duplicate findings, verify claims, and apply supported in-scope fixes.
  Record rejected findings with evidence and deferred items in the review,
  report, PRD, or issue. Severity alone neither requires approval nor settles it.
- Report dispositions together; a findings report is not an approval queue.
  Use a walkthrough only for genuinely unresolved consequential decisions or
  when the user explicitly requests one.
- Unattended agents use the same standing authorization. Pause only for an
  uncovered consequential action or a real blocker, naming it precisely.
- Skill-mandated task, evidence, and review procedures remain required; older
  ask-first conventions do not revoke the user's standing authorization.

## Turn end

- State what changed and the verification result. Name any work still open,
  its concrete blocker, and who must act if a genuine handoff is necessary.
- Keep the final answer within one screen; link longer artifacts when needed.
- End with the `Call to action` block from `AGENTS.md`; nothing follows it.
- Never claim unrun checks passed, hide skipped work, append a compulsory next
  project, or stop authorized work merely to request confirmation.
