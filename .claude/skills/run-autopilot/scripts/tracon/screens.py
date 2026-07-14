"""Terminal screens for tracon: dashboard and detail view.

Implements the Collector for per-tick I/O and Textual screens for the app.
"""

from __future__ import annotations

import json
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


class Collector:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._autopilot = root / "dev" / "local" / "autopilot"
        self._tail = LogTail(self._autopilot / "last-session.log")
        self._usage = SessionUsage()
        self._tracker = AgentTracker()

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

        texts = render_line(raw, event)
        tag = self._tracker.tag_for(event)
        if tag is not None:
            label, color = tag
            res = []
            for t in texts:
                p = Text(f"⟨{label}⟩ ", style=color)
                p.append_text(t)
                res.append(p)
            texts = res

        return event, texts

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


def build_app(roots: list[Path], forced: Path | None = None) -> App:
    from textual.app import App, ComposeResult
    from textual.widgets import DataTable, RichLog, Static, Footer
    from textual.screen import Screen
    from textual.binding import Binding

    class DetailScreen(Screen):
        BINDINGS = [
            Binding("escape", "app.pop_screen", "Back"),
            Binding("f", "toggle_follow", "Toggle Follow"),
            Binding("q", "app.quit", "Quit"),
        ]

        def __init__(self, root: Path) -> None:
            super().__init__()
            self.root = root
            self.collector = Collector(root)
            self._first_attach = True

        def compose(self) -> ComposeResult:
            yield Static(id="head")
            yield RichLog(id="log", max_lines=LOG_KEEP, markup=False, auto_scroll=True)
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

        def action_toggle_follow(self) -> None:
            log = self.query_one("#log", RichLog)
            log.auto_scroll = not log.auto_scroll

    class DashboardScreen(Screen):
        BINDINGS = [
            Binding("q", "app.quit", "Quit"),
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
            if forced is not None:
                current_roots = [forced]
            else:
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

    class TraconApp(App):
        def on_mount(self) -> None:
            self.push_screen(DashboardScreen())
            if forced is not None:
                self.push_screen(DetailScreen(forced))
            elif len(roots) == 1:
                self.push_screen(DetailScreen(roots[0]))

    return TraconApp()


def run_app(roots: list[Path], forced: Path | None = None) -> int:
    build_app(roots, forced).run()
    return 0


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
