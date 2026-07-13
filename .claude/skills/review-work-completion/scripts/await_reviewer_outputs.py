#!/usr/bin/env python3
"""Hold a headless review session open until CLI reviewer outputs are complete.

Headless `claude -p` kills background Bash tasks ~5 seconds after the final
result (documented; only live subagents keep the process alive). The review
Watcher subagent runs this script in bounded foreground calls so the session
cannot end while codex/gemini/qwen reviewers are still writing.

A file is complete when it exists, is non-empty, and its mtime has been
stable for --stable seconds (CLI reviewers write their `-o` output at the
end; the quiet period guards streaming writers). Prints one status line per
file, then a final line: DONE when every file is complete, WAITING otherwise
(the Watcher re-runs while WAITING). Exit 0 for both outcomes; argparse
exits 2 on bad arguments.
"""

from __future__ import annotations

import argparse
import os
import time


def is_complete(path: str, stable_secs: float) -> bool:
    try:
        st = os.stat(path)
    except OSError:
        return False
    return st.st_size > 0 and (time.time() - st.st_mtime) >= stable_secs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--budget", type=float, default=100.0,
        help="max seconds this call blocks (keep well under the Bash tool "
             "timeout so the harness never auto-backgrounds the call)",
    )
    parser.add_argument("--poll", type=float, default=10.0)
    parser.add_argument(
        "--stable", type=float, default=30.0,
        help="mtime quiet period marking a file complete",
    )
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()

    deadline = time.time() + args.budget
    while True:
        pending = [f for f in args.files if not is_complete(f, args.stable)]
        remaining = deadline - time.time()
        if not pending or remaining <= 0:
            break
        time.sleep(max(0.1, min(args.poll, remaining)))

    for f in args.files:
        print(f"{'done' if f not in pending else 'pending'}\t{f}")
    print("DONE" if not pending else "WAITING")


if __name__ == "__main__":
    main()
