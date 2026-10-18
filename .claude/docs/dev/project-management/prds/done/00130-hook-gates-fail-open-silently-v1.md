# Policy hooks fail open silently, and one gate is bypassed three ways

Source: agoge product-QA run, `dev/local/audit-results/agoge-2026-08-17.md`, findings 18, 32 and
37 (accepted as one cluster) plus finding 31, all accepted in the 2026-08-17 walkthrough. Found
by heidi and trudy.

## Overview

### Problem Statement

The hook layer's guarantee is "we check before the tool runs". Four defects make that guarantee
conditional, and every one of them is silent.

1. **A handler that exits during import kills the chain.** `_invoke` catches `Exception`, but
   `_load_handler` runs `spec.loader.exec_module` and re-raises `BaseException`. A handler with a
   module-level `sys.exit(3)` routed ahead of a blocking one made the dispatcher exit 3; the
   blocking handler never ran and `dispatch.log` recorded nothing. A non-0/2 PreToolUse exit
   means the harness lets the call through.
2. **A timing-out policy handler is treated as "allowed".** The same blocking Write went from
   BLOCKED to ALLOWED as the payload crossed the 5 s cap: `_invoke` turns `HandlerTimeout` into
   `0`, and `_aggregate` only escalates to 2 when a handler *returns* 2.
3. **A pathological payload crashes the dispatcher before any handler runs.** `_parse_stdin`
   guards only `(ValueError, OSError)`, so deeply-nested JSON raises `RecursionError` and exits 1.
4. **A handler without `run()` executes twice.** `_load_handler` runs the module top level, then
   `_subprocess_fallback` runs the same script again — the docstring promises one subprocess.
5. **The PRD-location gate is bypassed three ways**, one of which actually lands a file in the
   forbidden directory: a symlink inside `dev/local/prds/` pointing at a root `backlog/`; a path
   with the allowed directory embedded as a substring; and a Bash `mv` with a double-quoted path.
   Causes: line 87 allow-lists any path merely *containing* `/dev/local/prds/`;
   `os.path.abspath` rather than `Path.resolve`, so symlinks are not followed; and a Bash regex
   requiring a start, space or `=` before `backlog|wip|done`, which a leading quote defeats.

Items 1-4 are latent or hard to trigger today — all 13 shipped handlers define `run()`, and a
500 kB tool payload is implausible — so they are defence in depth. Item 5 is not latent: a quoted
path in an `mv` is completely ordinary.

### Target Users

Every tool call in every session, and the working-documents rule that the PRD gate enforces.

### Success Metrics

- A handler that calls `sys.exit` at import is logged as a handler fault and the rest of the
  chain still runs.
- An **enforcement** handler that times out results in a blocked tool call, not an allowed one.
- A deeply-nested JSON payload degrades to `{}` and the handlers run their normal path.
- A handler script without `run()` is refused at load, not executed twice.
- All four PRD-location probes below are blocked, and the control still passes.

## Functional Decomposition

### Capability: the dispatcher cannot silently stop enforcing (findings 18, 32, 37)

Accepted option, the fuller one: catch `BaseException` around `_load_handler` (excluding
`HandlerTimeout`) and log it as a handler fault; widen `_parse_stdin` to include
`RecursionError`; drop the subprocess fallback so `run()` is required; **and** classify handlers
in `ROUTES` as enforcement or observer, with an enforcement handler that times out returning 2.

The classification is the load-bearing part: it buys the fail-closed guarantee without letting an
observer block work.

### Capability: the PRD gate matches paths, not substrings (finding 31)

Accepted option: `Path(file_path).resolve()`, re-derive the repo-relative head and require it to
be exactly `dev/local/prds`, and tokenize Bash commands with `shlex` instead of regex-matching
them. Three bypasses in one gate is a design problem, not three bugs.

## Structural Decomposition

- `hooks/dispatch.py` — `_load_handler`, `_invoke`, `_aggregate`, `_parse_stdin`, `ROUTES`
  (enforcement/observer classification), `_subprocess_fallback` (removed)
- `hooks/enforce_prd_location.py` — line 87's allow-list, the `abspath` call, the Bash matcher
- all 13 shipped handlers — verified to define `run()`; confirm before removing the fallback

## Implementation Phases

### Phase 1: the cheap holes (findings 18, 37, and half of 32)

1. `BaseException` around `_load_handler`, logged as a fault.
2. `RecursionError` in `_parse_stdin`'s guard.
3. Remove the subprocess fallback; require `run()` and fail loudly when it is missing.

### Phase 2: classify and fail closed (finding 32)

4. Add the enforcement/observer distinction to `ROUTES` and classify all 13 handlers.
5. An enforcement handler that times out aggregates to 2.

### Phase 3: the PRD gate (finding 31)

6. `resolve()`, exact-head anchoring, `shlex` tokenization.

*Acceptance:* every probe below flips from ALLOWED to BLOCKED, the control stays BLOCKED, and no
observer handler can block a tool call.

## Test Strategy

Verbatim evidence:

```
DISPATCHER EXIT CODE=3          # sys.exit(3)-at-import handler ahead of a blocking one
                                # blocking handler never ran; dispatch.log recorded nothing
```

```
 50000 rc=2 elapsed=0.27s BLOCKED
200000 rc=2 elapsed=2.74s BLOCKED
500000 rc=0 elapsed=5.08s ALLOWED TIMEOUT
stderr: [dispatch] enforce_prd_location: timed out

50000 rc=1 RecursionError    # {"tool_name":"Write","tool_input":[[[ ... ]]]}
```

```
_invoke returned: (0, '', '')
handler body executed 2 time(s)   <- docstring says it falls back to ONE subprocess
```

```
control-plain-root     rc=2 BLOCKED
symlink-through-prds   rc=0 ALLOWED   # .../dev/local/prds/sneak/00002-y.md, sneak -> /tmp/agoge_repo/backlog
substring-in-path      rc=0 ALLOWED   # .../backlog/dev/local/prds/00003-z.md
bash-doublequoted      rc=0 ALLOWED   # mv "backlog/00005.md" /tmp/
landed at: /private/tmp/agoge_repo/backlog/00002-y.md
```

## Risks

- **Fail-closed converts a silent hole into a visible outage.** A slow enforcement handler now
  blocks the user's work, and handler cost grows with payload size. This was accepted knowingly;
  the observer classification is what bounds the blast radius.
- **A handler classified wrongly** either blocks when it should not, or keeps failing open. The
  classification of all 13 handlers is the review-critical part of this PRD.
- **Catching `BaseException` also swallows `KeyboardInterrupt`** unless handled explicitly, and it
  lets the dispatcher continue past a handler that deliberately tried to stop everything.
- **`resolve()` adds a syscall to every Write and Bash**, on the same hot path where a slow
  handler now fails closed — so this PRD makes latency matter more than it did.
- **`resolve()` behaves differently for a path that does not exist yet**, and legitimate writes
  through a symlinked repo root could break.
- **`shlex` on arbitrary command strings has its own failure modes** for commands that do not
  parse.
