"""Terminal screens for tracon: dashboard and detail view.

Implements the Collector for per-tick I/O and Textual screens for the app.
"""

from __future__ import annotations

import json
import os
import signal
import time
from pathlib import Path
from typing import Any, TYPE_CHECKING

from rich.panel import Panel
from rich.text import Text

from . import discovery, model, panels
from .stream import AgentTracker, LogTail, SessionUsage, render_line

if TYPE_CHECKING:
    from textual.app import App


LOG_KEEP = 5000
DETAIL_TICK = 0.5
FLEET_TICK = 2.0
THEME_FILE = Path.home() / ".claude" / "tracon-theme"

# Rendered label discovery.classify() uses for each terminal loop-metrics
# signal -- reused verbatim for the wrapper-dead loop-exit banner. A signal
# missing from this map (e.g. a stale non-terminal "continue" left by a
# prior session) falls back to "stopped" rather than being echoed verbatim.
_SIGNAL_LABELS = {"done": "drained", "died": "died", "paused": "paused"}

# Operator runbook per exit label. "stopped" covers both an operator pause
# (marker consumed, no row written) and a killed wrapper — state is intact
# either way, so the same next step holds.
_NEXT_STEPS = {
    "drained": "backlog empty — nothing queued.",
    "paused": "needs a decision: `claude` → /run-autopilot answers the blocker, then `autoclaude`.",
    "died": "check dev/local/autopilot/last-session.log, then rerun `autoclaude`.",
    "stopped": "state intact — rerun `autoclaude` to continue the batch.",
}


def _final_signal_label(root: Path | None) -> str:
    """Classify a wrapper-dead loop exit, state.json first.

    The wrapper's operator-pause and memory-pressure exits append NO new
    loop-metrics row, so the last metrics row on disk can be a stale PRIOR
    session's non-terminal signal (e.g. "continue"). state.json reflects the
    CURRENT, authoritative loop state and wins for the two cases it can
    prove outright (drained via empty next_phase, paused via its markers).
    For everything else -- including a genuinely terminal exit where
    state.json still shows the in-flight phase -- fall back to the last
    metrics row's signal.
    """
    if root is None:
        return "stopped"
    state = model.read_state(root / "dev" / "local" / "autopilot" / "state.json")
    if not state.exists:
        return "stopped"
    if state.next_phase == "":
        return "drained"
    if state.phase == "paused" or "pause_reason" in state.raw or "cap_pause_reason" in state.raw:
        return "paused"
    autopilot_dir = root / "dev" / "local" / "autopilot"
    rows = model.read_metrics(autopilot_dir / "loop-metrics.jsonl")
    last = model.last_row(rows)
    signal = last.signal if last is not None else ""
    return _SIGNAL_LABELS.get(signal, "stopped")


