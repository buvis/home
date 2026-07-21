"""macOS memory pressure notification level check.

Reads ``kern.memorystatus_vm_pressure_level`` via ``sysctl`` and reports the
host's current memory pressure notification level (1 normal, 2 warning, 4
critical). Called by the ``/work`` step-3 routing table's memory gate to
decide whether dispatching qwen (a local, memory-hungry model) is safe right
now.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

SYSCTL_KEY = "kern.memorystatus_vm_pressure_level"


def _collapse_to_one_line(text: str) -> str:
    return " ".join(text.split())


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check macOS memory pressure notification level.", exit_on_error=False
    )
    parser.add_argument(
        "--max-level",
        type=int,
        default=1,
        help="Highest pressure level still considered healthy (default: 1).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
    except argparse.ArgumentError as e:
        print(f"unknown: {_collapse_to_one_line(str(e))}")
        return 2
    except SystemExit as e:
        if e.code == 0:
            raise
        print("unknown: invalid arguments")
        return 2

    try:
        result = subprocess.run(
            ["sysctl", "-n", SYSCTL_KEY],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            print(f"unknown: failed to read {SYSCTL_KEY}: {_collapse_to_one_line(result.stderr)}")
            return 2
        level = int(result.stdout.strip())
    except Exception as e:
        print(f"unknown: failed to read {SYSCTL_KEY}: {_collapse_to_one_line(str(e))}")
        return 2

    if level <= args.max_level:
        print(f"ok: pressure level {level} <= {args.max_level}")
        return 0

    print(f"pressure: level {level} > {args.max_level}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
