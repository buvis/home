"""macOS memory pressure headroom check.

Reads ``kern.memorystatus_vm_pressure_level`` via ``sysctl`` and reports whether
the host currently has memory headroom. Called by the ``/work`` step-3 routing
table's memory gate to decide whether dispatching qwen (a local, memory-hungry
model) is safe right now.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

SYSCTL_KEY = "kern.memorystatus_vm_pressure_level"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check macOS memory pressure headroom.", exit_on_error=False
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
        print(f"unknown: {e}")
        return 2

    try:
        result = subprocess.run(
            ["sysctl", "-n", SYSCTL_KEY],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            print(f"unknown: failed to read {SYSCTL_KEY}: {result.stderr.strip()}")
            return 2
        level = int(result.stdout.strip())
    except Exception as e:
        print(f"unknown: failed to read {SYSCTL_KEY}: {e}")
        return 2

    if level <= args.max_level:
        print(f"ok: pressure level {level} <= {args.max_level}")
        return 0

    print(f"pressure: level {level} > {args.max_level}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