class Collector:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._autopilot = root / "dev" / "local" / "autopilot"
        self._tail = LogTail(self._autopilot / "last-session.log")
        self._usage = SessionUsage()
        self._tracker = AgentTracker()

    @property
    def tracker(self) -> AgentTracker:
        return self._tracker

    def bash_output_notes(self, now: float | None = None) -> dict[str, str]:
        """Liveness note per live bash lane, from statting its -o file: the
        runners tee CLI stdout there (gemini/copilot, grows live) or write it
        at completion (native codex), so size+age is the best available
        signal. Keyed by task_id; lanes without a parsed -o path get none."""
        if now is None:
            now = time.time()
        notes: dict[str, str] = {}
        for lane in self._tracker.live_tasks():
            if not lane.out_path:
                continue
            try:
                st = Path(lane.out_path).stat()
            except OSError:
                waited = model.fmt_dur(max(0.0, now - lane.started))
                notes[lane.task_id] = f"no output yet · {waited}"
                continue
            if st.st_size == 0:
                # tee creates the file at launch; empty means nothing landed
                # yet (or the CLI buffers stdout), not "stalled since launch"
                waited = model.fmt_dur(max(0.0, now - st.st_mtime))
                notes[lane.task_id] = f"no output yet · {waited}"
                continue
            age = model.fmt_dur(max(0.0, now - st.st_mtime))
            notes[lane.task_id] = f"out {panels.fmt_tok(st.st_size)} · {age} ago"
        return notes

    def poll(self) -> tuple[list[str], bool]:
        return self._tail.read_new()

    def feed(self, raw: str) -> tuple[dict[str, Any] | None, list[Text]]:
        try:
            event = json.loads(raw)
        except (ValueError, RecursionError):
            return None, render_line(raw, None)

        if not isinstance(event, dict):
            return None, render_line(raw, None)

        self._usage.feed(event)
        self._tracker.feed(event)

        # render_stream already lane-tags subagent events with ⟨label⟩;
        # prefixing our own tag doubled it (two truncated labels per line).
        return event, render_line(raw, event)

    def reset_session(self) -> None:
        self._usage.reset()
        self._tracker.reset()

    def snapshot(self) -> tuple[model.LoopState, list[model.MetricsRow], discovery.Status, tuple[int, int]]:
        state = model.read_state(self._autopilot / "state.json")
        rows = model.read_metrics(self._autopilot / "loop-metrics.jsonl", state.batch_id)
        try:
            log_mtime: float | None = (self._autopilot / "last-session.log").stat().st_mtime
        except OSError:
            log_mtime = None

        now = time.time()
        status = discovery.classify(state, rows, log_mtime, now)
        counts = model.prd_counts(self.root)
        return state, rows, status, counts

    def head(self) -> tuple[Panel, int]:
        state, rows, status, counts = self.snapshot()
        log_path = self._autopilot / "last-session.log"
        try:
            log_mtime: float | None = log_path.stat().st_mtime
        except OSError:
            log_mtime = None
        wrapper = discovery.wrapper_alive(self.root)
        now = time.time()
        status = discovery.limit_wait_status(status, log_path, log_mtime, wrapper, now)
        last = model.last_row(rows)
        status = discovery.orphan_status(
            status, state, wrapper, last.ts_end if last is not None else None, log_mtime, now
        )
        status = discovery.pause_pending_status(status, self.root, wrapper)
        agents = panels.agents_row(self._tracker)
        panel = panels.build_head(
            state=state,
            rows=rows,
            usage=self._usage,
            status=status,
            prd_counts=counts,
            batch_id=state.batch_id,
            root_name=self.root.name,
            session_start=self._tail.session_start,
            agents=agents,
        )
        return panel, panels.head_rows(agents)


