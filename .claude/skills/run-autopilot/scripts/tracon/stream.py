"""Live session-log follower: LogTail, SessionUsage, AgentTracker, render_line.

Reads `last-session.log` incrementally across the wrapper's per-session
in-place truncations (and rarer inode swaps), accumulates token/cost usage,
tracks parallel subagent/background-task lanes, and renders each parsed
event via the shared render_stream module. Read-only observer: never
writes a file, never signals a loop, never mutates state.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rich.text import Text

from .model import TAIL_BYTES

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # skills/run-autopilot/scripts
import render_stream

render_stream._color_enabled = True  # module-level ANSI switch; output re-parsed via Text.from_ansi

LANE_COLORS = ("magenta", "blue", "green", "yellow", "red", "bright_cyan")


@dataclass
class Lane:
    task_id: str  # task_started.task_id — the lifecycle key
    tool_use_id: str  # task_started.tool_use_id — equals the agent's parent_tool_use_id
    label: str  # task_started.description, trimmed to 20 chars
    color: str
    kind: str  # "local_agent" | "local_bash" (task_started.task_type)
    last: str = ""  # last_tool_name, straight off task_progress (agents only)
    n: int = 0  # usage.tool_uses, straight off task_progress (agents only)
    done: bool = False  # retired by task_updated/task_notification status, or by its tool_result


class LogTail:
    """Follow a file across the wrapper's per-session in-place truncations."""

    def __init__(self, path: Path, tail_bytes: int = TAIL_BYTES) -> None:
        self.path = path
        self.tail_bytes = tail_bytes
        self.session_start: float | None = None
        self._fh: Any = None
        self._ino: int | None = None
        self._buf = b""
        self._attached = False
        self._saw_missing = False

    def _close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                pass
        self._fh = None
        self._buf = b""

    def _open(self, ino: int) -> bool:
        try:
            self._fh = self.path.open("rb")
        except OSError:
            self._fh = None
            return False
        self._ino = ino
        self._buf = b""
        return True

    def read_new(self) -> tuple[list[str], bool]:
        """Return (new complete lines, session_reset)."""
        try:
            st = self.path.stat()
        except OSError:
            was_open = self._fh is not None
            self._close()
            if was_open:
                self.session_start = time.time()
            self._saw_missing = True
            return [], was_open

        reset = False
        if self._fh is None:
            first_attach = not self._attached and not self._saw_missing
            if not self._open(st.st_ino):
                return [], False
            self._attached = True
            if first_attach:
                self.session_start = None
                offset = max(0, st.st_size - self.tail_bytes)
                if offset:
                    self._fh.seek(offset)
                    try:
                        chunk = self._fh.read()
                    except OSError:
                        chunk = b""
                    self._buf = chunk.partition(b"\n")[2]  # discard the partial first line
            else:
                reset = True
                self.session_start = time.time()
        elif st.st_ino != self._ino:  # atomic rename: new inode, old fd now points at nothing
            self._close()
            if not self._open(st.st_ino):
                return [], True
            reset = True
            self.session_start = time.time()
        elif st.st_size < self._fh.tell():  # truncated in place: tee reopened for a new session
            self._fh.seek(0)
            self._buf = b""
            reset = True
            self.session_start = time.time()

        try:
            data = self._fh.read()
        except OSError:
            return [], reset
        if data:
            self._buf += data
        if b"\n" not in self._buf:
            return [], reset
        *complete, self._buf = self._buf.split(b"\n")
        lines = [c.decode("utf-8", errors="replace") for c in complete]
        return lines, reset


class SessionUsage:
    """Live token totals and cost; dedupes assistant events by message id."""

    def __init__(self) -> None:
        self._by_msg: dict[str, dict[str, Any]] = {}
        self._last: dict[str, Any] = {}
        self.model = ""
        self.session_cost = 0.0

    def reset(self) -> None:
        self._by_msg.clear()
        self._last = {}
        self.model = ""
        self.session_cost = 0.0

    def feed(self, event: dict[str, Any]) -> None:
        etype = event.get("type")
        if etype == "system" and event.get("subtype") == "init":
            self.model = str(event.get("model") or "")
            return
        if etype == "result":
            # sessions emit one result event PER re-invoke, each carrying the
            # cumulative conversation cost — latest wins
            cost = event.get("total_cost_usd")
            if isinstance(cost, (int, float)) and not isinstance(cost, bool):
                self.session_cost = float(cost)
            return
        if etype != "assistant":
            return
        msg = event.get("message") or {}
        usage, mid = msg.get("usage"), msg.get("id")
        if isinstance(usage, dict) and isinstance(mid, str):
            self._by_msg[mid] = usage
            self._last = usage

    def totals(self) -> tuple[int, int, int]:
        up = cached = out = 0
        for u in self._by_msg.values():
            up += (u.get("input_tokens") or 0) + (u.get("cache_creation_input_tokens") or 0)
            cached += u.get("cache_read_input_tokens") or 0
            out += u.get("output_tokens") or 0
        return up, cached, out

    def context_size(self) -> int:
        u = self._last
        return (
            (u.get("input_tokens") or 0)
            + (u.get("cache_read_input_tokens") or 0)
            + (u.get("cache_creation_input_tokens") or 0)
        )


