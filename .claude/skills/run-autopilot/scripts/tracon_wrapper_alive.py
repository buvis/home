from __future__ import annotations

import sys
from pathlib import Path

from tracon import discovery


def main() -> int:
    root = Path(sys.argv[1])
    return 0 if discovery.wrapper_alive(root) else 1


if __name__ == "__main__":
    sys.exit(main())