def build_app(roots: list[Path], forced: Path | None = None, wrapper_pid: int | None = None) -> App:
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal, VerticalScroll
    from textual.widgets import DataTable, RichLog, Static, Footer
    from textual.screen import Screen
    from textual.binding import Binding

    wrapper_root = forced if forced is not None else (roots[0] if roots else None)

    def _stop_loop(screen: Any, root: Path) -> None:
        """Interrupt the registered wrapper's process group — the same
        `kill -INT -pid` the wrapper's own ctrl+c handler sends. Guarded by
        a double press (screen-local arm window)."""
        pid = discovery.live_wrapper_pid(root)
        if pid is None:
            screen.app.notify(f"no live autoclaude for {root.name} — nothing to stop")
            return
        now = time.monotonic()
        if now >= getattr(screen, "_confirm_kill_until", 0.0):
            screen._confirm_kill_until = now + 3.0
            screen.app.notify(
                f"s stops the {root.name} loop NOW — press s again to confirm",
                severity="warning",
            )
            return
        try:
            os.killpg(pid, signal.SIGINT)
        except OSError as exc:
            screen.app.notify(f"stop failed: {exc}", severity="error")
            return
        screen.app.notify(f"interrupt sent — {root.name} loop tearing down")

    def _touch_pause_marker(app: App, root: Path) -> None:
        try:
            (root / "dev" / "local" / "autopilot" / "pause-requested").touch()
        except OSError as exc:
            app.notify(f"pause-requested write failed: {exc}", severity="error")
            return
        app.notify("pause requested — pauses when the current session ends; resume with `autoclaude`")

    HELP_TEXT = """\
tracon — autoclaude loop observer

UI keys (never touch a loop)
  enter     open the highlighted loop
  esc       back (detail → all loops; help/tasks/agents → close)
  t         task board: kanban lanes over the loop's task plan
  a         agent board: subagent and background-CLI lanes with live activity
  f         follow — log auto-scrolls to the newest lines
  q         quit tracon; every loop keeps running (ctrl+c does the same)
  ctrl+p    command palette (themes — the choice persists)

Loop keys (act on the attached / highlighted loop)
  p         request pause — honored at the session boundary; resume: autoclaude
  s         stop NOW — interrupts that loop's process group (press twice)

Status legend
  ● live         session writing within the last 20s
  ◐ quiet        session running but output has stalled
  ⏳ limit-wait  usage limit hit; the wrapper sleeps until the reset
  ⏸ paused       loop stopped for a decision — claude → /run-autopilot → autoclaude
  ⚠ orphaned    work queued but no autoclaude alive — run autoclaude
  ⚠ attention   needs_attention set (usually a cap-pause)
  ■ died         session died; check dev/local/autopilot/last-session.log
  ✔ drained      backlog empty; batch archived
  ○ idle/no log  nothing running

Numbers
  task 4/8        4 of 8 tasks completed; ▸ names the one in flight
  cycle 1/3       review-rework cycle vs its cap
  batch <stamp>   sessions/elapsed/active/cost all cover this batch
  ctx x/500.0k    last turn's context vs the session-rotation cap
  in/cache/out    input, cache-read and output tokens this session

esc or ? closes this help.
"""

    class HelpScreen(Screen):
        BINDINGS = [
            Binding("escape", "app.pop_screen", "Close"),
            Binding("question_mark", "app.pop_screen", "Close"),
        ]

        def compose(self) -> ComposeResult:
            yield VerticalScroll(Static(HELP_TEXT))
            yield Footer()

    class TasksScreen(Screen):
        """On-demand task detail: kanban lanes over the state.tasks snapshot."""

        BINDINGS = [
            Binding("escape", "app.pop_screen", "Back to log"),
            Binding("t", "app.pop_screen", "Back to log"),
        ]

        def __init__(self, root: Path) -> None:
            super().__init__()
            self.root = root

        def compose(self) -> ComposeResult:
            yield Static(id="tasks-head")
            with Horizontal():
                for lane in model.LANES:
                    yield VerticalScroll(Static(id=f"lane-{lane}"))
            yield Footer()

        def on_mount(self) -> None:
            self.refresh_tasks()
            self.set_interval(FLEET_TICK, self.refresh_tasks)

        def refresh_tasks(self) -> None:
            state = model.read_state(
                self.root / "dev" / "local" / "autopilot" / "state.json"
            )
            self.query_one("#tasks-head", Static).update(
                panels.tasks_head(state, self.root.name)
            )
            lanes = model.tasks_by_lane(state)
            for lane in model.LANES:
                self.query_one(f"#lane-{lane}", Static).update(
                    panels.lane_body(lane, lanes[lane])
                )

    class AgentsScreen(Screen):
        """On-demand agent detail: this session's subagent and background-CLI
        lanes with live activity, fed by the detail screen's collector (whose
        tick keeps running beneath — textual does not pause a background
        screen's timers)."""

        BINDINGS = [
            Binding("escape", "app.pop_screen", "Back to log"),
            Binding("a", "app.pop_screen", "Back to log"),
        ]

        def __init__(self, root: Path, collector: Collector) -> None:
            super().__init__()
            self.root = root
            self.collector = collector

        def compose(self) -> ComposeResult:
            yield Static(id="agents-head")
            yield VerticalScroll(Static(id="agents-body"))
            yield Footer()

        def on_mount(self) -> None:
            self.refresh_agents()
            self.set_interval(DETAIL_TICK, self.refresh_agents)

        def refresh_agents(self) -> None:
            state = model.read_state(
                self.root / "dev" / "local" / "autopilot" / "state.json"
            )
            self.query_one("#agents-head", Static).update(
                panels.agents_head(state, self.root.name)
            )
            self.query_one("#agents-body", Static).update(
                panels.agents_body(
                    self.collector.tracker, self.collector.bash_output_notes()
                )
            )

    class DetailScreen(Screen):
        BINDINGS = [
            Binding("escape", "app.pop_screen", "All loops"),
            Binding("t", "show_tasks", "Tasks"),
            Binding("a", "show_agents", "Agents"),
            Binding("f", "toggle_follow", "Follow"),
            Binding("q", "app.detach", "Quit UI (loop runs)"),
            Binding("p", "pause_loop", "Pause loop"),
            Binding("s", "stop_loop", "Stop loop"),
            Binding("question_mark", "show_help", "Help", key_display="?"),
        ]

        def __init__(self, root: Path) -> None:
            super().__init__()
            self.root = root
            self.collector = Collector(root)
            self._first_attach = True

        def compose(self) -> ComposeResult:
            yield Static(id="head")
            # wrap=True + min_width=1: lines fold to the pane width (split
            # terminals) instead of forcing a horizontal scrollbar.
            yield RichLog(id="log", max_lines=LOG_KEEP, markup=False, auto_scroll=True, wrap=True, min_width=1)
            yield Footer()

        def on_mount(self) -> None:
            self.tick()
            self.set_interval(DETAIL_TICK, self.tick)

        def update_head(self) -> None:
            head = self.query_one("#head", Static)
            panel, rows = self.collector.head()
            head.styles.height = rows + 2
            head.update(panel)

        def tick(self) -> None:
            lines, reset = self.collector.poll()
            log = self.query_one("#log", RichLog)

            if reset:
                log.write(Text("── new session ──", style="dim"))
                self.collector.reset_session()

            # Only the FIRST poll can return pre-attach content. Clear the flag
            # on that poll whether or not it yielded lines: attaching to an idle
            # loop and watching it start is the common case, and its first live
            # lines must not be dimmed and banner-ed as history.
            replay = self._first_attach and not reset
            self._first_attach = False

            if lines and replay:
                log.write(Text("── replay: log content from before attach ──", style="dim"))

            for line in lines:
                _, texts = self.collector.feed(line)
                for t in texts:
                    if replay:
                        t.stylize("dim")
                    log.write(t)

            self.update_head()

        def action_show_tasks(self) -> None:
            self.app.push_screen(TasksScreen(self.root))

        def action_show_agents(self) -> None:
            self.app.push_screen(AgentsScreen(self.root, self.collector))

        def action_stop_loop(self) -> None:
            _stop_loop(self, self.root)

        def action_show_help(self) -> None:
            self.app.push_screen(HelpScreen())

        def action_toggle_follow(self) -> None:
            log = self.query_one("#log", RichLog)
            log.auto_scroll = not log.auto_scroll
            if log.auto_scroll:
                self.app.notify("follow on — log sticks to the newest lines")
            else:
                self.app.notify("follow off — scroll freely; f to re-enable")

        def action_pause_loop(self) -> None:
            _touch_pause_marker(self.app, self.root)

    class DashboardScreen(Screen):
        BINDINGS = [
            Binding("q", "app.detach", "Quit UI (loop runs)"),
            Binding("t", "show_tasks", "Tasks"),
            Binding("p", "pause_loop", "Pause loop"),
            Binding("s", "stop_loop", "Stop selected"),
            Binding("question_mark", "show_help", "Help", key_display="?"),
        ]

        def compose(self) -> ComposeResult:
            yield DataTable(cursor_type="row")
            yield Footer()

        def on_mount(self) -> None:
            self.table = self.query_one(DataTable)
            self.table.add_columns("project", "status", "phase", "prd", "task", "cycle", "cost", "sessions")
            self._roots: list[Path] = []
            self.refresh_table()
            self.set_interval(FLEET_TICK, self.refresh_table)

        def refresh_table(self) -> None:
            current_roots = discovery.discover_loops()

            rows = [discovery.loop_status(r) for r in current_roots]
            sorted_rows = sorted(rows, key=lambda r: (r.status.rank, r.name))

            cursor_row = self.table.cursor_row
            selected_root = self._roots[cursor_row] if cursor_row is not None and cursor_row < len(self._roots) else None

            self.table.clear()
            self._roots = []

            if not sorted_rows:
                self.table.add_row("No loops found.", "", "", "", "", "", "", "")
                return

            for r in sorted_rows:
                self._roots.append(r.root)
                self.table.add_row(*panels.fleet_cells(r))

            if selected_root is not None:
                try:
                    new_cursor_row = self._roots.index(selected_root)
                    self.table.move_cursor(row=new_cursor_row)
                except ValueError:
                    pass

        def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
            if event.cursor_row >= len(self._roots):
                return
            root = self._roots[event.cursor_row]
            self.app.push_screen(DetailScreen(root))

        def _selected_root(self) -> Path | None:
            cursor_row = self.table.cursor_row
            if cursor_row is None or cursor_row >= len(self._roots):
                return None
            return self._roots[cursor_row]

        def action_pause_loop(self) -> None:
            root = self._selected_root()
            if root is not None:
                _touch_pause_marker(self.app, root)

        def action_stop_loop(self) -> None:
            root = self._selected_root()
            if root is not None:
                _stop_loop(self, root)

        def action_show_tasks(self) -> None:
            root = self._selected_root()
            if root is not None:
                self.app.push_screen(TasksScreen(root))

        def action_show_help(self) -> None:
            self.app.push_screen(HelpScreen())

    class _WrapperDeadScreen(Screen):
        def __init__(self, label: str) -> None:
            super().__init__()
            self._label = label

        def compose(self) -> ComposeResult:
            hint = _NEXT_STEPS.get(self._label, "")
            yield Static(f"loop exited: {self._label}" + (f"\n{hint}" if hint else ""))

    class TraconApp(App):
        # Stock scrollbar colors vanish against dark terminal palettes.
        CSS = """
        * {
            scrollbar-color: #5ea8ff;
            scrollbar-color-hover: #8cc4ff;
            scrollbar-color-active: #b3d9ff;
            scrollbar-background: #21252e;
        }
        TasksScreen Horizontal > VerticalScroll {
            margin-right: 3;
        }
        """
        # ctrl+c is a hidden synonym for q: exit the UI, never stop a loop.
        # Stopping is s, which acts on the loop you are looking at — a
        # ctrl+c that killed the LAUNCHING loop while the cursor highlighted
        # a different row was a footgun. Wrapper-launched, exit 0 lands on
        # the wrapper's detach branch (prints the reattach hint); standalone
        # keeps the SIGINT convention.
        BINDINGS = [Binding("ctrl+c", "quit", "Exit", show=False, priority=True)]

        def on_mount(self) -> None:
            try:
                saved_theme = THEME_FILE.read_text().strip()
            except OSError:
                saved_theme = ""
            if saved_theme:
                try:
                    self.theme = saved_theme
                except Exception:
                    pass  # saved name unknown to this textual version
            self.theme_changed_signal.subscribe(self, self._save_theme)
            self.push_screen(DashboardScreen())
            if forced is not None:
                self.push_screen(DetailScreen(forced))
            elif len(roots) == 1:
                self.push_screen(DetailScreen(roots[0]))
            if wrapper_pid is not None:
                self._wrapper_alive = True
                self.set_interval(2.0, self._poll_wrapper)

        def _save_theme(self, theme: Any) -> None:
            try:
                THEME_FILE.write_text(f"{theme.name}\n")
            except OSError:
                pass  # persistence is best-effort; never break the app

        def action_quit(self) -> None:
            self.exit(return_code=130 if wrapper_pid is None else 0)

        def action_detach(self) -> None:
            self.exit(return_code=0)

        def _poll_wrapper(self) -> None:
            alive = discovery.pid_alive(wrapper_pid)
            if self._wrapper_alive and not alive:
                self._wrapper_alive = False
                label = _final_signal_label(wrapper_root)
                self.push_screen(_WrapperDeadScreen(label))
                # long enough to read the next-steps line before the exit
                self.set_timer(5.0, lambda: self.exit(return_code=3))

    return TraconApp()


def run_app(roots: list[Path], forced: Path | None = None, wrapper_pid: int | None = None) -> int:
    app = build_app(roots, forced, wrapper_pid)
    app.run()
    return app.return_code if app.return_code is not None else 0


def run_once(root: Path | None = None) -> int:
    from rich.console import Console
    console = Console()

    loops = discovery.discover_loops()
    if not loops:
        console.print("No loops found.")
        return 1

    table = panels.fleet_table([discovery.loop_status(r) for r in loops])
    console.print(table)

    if root is None:
        cwd = Path.cwd()
        cwd_loops = [r for r in loops if r == cwd or r in cwd.parents]
        if cwd_loops:
            root = cwd_loops[0]
        else:
            root = Path.home() / ".claude"

    collector = Collector(root)
    lines, _ = collector.poll()

    # Feed BEFORE building the head: the header's session model, token totals
    # and agents row all come from the events in these very lines.
    rendered_lines = []
    for line in lines:
        _, texts = collector.feed(line)
        rendered_lines.extend(texts)

    panel, _ = collector.head()
    console.print(panel)

    for t in rendered_lines[-12:]:
        console.print(t)

    return 0
