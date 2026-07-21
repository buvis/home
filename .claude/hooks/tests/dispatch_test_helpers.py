"""Shared helpers for hooks/tests/test_dispatch.py and
hooks/tests/test_handler_run_parity.py.
"""

from __future__ import annotations

import contextlib
import functools
import types


@contextlib.contextmanager
def require_in_process_work(mod, who: str):
    """Witness that `mod.run(payload)` did the handler's real work IN THIS PROCESS.

    THE ORACLE HOLE this closes differs slightly by caller. In
    test_handler_run_parity.py the assertions compare an in-process leg
    against a subprocess leg, so a `run()` that just re-execs its own script -
    `subprocess.run([sys.executable, __file__], input=json.dumps(payload),
    ...)` - reproduces the exit code, stdout, stderr AND every side-effect
    file BY CONSTRUCTION, because it is literally the same program the
    expected leg runs; no output-based comparison can tell it apart. In
    test_dispatch.py there is no subprocess leg to compare against - the
    helper is the ONLY thing establishing that the handler's work happened in
    this process at all. Either way the same defect is fatal: PRD 00071 exists
    to REMOVE the per-hook fork/exec, and a re-execing `run()` is strictly
    SLOWER than the code it replaces (fork/exec paid twice against a target of
    one python spawn per pre/post hook).

    Denying spawns BY NAME cannot close it: the interpreter is trivially
    hidden behind a one-line `/bin/sh` shim (or a renamed interpreter), where
    argv inspection sees only the shim path. So this oracle is POSITIVE
    instead - the handler module's own entry point is wrapped with a
    recorder, and `run()` must make it fire. A child process cannot touch the
    parent's module object, so EVERY subprocess-shaped run() leaves the
    recorder unfired regardless of how the child is launched. A no-op
    `return (0, "", "")` leaves it unfired too.

    Because it witnesses work instead of policing spawns, a handler's own
    legitimate child processes still run: review_coverage_hook delegates to
    check_review_file.py via `python3`, enforce_prd_location shells out to
    `git rev-parse`. That is pre-existing handler work, not dispatcher
    overhead.

    Applied to the IN-PROCESS leg only; a subprocess leg must of course spawn.
    """
    own = {
        name: obj
        for name, obj in vars(mod).items()
        if isinstance(obj, types.FunctionType) and name != "run"
    }
    # `main` is the documented entry point of every handler script; when a module
    # has one, only IT counts as the work witness (a trivial helper must not
    # stand in for the handler's real work). Otherwise fall back to any of the
    # module's own functions.
    targets = {"main": own["main"]} if "main" in own else own
    assert targets, f"{who}: module exposes no work function to witness"
    fired: list[str] = []

    def recorder(name, real):
        @functools.wraps(real)
        def wrapper(*args, **kwargs):
            fired.append(name)
            return real(*args, **kwargs)

        return wrapper

    for name, real in targets.items():
        setattr(mod, name, recorder(name, real))
    try:
        yield fired
    finally:
        for name, real in targets.items():
            setattr(mod, name, real)
