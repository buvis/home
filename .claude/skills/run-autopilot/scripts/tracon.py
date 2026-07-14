# /// script
# requires-python = ">=3.11"
# dependencies = ["rich>=13", "textual>=1.0,<9"]
# ///

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tracon import discovery, screens

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    try:
        if args.once:
            return screens.run_once(args.root)

        loops = discovery.discover_loops()
        return screens.run_app(loops, args.root)
    except KeyboardInterrupt:
        return 0

if __name__ == "__main__":
    sys.exit(main())