class AgentTracker:
    """Attribute parallel work: subagent lanes and background-task lanes."""

    def __init__(self) -> None:
        self._by_task: dict[str, Lane] = {}
        self._by_tool: dict[str, Lane] = {}

    def reset(self) -> None:
        self._by_task.clear()
        self._by_tool.clear()

    def _register(self, *, task_id: str, tool_use_id: str, label: str, kind: str) -> Lane:
        color = LANE_COLORS[len(self._by_task) % len(LANE_COLORS)]
        lane = Lane(task_id=task_id, tool_use_id=tool_use_id, label=label, color=color, kind=kind)
        self._by_task[task_id] = lane
        self._by_tool[tool_use_id] = lane
        return lane

    _TERMINAL_STATUSES = frozenset({"completed", "failed", "stopped", "killed"})

    def _retire_by_task_id(self, task_id: Any, status: Any) -> None:
        lane = self._by_task.get(str(task_id))
        if lane is not None and status in self._TERMINAL_STATUSES:
            lane.done = True

    def _apply_background_tasks(self, tasks: Any) -> None:
        """tasks[] is the CURRENT SET of running background tasks; liveness
        is membership — an absent task_id (including an empty list) retires."""
        if not isinstance(tasks, list):
            tasks = []
        alive: set[str] = set()
        for item in tasks:
            if not isinstance(item, dict):
                continue
            task_id = str(item.get("task_id") or "")
            if not task_id:
                continue
            alive.add(task_id)
            if task_id not in self._by_task:
                kind = str(item.get("task_type") or "local_bash")
                label = str(item.get("description") or task_id)[:20]
                self._register(task_id=task_id, tool_use_id=task_id, label=label, kind=kind)
        for task_id, lane in self._by_task.items():
            if lane.kind == "local_bash" and task_id not in alive:
                lane.done = True

    def _feed_system(self, event: dict[str, Any]) -> None:
        sub = event.get("subtype")
        if sub == "task_started":
            task_id = str(event.get("task_id"))
            tool_use_id = str(event.get("tool_use_id"))
            description = event.get("description")
            subagent_type = event.get("subagent_type")
            label = str(description or subagent_type or f"agent{len(self._by_task) + 1}")[:20]
            kind = str(event.get("task_type") or "")
            self._register(task_id=task_id, tool_use_id=tool_use_id, label=label, kind=kind)
        elif sub == "task_progress":
            lane = self._by_task.get(str(event.get("task_id")))
            if lane is not None:
                lane.last = str(event.get("last_tool_name") or "")
                lane.n = int((event.get("usage") or {}).get("tool_uses") or 0)
        elif sub == "task_updated":
            self._retire_by_task_id(event.get("task_id"), (event.get("patch") or {}).get("status"))
        elif sub == "task_notification":
            self._retire_by_task_id(event.get("task_id"), event.get("status"))
        elif sub == "background_tasks_changed":
            self._apply_background_tasks(event.get("tasks"))

    def _feed_assistant(self, event: dict[str, Any]) -> None:
        parent = event.get("parent_tool_use_id")
        if not parent:
            return
        parent = str(parent)
        if parent not in self._by_tool:
            label = f"agent{len(self._by_task) + 1}"
            self._register(task_id=parent, tool_use_id=parent, label=label, kind="local_agent")

    def _feed_user(self, event: dict[str, Any]) -> None:
        content = (event.get("message") or {}).get("content")
        if not isinstance(content, list):
            return
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                lane = self._by_tool.get(str(block.get("tool_use_id")))
                if lane is not None:
                    lane.done = True

    def feed(self, event: dict[str, Any]) -> None:
        etype = event.get("type")
        if etype == "system":
            self._feed_system(event)
        elif etype == "assistant":
            self._feed_assistant(event)
        elif etype == "user":
            self._feed_user(event)

    def tag_for(self, event: dict[str, Any] | None) -> tuple[str, str] | None:
        if not event:
            return None
        parent = event.get("parent_tool_use_id")
        if not parent:
            return None
        lane = self._by_tool.get(str(parent))
        if lane is None:
            return None
        return lane.label, lane.color

    def live_lanes(self) -> list[Lane]:
        return [lane for lane in self._by_task.values() if lane.kind == "local_agent" and not lane.done]

    def live_tasks(self) -> list[Lane]:
        return [lane for lane in self._by_task.values() if lane.kind == "local_bash" and not lane.done]


def render_line(raw: str, event: dict[str, Any] | None) -> list[Text]:
    """Render an already-parsed event; fail open to the raw line on any error."""
    if event is None:
        return [Text(raw)]
    try:
        rendered = render_stream.render(event)
    except Exception:
        return [Text(raw)]
    return [Text.from_ansi(line) for line in rendered]
