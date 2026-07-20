from __future__ import annotations

import sys
from pathlib import Path

from tracon import discovery


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: tracon_wrapper_alive.py <root>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1])
    pid = discovery.live_wrapper_pid(root)
    if pid is None:
        return 1
    print(pid)  # so a refusing caller can name the incumbent loop's pid
    return 0


if __name__ == "__main__":
    sys.exit(main())
