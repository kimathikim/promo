#!/usr/bin/env python3
"""PROmodoro - a progressive Pomodoro timer for the terminal.

Each focus session is followed by a rating of how focused you were, and the
next session grows or shrinks accordingly. Breaks are one fifth of the time you
actually focused, and a long break is due after a configurable amount of focus.
"""

import argparse
import csv
import os
import select
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

try:
    from rich import box
    from rich.align import Align
    from rich.console import Console, Group
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress_bar import ProgressBar
    from rich.table import Table
    from rich.text import Text
except ImportError:  # pragma: no cover - only hit when the dependency is missing
    sys.exit("promo needs the 'rich' package: pip install rich")

try:
    import termios
    import tty
except ImportError:  # Windows: timer still runs, keyboard controls are disabled
    termios = None
    tty = None


DEFAULT_MESSAGE = "Let's get things done"
LONG_BREAK_MINUTES = 30
MIN_FOCUS_MINUTES = 5
MAX_FOCUS_MINUTES = 180
TICK = 0.2

CSV_HEADER = [
    "date", "start", "end", "phase", "planned_min", "actual_min",
    "focus_level", "message",
]

PHASE_STYLE = {
    "focus": ("FOCUS", "bold #ff6b6b"),
    "break": ("SHORT BREAK", "bold #4ecdc4"),
    "long_break": ("LONG BREAK", "bold #a78bfa"),
}


@dataclass
class FocusLevel:
    key: str
    name: str
    delta: int
    hint: str
    style: str


FOCUS_LEVELS = [
    FocusLevel("1", "Break", 0, "take a long break now", "#a78bfa"),
    FocusLevel("2", "Distracted", -5, "shorter next session", "#f87171"),
    FocusLevel("3", "Normal", +5, "a bit longer", "#facc15"),
    FocusLevel("4", "Focused", +10, "noticeably longer", "#4ade80"),
    FocusLevel("5", "Flow", +20, "ride the wave", "#38bdf8"),
]


# --------------------------------------------------------------------------
# Big clock font (3 columns x 5 rows, doubled horizontally when drawn)
# --------------------------------------------------------------------------
FONT = {
    "0": ["###", "# #", "# #", "# #", "###"],
    "1": ["  #", "  #", "  #", "  #", "  #"],
    "2": ["###", "  #", "###", "#  ", "###"],
    "3": ["###", "  #", "###", "  #", "###"],
    "4": ["# #", "# #", "###", "  #", "  #"],
    "5": ["###", "#  ", "###", "  #", "###"],
    "6": ["###", "#  ", "###", "# #", "###"],
    "7": ["###", "  #", "  #", "  #", "  #"],
    "8": ["###", "# #", "###", "# #", "###"],
    "9": ["###", "# #", "###", "  #", "###"],
    ":": [" ", "#", " ", "#", " "],
}


def big_text(value: str, style: str) -> Text:
    rows = []
    for r in range(5):
        parts = [FONT[ch][r].replace("#", "██").replace(" ", "  ") for ch in value]
        rows.append("  ".join(parts))
    return Text("\n".join(rows), style=style, justify="center")


def fmt_clock(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def fmt_minutes(minutes: float) -> str:
    minutes = int(round(minutes))
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h}h {m:02d}m"
    return f"{h}h" if h else f"{m}m"


# --------------------------------------------------------------------------
# State
# --------------------------------------------------------------------------
@dataclass
class Phase:
    kind: str
    planned: float  # seconds
    elapsed: float = 0.0
    paused: bool = False
    started_at: datetime = field(default_factory=datetime.now)

    @property
    def remaining(self) -> float:
        return max(0.0, self.planned - self.elapsed)

    @property
    def fraction(self) -> float:
        return min(1.0, self.elapsed / self.planned) if self.planned else 1.0


@dataclass
class Stats:
    sessions: int = 0
    focus_min: float = 0.0
    break_min: float = 0.0
    since_long_break: float = 0.0
    today_before: float = 0.0  # focus minutes already logged today
    history: List[tuple] = field(default_factory=list)


# --------------------------------------------------------------------------
# Terminal input
# --------------------------------------------------------------------------
class Keys:
    """Non-blocking single key reader (cbreak mode, Ctrl-C still works)."""

    def __init__(self):
        self.fd = None
        self.saved = None

    def __enter__(self):
        if termios and sys.stdin.isatty():
            self.fd = sys.stdin.fileno()
            self.saved = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)
        return self

    def __exit__(self, *exc):
        if self.saved is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)

    @property
    def interactive(self) -> bool:
        return self.fd is not None

    def read(self, timeout: float) -> Optional[str]:
        if self.fd is None:
            time.sleep(timeout)
            return None
        ready, _, _ = select.select([self.fd], [], [], timeout)
        if not ready:
            return None
        data = os.read(self.fd, 32).decode(errors="ignore")
        if not data or data.startswith("\x1b"):  # ignore arrows/escape codes
            return None
        return data[0]


# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------
class Log:
    def __init__(self, path: str):
        self.path = os.path.expanduser(path)

    def write(self, phase: Phase, message: str, level: str = "") -> None:
        new = not os.path.exists(self.path) or os.path.getsize(self.path) == 0
        try:
            with open(self.path, "a", newline="") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(CSV_HEADER)
                w.writerow([
                    phase.started_at.strftime("%Y-%m-%d"),
                    phase.started_at.strftime("%H:%M:%S"),
                    datetime.now().strftime("%H:%M:%S"),
                    phase.kind,
                    round(phase.planned / 60, 2),
                    round(phase.elapsed / 60, 2),
                    level,
                    message,
                ])
        except OSError:
            pass  # never let logging kill a focus session

    def focus_today(self) -> float:
        today = datetime.now().strftime("%Y-%m-%d")
        total = 0.0
        try:
            with open(self.path, newline="") as f:
                for row in csv.DictReader(f):
                    if row.get("date") == today and row.get("phase") == "focus":
                        total += float(row.get("actual_min") or 0)
        except (OSError, ValueError, csv.Error):
            pass
        return total


def notify(title: str, body: str, bell: bool) -> None:
    if bell:
        sys.stdout.write("\a")
        sys.stdout.flush()
    if shutil.which("notify-send"):
        subprocess.Popen(
            ["notify-send", "-a", "promo", title, body],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------
class UI:
    def __init__(self, console: Console, args, stats: Stats):
        self.console = console
        self.args = args
        self.stats = stats

    @property
    def width(self) -> int:
        return max(40, min(self.console.size.width - 4, 72))

    def _frame(self, body, title: str, style: str) -> Align:
        panel = Panel(
            body,
            title="[bold] PROmodoro [/]",
            subtitle=title,
            border_style=style,
            box=box.ROUNDED,
            width=self.width,
            padding=(1, 2),
        )
        return Align.center(panel, vertical="middle",
                            height=self.console.size.height)

    def _stats_grid(self, phase: Optional[Phase]) -> Table:
        s = self.stats
        live_focus = phase.elapsed / 60 if phase and phase.kind == "focus" else 0
        grid = Table.grid(expand=True, padding=(0, 2))
        grid.add_column(style="dim")
        grid.add_column(justify="right")
        grid.add_column(style="dim")
        grid.add_column(justify="right")
        grid.add_row(
            "Sessions", str(s.sessions),
            "Focused", fmt_minutes(s.focus_min + live_focus),
        )
        grid.add_row(
            "Breaks", fmt_minutes(s.break_min),
            "Today", fmt_minutes(s.today_before + s.focus_min + live_focus),
        )
        return grid

    def _long_break_meter(self, phase: Optional[Phase]) -> Group:
        live = phase.elapsed / 60 if phase and phase.kind == "focus" else 0
        done = min(self.args.long_break_after, self.stats.since_long_break + live)
        bar = ProgressBar(total=self.args.long_break_after, completed=done,
                          width=self.width - 6, complete_style="#a78bfa",
                          finished_style="#a78bfa")
        label = Text.assemble(
            ("Long break in ", "dim"),
            (fmt_minutes(self.args.long_break_after - done), "#a78bfa"),
        )
        if self.stats.sessions:
            label.append("  ·  ", style="dim")
            label.append("●" * min(self.stats.sessions, 12), style="#ff6b6b")
        return Group(label, bar)

    @staticmethod
    def _keys(*pairs) -> Text:
        t = Text(justify="center")
        for i, (k, desc) in enumerate(pairs):
            if i:
                t.append("   ")
            t.append(f" {k} ", style="bold reverse")
            t.append(f" {desc}", style="dim")
        return t

    def timer(self, phase: Phase) -> Align:
        label, color = PHASE_STYLE[phase.kind]
        clock_style = "dim" if phase.paused else color
        status = Text(justify="center")
        status.append(f"● {label}", style=color)
        if phase.kind == "focus":
            status.append(f"  ·  session {self.stats.sessions + 1}", style="dim")
        if phase.paused:
            status.append("  ·  PAUSED", style="bold yellow blink")

        bar = ProgressBar(total=phase.planned, completed=phase.elapsed,
                          width=self.width - 14, complete_style=color,
                          finished_style=color)
        bar_row = Table.grid(padding=(0, 1))
        bar_row.add_column()
        bar_row.add_column(justify="right", style="dim")
        bar_row.add_row(bar, f"{int(phase.fraction * 100):>3d}%")

        ends = datetime.fromtimestamp(time.time() + phase.remaining)
        info = Text(justify="center", style="dim")
        info.append(f"{fmt_minutes(phase.planned / 60)} planned")
        if not phase.paused:
            info.append(f"  ·  ends at {ends:%H:%M}")

        body = Group(
            status,
            Text(""),
            big_text(fmt_clock(phase.remaining), clock_style),
            Text(""),
            Align.center(bar_row),
            info,
            Text(""),
            Text(f"“{self.args.message}”", style="italic", justify="center")
            if phase.kind == "focus"
            else Text("Step away from the screen. Stretch. Hydrate.",
                      style="italic dim", justify="center"),
            Text(""),
            self._long_break_meter(phase),
            Text(""),
            self._stats_grid(phase),
            Text(""),
            self._keys(("space", "pause"), ("s", "skip"),
                       ("+/-", "1 min"), ("q", "quit")),
        )
        return self._frame(body, f"[{color}]{label.lower()}[/]", color)

    def rating(self, focused_min: float, current_min: int) -> Align:
        table = Table(box=box.SIMPLE_HEAD, expand=True, show_edge=False)
        table.add_column("key", justify="center", style="bold reverse")
        table.add_column("level")
        table.add_column("next session", justify="right")
        table.add_column("", style="dim")
        for lvl in FOCUS_LEVELS:
            nxt = ("long break" if lvl.delta == 0
                   else fmt_minutes(clamp_focus(current_min + lvl.delta)))
            table.add_row(f" {lvl.key} ", Text(lvl.name, style=f"bold {lvl.style}"),
                          nxt, lvl.hint)
        body = Group(
            Text("✔ Session complete", style="bold #4ade80", justify="center"),
            Text(f"You focused for {fmt_minutes(focused_min)}. "
                 "How was your focus?", justify="center", style="dim"),
            Text(""),
            table,
            Text(""),
            self._stats_grid(None),
            Text(""),
            self._keys(("1-5", "rate"), ("enter", "normal"), ("q", "quit")),
        )
        return self._frame(body, "[#4ade80]rate your focus[/]", "#4ade80")


def clamp_focus(minutes: float) -> int:
    return int(max(MIN_FOCUS_MINUTES, min(MAX_FOCUS_MINUTES, minutes)))


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------
class Quit(Exception):
    pass


class App:
    def __init__(self, args):
        self.args = args
        self.console = Console()
        self.log = Log(args.log)
        self.stats = Stats(today_before=self.log.focus_today())
        self.ui = UI(self.console, args, self.stats)
        self.focus_min = args.minutes
        self.current: Optional[Phase] = None

    def run_phase(self, live: Live, keys: Keys, phase: Phase) -> bool:
        """Run a phase until it ends. Returns True if it ran to completion."""
        self.current = phase
        last = time.monotonic()
        while True:
            now = time.monotonic()
            if not phase.paused:
                phase.elapsed += now - last
            last = now
            if phase.remaining <= 0:
                phase.elapsed = phase.planned
                return True
            live.update(self.ui.timer(phase), refresh=True)
            key = keys.read(TICK)
            if key is None:
                continue
            key = key.lower()
            if key in (" ", "p"):
                phase.paused = not phase.paused
            elif key == "s":
                return False
            elif key in ("+", "="):
                phase.planned += 60
            elif key in ("-", "_"):
                phase.planned = max(phase.elapsed + 1, phase.planned - 60)
            elif key == "q":
                raise Quit

    def ask_level(self, live: Live, keys: Keys, focused_min: float) -> FocusLevel:
        if not keys.interactive:
            return FOCUS_LEVELS[2]
        live.update(self.ui.rating(focused_min, self.focus_min), refresh=True)
        while True:
            key = keys.read(1.0)
            if key is None:
                live.update(self.ui.rating(focused_min, self.focus_min),
                            refresh=True)
                continue
            if key in ("\n", "\r"):
                return FOCUS_LEVELS[2]
            if key.lower() == "q":
                raise Quit
            for lvl in FOCUS_LEVELS:
                if key == lvl.key:
                    return lvl

    def finish(self, phase: Phase, level: str = "") -> None:
        minutes = phase.elapsed / 60
        if phase.kind == "focus":
            self.stats.sessions += 1
            self.stats.focus_min += minutes
            self.stats.since_long_break += minutes
        else:
            self.stats.break_min += minutes
            if phase.kind == "long_break":
                self.stats.since_long_break = 0
        self.stats.history.append((phase.kind, phase.planned / 60, minutes, level))
        self.log.write(phase, self.args.message, level)
        self.current = None

    def cycle(self, live: Live, keys: Keys) -> None:
        bell = not self.args.no_bell
        focus = Phase("focus", self.focus_min * 60)
        self.run_phase(live, keys, focus)
        focused_min = focus.elapsed / 60
        notify("Focus session done", f"{fmt_minutes(focused_min)} focused", bell)

        # rate before logging so the level lands on the focus row
        level = self.ask_level(live, keys, focused_min)
        self.finish(focus, level.name)
        if level.delta:
            self.focus_min = clamp_focus(self.focus_min + level.delta)

        long_due = self.stats.since_long_break >= self.args.long_break_after
        if level.name == "Break" or long_due:
            brk = Phase("long_break", LONG_BREAK_MINUTES * 60)
        else:
            brk = Phase("break", max(60, round(focus.elapsed / 5)))
        self.run_phase(live, keys, brk)
        self.finish(brk)
        notify("Break over", f"Next: {fmt_minutes(self.focus_min)} of focus", bell)

    def run(self) -> None:
        try:
            with Keys() as keys, Live(console=self.console, screen=True,
                                      auto_refresh=False,
                                      transient=True) as live:
                while True:
                    self.cycle(live, keys)
        except (Quit, KeyboardInterrupt):
            # keep whatever was done in the unfinished phase
            if self.current and self.current.elapsed >= 30:
                self.finish(self.current, "stopped")
        self.summary()

    def summary(self) -> None:
        s = self.stats
        table = Table(box=box.SIMPLE_HEAD, show_edge=False)
        table.add_column("#", style="dim", justify="right")
        table.add_column("phase")
        table.add_column("planned", justify="right")
        table.add_column("actual", justify="right")
        table.add_column("focus level")
        for i, (kind, planned, actual, level) in enumerate(s.history, 1):
            label, color = PHASE_STYLE[kind]
            table.add_row(str(i), Text(label.title(), style=color),
                          fmt_minutes(planned), fmt_minutes(actual), level)
        body = Group(
            Text.assemble(
                ("Focused ", "dim"), (fmt_minutes(s.focus_min), "bold #ff6b6b"),
                ("   Breaks ", "dim"), (fmt_minutes(s.break_min), "bold #4ecdc4"),
                ("   Sessions ", "dim"), (str(s.sessions), "bold"),
                ("   Today ", "dim"),
                (fmt_minutes(s.today_before + s.focus_min), "bold #a78bfa"),
            ),
            Text(""),
            table if s.history else Text("No sessions recorded.", style="dim"),
            Text(""),
            Text(f"Log: {self.log.path}", style="dim"),
        )
        self.console.print(Panel(body, title="[bold] PROmodoro · summary [/]",
                                 border_style="#a78bfa", box=box.ROUNDED,
                                 padding=(1, 2), expand=False))


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="promo",
        description="Progressive Pomodoro timer: sessions grow with your focus.",
        epilog="Keys: space/p pause · s skip · +/- adjust by 1 min · q quit",
    )
    p.add_argument("hours", nargs="?", type=int, default=0,
                   help="hours for the first focus session (default 0)")
    p.add_argument("minutes", nargs="?", type=int, default=5,
                   help="minutes for the first focus session (default 5)")
    p.add_argument("message", nargs="?", default=DEFAULT_MESSAGE,
                   help=f'message shown while focusing (default "{DEFAULT_MESSAGE}")')
    p.add_argument("--long-break-after", type=int, default=180, metavar="MIN",
                   help="focus minutes before a long break (default 180)")
    p.add_argument("--log", default="~/timeManager.csv", metavar="PATH",
                   help="CSV log file (default ~/timeManager.csv)")
    p.add_argument("--no-bell", action="store_true",
                   help="do not ring the terminal bell")
    args = p.parse_args(argv)
    if args.hours < 0 or args.minutes < 0:
        p.error("hours and minutes must be positive")
    if args.long_break_after <= 0:
        p.error("--long-break-after must be positive")
    args.minutes = max(1, min(MAX_FOCUS_MINUTES, args.hours * 60 + args.minutes))
    return args


def main(argv=None) -> None:
    App(parse_args(argv)).run()


if __name__ == "__main__":
    main()
