# Paid-for reviews are discarded and failed alerts report success

Source: agoge product-QA run, `dev/local/audit-results/agoge-2026-08-17.md`, findings 6 (HIGH)
and 21 + 44 (MEDIUM + LOW, accepted as one cluster), all accepted in the 2026-08-17
walkthrough. Found by heidi and trudy.

## Overview

### Problem Statement

Two subsystems throw away work and then report that nothing went wrong.

**The codex review runner discards completed reviews.** It decides a review failed by searching
the whole event stream — including the reviewer's own command arguments and the finding prose it
just wrote — for "quota", "rate limit" or "usage limit". So a review *of* billing or
rate-limiting code classifies itself as an API limit. Worse, `return 4` at line 579 precedes the
`review_out.write_text` at 580-584, so the completed review is never written and the caller pays
for a second one. This confirms memory `project_codex_review_run_exit4_false_positive.md` is
still live at HEAD; a full review has already had to be salvaged by hand from
`codex-review-last.jsonl`.

**The notify path loses messages three ways and reports success.** `notify.py --send` exits 0
whether or not delivery happened — against an unreachable port, on HTTP 403, and on a failing
desktop path, the only trace is a line in `notify.log`. Separately, a project path containing a
carriage return makes the stdlib reject the header (correctly — header injection does **not**
succeed, the boundary holds), but `send_ntfy`'s `except (URLError, TimeoutError, OSError)` does
not catch `ValueError`, so the notification is dropped, swallowed to rc 0 under dispatch, and the
standalone `__main__` path crashes. `autoclaude` uses exactly this call for its loop-exit alert,
and the code's own comment blames this for the unannounced loop death on 2026-07-12.

The third way notify loses messages — the dead bash stub in the test suite — is PRD 00129.

### Target Users

Every review cycle that touches security, billing or rate-limiting code, and the operator
relying on push notifications to learn that a batch ended.

### Success Metrics

- A review whose findings mention "quota" or "rate limit" completes, is written to
  `codex-review-output.md`, and does **not** exit 4.
- A genuine usage-limit event still exits 4, and the output written before the return is kept.
- `notify.py --send` exits non-zero when both delivery paths fail.
- A project path containing a carriage return still delivers a notification, with a sanitized
  title, and never crashes the standalone hook.

## Functional Decomposition

### Capability: a finished review survives its own classifier (finding 6)

Accepted option: scope the marker scan to codex's **own error event types**, never to
`exec_command_*` argv or agent prose, **and** write `review_out` before the exit-4 return. Both
halves — the misclassification and the data loss.

### Capability: an undelivered alert says so (findings 21, 44)

Accepted option: return a bool from both delivery paths and exit non-zero from `--send` when
both fail; add `ValueError` to `send_ntfy`'s except clause; and sanitize the title through the
existing `_header_safe` RFC-2047 path so the notification goes out cleaned rather than vanishing.

## Structural Decomposition

- `skills/run-autopilot/scripts/codex_review_run.py` — the classifier and the line-579/580 order
- `hooks/notify.py` — `send_ntfy`'s except clause, `_header_safe`, the `--send` exit code, the
  desktop path

## Implementation Phases

### Phase 1: the review runner (finding 6)

1. Move the `review_out.write_text` above the `return 4` — the data-loss half, correct on its
   own even if the scan work is reverted.
2. Restrict the marker scan to codex's error event types.

### Phase 2: the notify path (findings 21, 44)

3. Bool returns from both delivery paths; non-zero `--send` exit when both fail.
4. `ValueError` in the except clause; title sanitized through `_header_safe`.

*Acceptance:* the six classifier shapes below produce the right verdicts, and a stubbed codex
emitting a quota-mentioning finding leaves `codex-review-output.md` on disk.

## Test Strategy

Verbatim evidence — the classifier probe is a table of six real event shapes:

```
reviewer greps for the word quota   -> signals_failure=True
finding prose mentions quota        -> signals_failure=True
finding prose mentions rate limit   -> signals_failure=True
file path contains quota            -> signals_failure=True
genuinely clean                     -> signals_failure=False
real usage limit                    -> signals_failure=True
```

```
stub codex emits: "Finding 1: the quota check in billing.py is unbounded. Verdict: REWORK." exit 0
exit: 4
⚠ codex_review: codex FAILED — usage-limit/error event, total 0s (caller should fall back)
codex-review-output.md exists? False
```

```
EXIT CODE: 0     stdout: ''    stderr: ''
--- notify.log ---
[01:04:28] CLI --send: agoge probe / unreachable-host test
[01:04:28] ERROR: Failed to send notification (exit code: URLError)
```

```
ValueError: Invalid header value b'Claude [evil\r\nX-Agoge-Injected: yes]: waiting'
  ... notify.py:353 urllib.request.urlopen(req)
  (sink received no second request — notification dropped)
```

Tests: the classifier returns `False` for the four benign shapes and `True` for the real limit
event; the runner writes its output on the exit-4 path; `--send` against a closed port exits
non-zero; a `cwd` containing `\r` sends with a sanitized title and does not raise.

## Risks

- **Scoping the scan depends on codex's event vocabulary**, which comes from an upstream tool and
  can change; a genuine usage-limit event whose type is not on the list would be missed. The
  write-before-return change is what makes that survivable — nothing is lost, only re-run.
- **A non-zero exit from a notify hook may surprise callers.** Whether anything consumes it is
  unverified; if the wrapper ignores it, the code is honest and nothing observable changes.
- **The notify path runs at every session end**, so a mistake there is paid every session.
- **A sanitized title may be less informative** for non-ASCII project paths that render fine
  today.
