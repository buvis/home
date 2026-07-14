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
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--wrapper-pid", type=int)
    args = parser.parse_args()

    if args.preflight:
        import importlib

        importlib.import_module("rich")
        importlib.import_module("textual")
        return 0

    try:
        if args.once:
            return screens.run_once(args.root)

        loops = discovery.discover_loops()
        return screens.run_app(loops, args.root, wrapper_pid=args.wrapper_pid)
    except KeyboardInterrupt:
        return 130

if __name__ == "__main__":
    sys.exit(main())
