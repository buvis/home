Filename: `feedback_<snake_case_slug>.md` in the session's memory directory.

---
name: feedback-<short-kebab-slug>
description: "<one line: the rule, and the incident it came from>"
metadata:
  node_type: memory
  type: feedback
  originSessionId: <this session's id, if known>
  modified: <ISO-8601 UTC; set on every edit, including a retroactive one>
---

<The invariant, stated as an instruction. One or two sentences.>

**Chain:** <trigger> -> <mechanism> -> <missing check> -> <why it was missing>
-> <root cause>. Least confident link: <which one, and why>.

**Guard:** <proposed: event + location + what it catches> | <rejected: one-line
reason> | <installed: path>.

**Why:** <what actually happened - the incident, dated, with the concrete cost.>

**How to apply:** <what a future session should do differently, concretely.>

Related: [[other-memory-name]].
