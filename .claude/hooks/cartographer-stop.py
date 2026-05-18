"""PostToolUse hook: mark atlas stale when files are modified.

Fires on Write, Edit, MultiEdit; writes staleness.flag with an ISO 8601 UTC
timestamp to the project's atlas directory. Exits 0 silently on any error so
it never crashes the host tool.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude" / "hooks"))

from _lib_cartographer import atlas_dir, project_hash

_WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit"})


def main() -> None:
    try:
        data = json.load(sys.stdin)
        tool_name = data.get("tool_name", "")
        if tool_name not in _WRITE_TOOLS:
            return
        tool_input = data.get("tool_input") or {}
        file_path = tool_input.get("file_path") or tool_input.get("path")
        cwd = str(Path.cwd()) if file_path is None else str(Path(file_path).parent)
        h, _name, _remote = project_hash(cwd)
        atlas_path = atlas_dir(h)
        atlas_path.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat()
        (atlas_path / "staleness.flag").write_text(ts, encoding="utf-8")
    except Exception:
        return


if __name__ == "__main__":
    main()
