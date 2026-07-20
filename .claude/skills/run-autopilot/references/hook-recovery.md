# Hook-layer recovery runbook

When the hook layer degrades, ~13 hooks fail at once and every one fails open
(silently). This is the "python3 broke, now what" reference (PRD 00086 R1).

## Symptom: python3 is broken (mise upgrade, venv drift, PATH change)

Every hook is `python3 <script>`; a broken interpreter fails all of them
silently (they exit non-zero, the harness treats it as non-blocking). The
diagnostic tools (validate, audit) need the same interpreter, so they break
too. Signs: gateguard/warden/aegis stop firing, no cartographer injections,
no cost rows.

### 1. Confirm it

```bash
python3 -c "print('ok')"
```

Non-zero or no output = the interpreter is the problem. `mise which python3`
resolves the managed one; `mise reshim` if a shim is missing.

### 2. Work without hooks (recovery only)

```bash
claude --no-hooks
```

`--no-hooks` disables ALL hooks for the session. **Caveat: this also drops
warden and aegis** — no command filtering, no fact-forcing gate, no
prefer-tools routing. Use it only to repair the interpreter, never for normal
work. Re-enable by restarting `claude` without the flag once step 1 passes.

### 3. Where hook stderr lands when hooks degrade

- Per-hook stderr surfaces in the session's hook-error lines (the harness
  prints a `PreToolUse:... hook error` on a blocking failure; non-blocking
  failures are swallowed).
- Hooks that log to disk: `~/.claude/hooks/*.log` (e.g. `notify.log`,
  `dispatch.log` if the consolidator has landed). A metrics hook that cannot
  write prints `<hook>: write failed (...)` to stderr.
- Headless autopilot: the wrapper tees the whole session to
  `dev/local/autopilot/last-session.log` — grep it for `hook error`.

## Prevention wired into autoclaude

`autoclaude` runs an interpreter preflight (`python3 -c 'print()'`) before the
batch launch and refuses to start the loop if it fails, naming the fix
(`mise reshim`). A batch never launches onto a broken interpreter that would
silently disable every enforcement hook.

## settings.json backup-before-edit convention

`settings.json` drives every hook registration; a bad edit that leaves it
unparseable disables the whole hook block. Before editing it — via
`update-config`, a manual edit, or any automated flow — snapshot it first:

```bash
cp ~/.claude/settings.json ~/.claude/settings.json.bak
```

Then edit, and verify it still parses:

```bash
jq -e . ~/.claude/settings.json
```

Non-zero exit = restore from the `.bak` before continuing. The buvis history
is the durable rollback; the `.bak` is the fast in-place one.
```
