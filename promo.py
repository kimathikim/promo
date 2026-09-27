#!/usr/bin/env python3
"""PROmodoro - a progressive Pomodoro timer for developers.

Each focus session is followed by a rating of how focused you were, and the
next session grows or shrinks accordingly. Breaks are one fifth of the time you
actually focused, and a long break is due after a configurable amount of focus.

    promo [hours] [minutes] [task]   run the timer
    promo stats                      focus heatmap, streaks and trends
    promo status                     one-line status for tmux / waybar / polybar
"""

import argparse
import configparser
import csv
import json
import math
import os
import random
import re
import select
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

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


def _xdg(var: str, fallback: str) -> str:
    return os.path.join(os.environ.get(var) or os.path.expanduser(fallback), "promo")


DATA_DIR = _xdg("XDG_DATA_HOME", "~/.local/share")
CACHE_DIR = _xdg("XDG_CACHE_HOME", "~/.cache")
CONFIG_PATH = os.path.join(_xdg("XDG_CONFIG_HOME", "~/.config"), "config.ini")
STATE_PATH = os.path.join(CACHE_DIR, "state.json")
CONTROL_PATH = os.path.join(CACHE_DIR, "control")  # FIFO for remote commands

LONG_BREAK_MINUTES = 30
MIN_FOCUS_MINUTES = 5
MAX_FOCUS_MINUTES = 180

CSV_HEADER = [
    "date", "start", "end", "phase", "planned_min", "actual_min",
    "focus_level", "task", "project", "branch", "commits",
]

# label, accent colour, status-bar icon
PHASES = {
    "focus": ("FOCUS", "#ff6b6b", "🍅"),
    "break": ("SHORT BREAK", "#4ecdc4", "☕"),
    "long_break": ("LONG BREAK", "#a78bfa", "🌴"),
}

CARD_TOP = "#2c313c"
CARD_BOTTOM = "#242830"
DIGIT = "#f1f1f1"
DIGIT_DIM = "#6b717d"
MUTED = "#6b717d"


@dataclass
class FocusLevel:
    key: str
    name: str
    delta: int
    style: str


FOCUS_LEVELS = [
    FocusLevel("1", "Break", 0, "#a78bfa"),
    FocusLevel("2", "Distracted", -5, "#f87171"),
    FocusLevel("3", "Normal", +5, "#facc15"),
    FocusLevel("4", "Focused", +10, "#4ade80"),
    FocusLevel("5", "Flow", +20, "#38bdf8"),
]


# --------------------------------------------------------------------------
# Clock rendering
# --------------------------------------------------------------------------
# Flip font: 4 x 6 pixels, split 3/3 across the card hinge.
FLIP_FONT = {
    "0": ["####", "#  #", "#  #", "#  #", "#  #", "####"],
    "1": [" ## ", "  # ", "  # ", "  # ", "  # ", " ###"],
    "2": ["####", "   #", "####", "#   ", "#   ", "####"],
    "3": ["####", "   #", "####", "   #", "   #", "####"],
    "4": ["#  #", "#  #", "####", "   #", "   #", "   #"],
    "5": ["####", "#   ", "####", "   #", "   #", "####"],
    "6": ["####", "#   ", "####", "#  #", "#  #", "####"],
    "7": ["####", "   #", "   #", "   #", "   #", "   #"],
    "8": ["####", "#  #", "####", "#  #", "#  #", "####"],
    "9": ["####", "#  #", "####", "   #", "   #", "####"],
}
# Compact font for small terminals: 3 x 5 pixels.
SMALL_FONT = {
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
CARD_WIDTH = 12  # 4 pixels doubled + 2 columns padding each side
FLIP_SECONDS = 0.18


def _pixels(row: str) -> str:
    return "".join("██" if c == "#" else "  " for c in row)


class FlipClock:
    """Renders MM:SS as flip cards and animates digits as they change."""

    def __init__(self):
        self.shown = ""
        self.flips: Dict[int, Tuple[str, float]] = {}  # index -> (old char, t0)

    def update(self, value: str, now: float) -> None:
        if len(value) == len(self.shown):
            for i, (old, new) in enumerate(zip(self.shown, value)):
                if old != new:
                    self.flips[i] = (old, now)
        else:
            self.flips.clear()
        self.shown = value
        self.flips = {i: f for i, f in self.flips.items()
                      if now - f[1] < FLIP_SECONDS}

    def next_frame_in(self, now: float) -> Optional[float]:
        if not self.flips:
            return None
        return max(0.01, min(t0 + FLIP_SECONDS - now for _, t0 in self.flips.values()))

    @staticmethod
    def width(value: str) -> int:
        digits = sum(c.isdigit() for c in value)
        colons = value.count(":")
        return digits * CARD_WIDTH + colons * 8 + (digits - colons - 1)

    def render_flip(self, value: str, dim: bool) -> Text:
        rows = [Text() for _ in range(9)]
        fg = DIGIT_DIM if dim else DIGIT
        for i, ch in enumerate(value):
            if i and ":" not in (ch, value[i - 1]):
                for r in rows:
                    r.append(" ")
            if ch == ":":
                for n, r in enumerate(rows):
                    r.append("   ██   " if n in (2, 6) else " " * 8, style=MUTED)
                continue
            # mid-flip: the new digit has dropped onto the top half while the
            # bottom half still shows the old one
            bottom = self.flips[i][0] if i in self.flips else ch
            bottom_fg = DIGIT_DIM if i in self.flips else fg
            glyph_top, glyph_bottom = FLIP_FONT[ch], FLIP_FONT[bottom]
            rows[0].append(" " * CARD_WIDTH, style=f"on {CARD_TOP}")
            for g in range(3):
                rows[1 + g].append(f"  {_pixels(glyph_top[g])}  ",
                                   style=f"bold {fg} on {CARD_TOP}")
            rows[4].append(" " * CARD_WIDTH)  # the hinge
            for g in range(3, 6):
                rows[2 + g].append(f"  {_pixels(glyph_bottom[g])}  ",
                                   style=f"bold {bottom_fg} on {CARD_BOTTOM}")
            rows[8].append(" " * CARD_WIDTH, style=f"on {CARD_BOTTOM}")
        # Center the clock as one block. Per-line centering strips trailing
        # spaces, which shifts rows that end in blank card padding.
        out = Text("\n").join(rows)
        out.no_wrap = True
        return out

    @staticmethod
    def render_small(value: str, style: str) -> Text:
        rows = ["  ".join(_pixels(SMALL_FONT[c][r]) if c.isdigit()
                          else SMALL_FONT[c][r].replace("#", "█")
                          for c in value) for r in range(5)]
        return Text("\n".join(rows), style=style, no_wrap=True)


def fmt_clock(seconds: float) -> str:
    seconds = max(0, int(math.ceil(seconds - 1e-6)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def fmt_minutes(minutes: float) -> str:
    minutes = int(round(minutes))
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h}h {m:02d}m"
    return f"{h}h" if h else f"{m}m"


def plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def tilde(path: str) -> str:
    path, home = os.path.expanduser(path), os.path.expanduser("~")
    return "~" + path[len(home):] if path.startswith(home + os.sep) else path


def clamp_focus(minutes: float) -> int:
    return int(max(MIN_FOCUS_MINUTES, min(MAX_FOCUS_MINUTES, minutes)))


# --------------------------------------------------------------------------
# Game: XP, levels, combos and achievements, all replayed from the session log
# --------------------------------------------------------------------------
XP_MULTIPLIER = {"Flow": 1.5, "Focused": 1.25, "Normal": 1.0, "Distracted": 0.5}
COMBO_LEVELS = {"Focused", "Flow"}
TITLES = ["Intern", "Junior Dev", "Mid-level Dev", "Senior Dev", "Staff Engineer",
          "Principal Engineer", "Distinguished Engineer", "10x Engineer",
          "Blazingly Fast"]
XP_STEP = 150  # level n starts at XP_STEP * n^2

ACHIEVEMENTS = [
    ("first_blood", "First Blood", "finish your first focus session"),
    ("deep_work", "Deep Work", "one session of 90+ minutes"),
    ("in_the_zone", "In The Zone", "rate 5 sessions as Flow"),
    ("combo", "C-C-C-Combo", "5 Focused/Flow sessions in a row"),
    ("ship_it", "Ship It", "5+ commits in one session"),
    ("marathon", "Marathon", "4 hours of focus in one day"),
    ("on_fire", "On Fire", "focus 7 days in a row"),
    ("night_owl", "Night Owl", "start a session between midnight and 4am"),
    ("early_bird", "Early Bird", "start a session between 4am and 6am"),
    ("centurion", "Centurion", "finish 100 focus sessions"),
]


def session_xp(minutes: float, level: str, combo: int) -> int:
    """XP for one session: minutes x focus multiplier, +10% per combo step."""
    return int(round(minutes * XP_MULTIPLIER.get(level, 0.75)
                     * (1 + 0.1 * min(combo, 5))))


def level_for(xp: int) -> Tuple[int, str, int, int]:
    """(level, title, xp into this level, xp this level spans)."""
    n = min(len(TITLES) - 1, int(math.sqrt(max(0, xp) / XP_STEP)))
    lo, hi = XP_STEP * n * n, XP_STEP * (n + 1) ** 2
    return n, TITLES[n], xp - lo, hi - lo


@dataclass
class Progress:
    xp: int = 0
    combo: int = 0
    best_combo: int = 0
    unlocked: set = field(default_factory=set)

    @property
    def level(self) -> Tuple[int, str, int, int]:
        return level_for(self.xp)


def replay(rows: List[dict]) -> Progress:
    """Rebuild XP, combo and achievements from logged focus sessions."""
    p = Progress()
    flows = sessions = 0
    by_day: Dict[str, float] = defaultdict(float)
    for r in rows:
        mins = _num(r.get("actual_min"))
        if r.get("phase") != "focus" or mins < 1:
            continue
        level = r.get("focus_level") or ""
        sessions += 1
        p.combo = p.combo + 1 if level in COMBO_LEVELS else 0
        p.best_combo = max(p.best_combo, p.combo)
        p.xp += session_xp(mins, level, p.combo)
        flows += level == "Flow"
        by_day[r.get("date") or ""] += mins
        try:
            hour = int((r.get("start") or "12")[:2])
        except ValueError:
            hour = 12
        checks = {
            "first_blood": True,
            "deep_work": mins >= 90,
            "in_the_zone": flows >= 5,
            "combo": p.combo >= 5,
            "ship_it": _num(r.get("commits")) >= 5,
            "marathon": by_day[r.get("date") or ""] >= 240,
            "night_owl": hour < 4,
            "early_bird": 4 <= hour < 6,
            "centurion": sessions >= 100,
        }
        p.unlocked.update(k for k, ok in checks.items() if ok)
    days = sorted(d for d in by_day if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d))
    run = best = 0
    prev = None
    for d in map(date.fromisoformat, days):
        run = run + 1 if prev and d - prev == timedelta(days=1) else 1
        best, prev = max(best, run), d
    if best >= 7:
        p.unlocked.add("on_fire")
    return p


# Opt-in commentary (--spicy).
SPICY_BREAKS = [
    "go touch grass 🌱",
    "hydrate or diedrate 💧",
    "stand up. your spine has a skill issue",
    "look at something 20 feet away. no, not the other monitor",
    "stretch. you are not a shrimp 🦐",
    "away from the keyboard. yes, even vim can wait",
]


def spicy_verdict(level: str, minutes: float, commits: int, has_repo: bool) -> str:
    if level == "Flow":
        return random.choice(["BLAZINGLY FAST 🚀", "flow state achieved. chat is speechless",
                              "that was a 10x session"])
    if level == "Distracted":
        return random.choice(["chat, we got distracted", "the algorithm won this round",
                              "the feed will still be there later. probably."])
    if has_repo and minutes >= 25 and commits == 0:
        return random.choice([f"{fmt_minutes(minutes)} and 0 commits… skill issue?",
                              "no commits? bold strategy",
                              "even `git commit -m wip` would count"])
    if level == "Break":
        return "rest is part of the work. seriously."
    return random.choice(["solid. keep stacking.", "another one. 🔁",
                          "consistency beats intensity"])


# --------------------------------------------------------------------------
# Git context
# --------------------------------------------------------------------------
def git(*args: str) -> Optional[str]:
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True,
                             timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


@dataclass
class Repo:
    root: str
    name: str
    branch: str
    email: Optional[str]

    @classmethod
    def detect(cls) -> Optional["Repo"]:
        root = git("rev-parse", "--show-toplevel")
        if not root:
            return None
        branch = git("-C", root, "rev-parse", "--abbrev-ref", "HEAD") or "?"
        email = git("-C", root, "config", "user.email")
        return cls(root, os.path.basename(root), branch, email)

    def refresh_branch(self) -> None:
        self.branch = git("-C", self.root, "rev-parse", "--abbrev-ref", "HEAD") or self.branch

    def activity_since(self, since: datetime) -> Tuple[int, int, int]:
        """(commits, insertions, deletions) authored since `since`."""
        args = ["-C", self.root, "log", "--all", "--no-merges",
                f"--since={since:%Y-%m-%d %H:%M:%S}", "--format=%H", "--shortstat"]
        if self.email:
            args.append(f"--author={self.email}")
        out = git(*args)
        if not out:
            return 0, 0, 0
        commits = ins = dels = 0
        for line in out.splitlines():
            if re.fullmatch(r"[0-9a-f]{40,64}", line.strip()):
                commits += 1
            m = re.search(r"(\d+) insertion", line)
            ins += int(m.group(1)) if m else 0
            m = re.search(r"(\d+) deletion", line)
            dels += int(m.group(1)) if m else 0
        return commits, ins, dels


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
    commits: int = 0
    notes: int = 0
    history: List[tuple] = field(default_factory=list)


# --------------------------------------------------------------------------
# Terminal input
# --------------------------------------------------------------------------
class Input:
    """Keyboard (cbreak mode, so Ctrl-C still works) plus the control FIFO
    that `promo toggle`, the Neovim plugin and tmux bindings write to."""

    ARROWS = {"\x1b[D": "h", "\x1b[C": "l", "\x1bOD": "h", "\x1bOC": "l"}

    def __init__(self):
        self.fd = None
        self.saved = None
        self.ctl = None
        self._pending = b""

    def __enter__(self):
        if termios and sys.stdin.isatty():
            self.fd = sys.stdin.fileno()
            self.saved = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)
        try:
            ensure_dir(CONTROL_PATH)
            if os.path.exists(CONTROL_PATH):
                os.remove(CONTROL_PATH)
            os.mkfifo(CONTROL_PATH, 0o600)
            # O_RDWR keeps a writer open ourselves, so the FIFO never hits EOF
            self.ctl = os.open(CONTROL_PATH, os.O_RDWR | os.O_NONBLOCK)
        except (OSError, AttributeError):  # no mkfifo on Windows
            self.ctl = None
        return self

    def __exit__(self, *exc):
        if self.saved is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)
        if self.ctl is not None:
            os.close(self.ctl)
            try:
                os.remove(CONTROL_PATH)
            except OSError:
                pass

    @property
    def interactive(self) -> bool:
        return self.fd is not None

    def read(self, timeout: float) -> Tuple[str, List[str]]:
        """Wait up to `timeout` for input. Returns (typed characters, remote
        command lines). A lone Esc is kept, left/right arrows become h/l and
        other escape sequences are dropped."""
        fds = [fd for fd in (self.fd, self.ctl) if fd is not None]
        if not fds:
            time.sleep(timeout)
            return "", []
        ready, _, _ = select.select(fds, [], [], max(0.0, timeout))
        keys, commands = "", []
        if self.fd is not None and self.fd in ready:
            data = os.read(self.fd, 1024).decode(errors="ignore")
            if data == "\x1b":
                keys = data
            else:
                for seq, key in self.ARROWS.items():
                    data = data.replace(seq, key)
                keys = re.sub(r"\x1b(\[[0-9;?]*[ -/]*[@-~]|O.|.)?", "", data)
        if self.ctl is not None and self.ctl in ready:
            try:
                self._pending += os.read(self.ctl, 4096)
            except BlockingIOError:
                pass
            *lines, self._pending = self._pending.split(b"\n")
            commands = [ln.decode(errors="ignore").strip() for ln in lines if ln.strip()]
        return keys, commands


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------
def ensure_dir(path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)


class Log:
    def __init__(self, path: str):
        self.path = os.path.expanduser(path)

    def write(self, phase: Phase, task: str, repo: Optional[Repo],
              level: str = "", commits: int = 0) -> None:
        try:
            ensure_dir(self.path)
            new = not os.path.exists(self.path) or os.path.getsize(self.path) == 0
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
                    task,
                    repo.name if repo else "",
                    repo.branch if repo else "",
                    commits if phase.kind == "focus" else "",
                ])
        except OSError:
            pass  # never let logging kill a focus session

    def rows(self) -> List[dict]:
        try:
            with open(self.path, newline="") as f:
                return [r for r in csv.DictReader(f) if r.get("date")]
        except (OSError, csv.Error):
            return []

    def focus_today(self) -> float:
        today = date.today().isoformat()
        return sum(_num(r.get("actual_min")) for r in self.rows()
                   if r.get("date") == today and r.get("phase") == "focus")


def _num(value) -> float:
    try:
        return float(value or 0)
    except ValueError:
        return 0.0


def append_note(path: str, text: str, task: str, repo: Optional[Repo]) -> bool:
    ctx = " · ".join(x for x in (
        f"{repo.name}@{repo.branch}" if repo else "", task) if x)
    line = f"- [ ] {datetime.now():%Y-%m-%d %H:%M} {text}"
    if ctx:
        line += f"  _({ctx})_"
    try:
        path = os.path.expanduser(path)
        ensure_dir(path)
        with open(path, "a") as f:
            f.write(line + "\n")
        return True
    except OSError:
        return False


def write_state(state: Optional[dict]) -> None:
    try:
        if state is None:
            if os.path.exists(STATE_PATH):
                os.remove(STATE_PATH)
            return
        ensure_dir(STATE_PATH)
        tmp = STATE_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f)
        os.replace(tmp, STATE_PATH)
    except OSError:
        pass


def notify(title: str, body: str, bell: bool) -> None:
    if bell:
        sys.stdout.write("\a")
        sys.stdout.flush()
    if shutil.which("notify-send"):
        subprocess.Popen(["notify-send", "-a", "promo", title, body],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif sys.platform == "darwin" and shutil.which("osascript"):
        script = f'display notification "{body}" with title "{title}"'
        subprocess.Popen(["osascript", "-e", script],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------
def key_hints(*pairs) -> Text:
    t = Text(justify="center")
    for i, (k, desc) in enumerate(pairs):
        if i:
            t.append("    ")
        t.append(k, style="bold")
        t.append(f" {desc}", style=MUTED)
    return t


class UI:
    def __init__(self, app: "App"):
        self.app = app
        self.console = app.console
        self.clock = FlipClock()

    @property
    def width(self) -> int:
        return self.console.size.width

    def _screen(self, *parts) -> Align:
        return Align.center(Group(*parts), vertical="middle",
                            height=self.console.size.height)

    def _clock(self, phase: Phase, now: float) -> Tuple[Text, int]:
        value = fmt_clock(phase.remaining)
        self.clock.update(value, now)
        w, h = self.width, self.console.size.height
        flip_w = FlipClock.width(value)
        if flip_w + 4 <= w and h >= 20:
            return self.clock.render_flip(value, phase.paused), flip_w
        small = FlipClock.render_small(value, MUTED if phase.paused else DIGIT)
        small_w = max(len(line) for line in small.plain.splitlines())
        if small_w + 4 <= w and h >= 14:
            return small, small_w
        return Text(value, style="bold", justify="center"), len(value)

    def _header(self, phase: Phase) -> Group:
        app = self.app
        label, color, _ = PHASES[phase.kind]
        top = Text(justify="center")
        top.append("● ", style=color)
        top.append(label, style=f"bold {color}")
        if phase.kind == "focus":
            top.append(f"   session {app.stats.sessions + 1}", style=MUTED)
            if app.args.task:
                top.append("   ")
                top.append(app.args.task, style="bold")
            if app.progress and app.progress.combo >= 2:
                top.append(f"   🔥 x{app.progress.combo}", style="bold #fb923c")
        else:
            top.append(f"   next: {fmt_minutes(app.focus_min)} focus", style=MUTED)
        sub = Text(justify="center", style=MUTED)
        if app.repo and phase.kind == "focus":
            branch = app.repo.branch
            if len(branch) > 32:
                branch = branch[:31] + "…"
            sub.append(f"{app.repo.name}  ⎇ {branch}")
        elif phase.kind != "focus":
            sub.append(app.break_line)
        return Group(top, sub)

    def _details(self, phase: Phase) -> Table:
        app, s = self.app, self.app.stats
        live = phase.elapsed / 60 if phase.kind == "focus" else 0
        grid = Table.grid(padding=(0, 2))
        grid.add_column(style=MUTED, justify="right")
        grid.add_column()
        today = s.today_before + s.focus_min + live
        if app.args.goal:
            bar = ProgressBar(total=app.args.goal, completed=min(today, app.args.goal),
                              width=20, complete_style="#4ade80",
                              finished_style="#4ade80")
            row = Table.grid(padding=(0, 1))
            row.add_row(Text(fmt_minutes(today)), bar,
                        Text(f"of {fmt_minutes(app.args.goal)} goal", style=MUTED))
            grid.add_row("today", row)
        else:
            grid.add_row("today", fmt_minutes(today))
        grid.add_row("this run", f"{plural(s.sessions, 'session')} · "
                     f"{fmt_minutes(s.focus_min + live)} focus · "
                     f"{fmt_minutes(s.break_min)} breaks")
        left = max(0, app.args.long_break_after - s.since_long_break - live)
        dots = Text(fmt_minutes(left))
        if s.sessions:
            dots.append("   " + "●" * min(s.sessions, 12), style=PHASES["focus"][1])
        grid.add_row("long break in", dots)
        if app.repo:
            c, ins, dels = app.live_git(phase)
            git_row = Text(f"{plural(s.commits + c, 'commit')} this run")
            if ins or dels:
                git_row.append("   ")
                git_row.append(f"+{ins}", style="#4ade80")
                git_row.append(" ")
                git_row.append(f"−{dels}", style="#f87171")
                git_row.append(" this session", style=MUTED)
            grid.add_row("git", git_row)
        if s.notes:
            grid.add_row("notes", f"{s.notes} captured (see summary)")
        if app.progress:
            _, title, into, span = app.progress.level
            lvl = Table.grid(padding=(0, 1))
            lvl.add_row(Text(title, style="bold #facc15"),
                        ProgressBar(total=span, completed=min(into, span), width=14,
                                    complete_style="#facc15", finished_style="#facc15"),
                        Text(f"{app.progress.xp:,} XP", style=MUTED))
            grid.add_row("level", lvl)
        return grid

    def _footer(self) -> Text:
        app = self.app
        if app.prompt is not None:
            kind, text = app.prompt
            t = Text(justify="center")
            t.append("✎ " if kind == "note" else ":", style="#facc15")
            t.append(text)
            t.append("▏", style="blink")
            t.append("\n")
            t.append("enter", style="bold")
            t.append(" save    " if kind == "note" else " run    ", style=MUTED)
            t.append("esc", style="bold")
            t.append(" cancel", style=MUTED)
            return t
        return key_hints(("space", "pause"), ("s", "skip"), ("+/-", "1 min"),
                         ("n", "note"), ("i", "details"), (":", "cmd"), ("q", "quit"))

    def timer(self, phase: Phase, now: float) -> Align:
        _, color, _ = PHASES[phase.kind]
        clock, clock_w = self._clock(phase, now)
        bar = ProgressBar(total=phase.planned, completed=phase.elapsed,
                          width=max(10, min(clock_w, self.width - 4)),
                          complete_style=color, finished_style=color,
                          style="#2c313c")
        info = Text(justify="center", style=MUTED)
        if phase.paused:
            info.append("PAUSED", style="bold #facc15")
            info.append("  press space to resume")
        else:
            ends = datetime.now() + timedelta(seconds=phase.remaining)
            info.append(f"ends {ends:%H:%M}   ·   {int(phase.fraction * 100)}%"
                        f"   ·   {fmt_minutes(phase.planned / 60)}")
        toast = self.app.current_toast()
        parts = [self._header(phase), Text(""), Align.center(clock), Text(""),
                 Align.center(bar), info]
        if self.app.show_details:
            parts += [Text(""), Align.center(self._details(phase))]
        parts += [Text(""),
                  Text(toast, style="#4ade80", justify="center") if toast else Text(""),
                  self._footer()]
        return self._screen(*parts)

    def rating(self, focused_min: float, activity: Tuple[int, int, int]) -> Align:
        app = self.app
        head = Text(justify="center")
        head.append("✔ ", style="#4ade80")
        head.append("Session complete", style="bold")
        sub = Text(justify="center", style=MUTED)
        sub.append(f"{fmt_minutes(focused_min)} focused")
        commits, ins, dels = activity
        if app.repo:
            sub.append(f"   ·   {plural(commits, 'commit')}")
            if ins or dels:
                sub.append(f"  +{ins} −{dels}")
        grid = Table.grid(padding=(0, 3))
        for _ in FOCUS_LEVELS:
            grid.add_column(justify="center")
        names, nexts = [], []
        for lvl in FOCUS_LEVELS:
            names.append(Text.assemble((lvl.key, "bold reverse"), " ",
                                       (lvl.name, f"bold {lvl.style}")))
            nexts.append(Text("long break" if lvl.delta == 0 else
                              f"next {fmt_minutes(clamp_focus(app.focus_min + lvl.delta))}",
                              style=MUTED))
        marks = [Text("━" * (len(lvl.name) + 2) if i == app.rating_sel else "",
                      style=lvl.style) for i, lvl in enumerate(FOCUS_LEVELS)]
        grid.add_row(*names)
        grid.add_row(*marks)
        grid.add_row(*nexts)
        hint = Text("", justify="center")
        if app.progress and app.progress.combo >= 1:
            hint = Text(f"🔥 x{app.progress.combo} combo: rate Focused or Flow to keep it",
                        style="#fb923c", justify="center")
        return self._screen(
            head, sub, Text(""),
            Text("How was your focus?", justify="center"), Text(""),
            Align.center(grid), Text(""), hint, Text(""),
            key_hints(("1-5", "rate"), ("h/l", "move"), ("enter", "pick"), ("q", "quit")),
        )


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
        self.repo = Repo.detect() if args.git else None
        self.stats = Stats(today_before=self.log.focus_today())
        self.focus_min = args.minutes
        self.current: Optional[Phase] = None
        self.show_details = False
        self.prompt: Optional[Tuple[str, str]] = None  # ("note" | "cmd", text)
        self.rating_sel = 2
        self.break_line = "step away from the screen · stretch · drink water"
        self.progress: Optional[Progress] = replay(self.log.rows()) if args.game else None
        self.xp_start = self.progress.xp if self.progress else 0
        self.toast: Tuple[str, float] = ("", 0.0)
        self._git_cache: Tuple[float, Tuple[int, int, int]] = (0.0, (0, 0, 0))
        self._title = ""
        self.ui = UI(self)

    # -- helpers ---------------------------------------------------------
    def say(self, message: str, seconds: float = 2.5) -> None:
        self.toast = (message, time.monotonic() + seconds)

    def current_toast(self) -> str:
        msg, until = self.toast
        return msg if time.monotonic() < until else ""

    def live_git(self, phase: Phase) -> Tuple[int, int, int]:
        """Git activity in the current focus session, refreshed every 20 s."""
        if not self.repo or phase.kind != "focus":
            return 0, 0, 0
        stamp, value = self._git_cache
        if time.monotonic() - stamp > 20:
            value = self.repo.activity_since(phase.started_at)
            self._git_cache = (time.monotonic(), value)
        return value

    def hook(self, event: str, phase: Phase) -> None:
        if not self.args.hook:
            return
        env = dict(os.environ,
                   PROMO_EVENT=event, PROMO_PHASE=phase.kind,
                   PROMO_MINUTES=str(round(phase.planned / 60)),
                   PROMO_TASK=self.args.task or "",
                   PROMO_PROJECT=self.repo.name if self.repo else "",
                   PROMO_BRANCH=self.repo.branch if self.repo else "")
        try:
            subprocess.Popen(os.path.expanduser(self.args.hook), shell=True, env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        except OSError:
            pass

    def publish(self, phase: Optional[Phase]) -> None:
        """Share state with `promo status` (tmux, waybar, polybar...)."""
        if phase is None:
            write_state(None)
            return
        write_state({
            "pid": os.getpid(),
            "phase": phase.kind,
            "paused": phase.paused,
            "ends_at": None if phase.paused else time.time() + phase.remaining,
            "remaining": phase.remaining,
            "planned": phase.planned,
            "task": self.args.task or "",
            "project": self.repo.name if self.repo else "",
            "branch": self.repo.branch if self.repo else "",
            "session": self.stats.sessions + (1 if phase.kind == "focus" else 0),
            "combo": self.progress.combo if self.progress else 0,
        })

    def set_title(self, phase: Phase) -> None:
        if not self.args.title:
            return
        icon = PHASES[phase.kind][2]
        title = f"{'⏸' if phase.paused else icon} {fmt_clock(phase.remaining)}"
        if title != self._title:
            self._title = title
            sys.stdout.write(f"\x1b]2;{title}\x07")
            sys.stdout.flush()

    # -- input -----------------------------------------------------------
    def save_note(self, text: str) -> None:
        if not text:
            return
        if append_note(self.args.notes, text, self.args.task, self.repo):
            self.stats.notes += 1
            self.say("note saved, back to work")
        else:
            self.say("could not write note file")

    def run_command(self, line: str, phase: Phase) -> Optional[str]:
        """Commands shared by the `:` prompt and remote control
        (`promo toggle`, the Neovim plugin, tmux bindings)."""
        name, _, arg = line.strip().lstrip(":").partition(" ")
        name, arg = name.lower(), arg.strip()
        if re.fullmatch(r"[+-]\d+", name):  # :+10  :-5
            name, arg = name[0], name[1:]
        if name in ("q", "q!", "quit", "stop", "wq", "x"):
            raise Quit
        if name in ("toggle", "p", "pause", "resume"):
            want = {"pause": True, "resume": False}.get(name, not phase.paused)
            if want != phase.paused:
                phase.paused = want
                self.hook("pause" if want else "resume", phase)
                self.publish(phase)
        elif name in ("skip", "s", "next"):
            return "skip"
        elif name in ("add", "+", "sub", "-"):
            try:
                minutes = int(arg or 1)
            except ValueError:
                self.say(f"E474: Invalid argument: {arg}")
                return None
            sign = 1 if name in ("add", "+") else -1
            phase.planned = max(phase.elapsed + 1, phase.planned + sign * minutes * 60)
            self.publish(phase)
            self.say(f"{'+' if sign > 0 else '−'}{minutes} min")
        elif name in ("note", "n"):
            if arg:
                self.save_note(arg)
            else:
                self.prompt = ("note", "")
        elif name == "task":
            self.args.task = arg
            self.publish(phase)
            self.say(f"task: {arg}" if arg else "task cleared")
        elif name in ("details", "i"):
            self.show_details = not self.show_details
        elif name in ("rate",) + tuple(lvl.key for lvl in FOCUS_LEVELS):
            self.say("nothing to rate yet, keep going")
        elif name:
            self.say(f"E492: Not an editor command: {line.strip()}")
        return None

    def handle_key(self, ch: str, phase: Phase) -> Optional[str]:
        if self.prompt is not None:
            kind, text = self.prompt
            if ch in ("\n", "\r"):
                self.prompt = None
                if kind == "note":
                    self.save_note(text.strip())
                elif text.strip():
                    return self.run_command(text, phase)
            elif ch == "\x1b":
                self.prompt = None
            elif ch in ("\x7f", "\b"):
                # like vim, backspace on an empty command line closes it
                self.prompt = None if kind == "cmd" and not text else (kind, text[:-1])
            elif ch == "\x15":  # Ctrl-U
                self.prompt = (kind, "")
            elif ch.isprintable():
                self.prompt = (kind, text + ch)
            return None
        if ch == ":":
            self.prompt = ("cmd", "")
            return None
        keymap = {" ": "toggle", "p": "toggle", "s": "skip", "+": "+1", "=": "+1",
                  "-": "-1", "_": "-1", "i": "details", "n": "note", "q": "quit"}
        cmd = keymap.get(ch.lower())
        if cmd in ("+1", "-1"):
            phase.planned = max(phase.elapsed + 1, phase.planned + int(cmd) * 60)
            self.publish(phase)
            return None
        return self.run_command(cmd, phase) if cmd else None

    # -- phases ----------------------------------------------------------
    def run_phase(self, live: Live, inp: Input, phase: Phase) -> bool:
        """Run a phase until it ends. Returns True if it ran to completion."""
        self.current = phase
        self._git_cache = (0.0, (0, 0, 0))
        self.publish(phase)
        last = time.monotonic()
        while True:
            now = time.monotonic()
            if not phase.paused:
                phase.elapsed += now - last
            last = now
            if phase.remaining <= 0:
                phase.elapsed = phase.planned
                return True
            live.update(self.ui.timer(phase, now), refresh=True)
            self.set_title(phase)
            keys, commands = inp.read(self.wait_time(phase, now))
            for ch in keys:
                if self.handle_key(ch, phase) == "skip":
                    return False
            for line in commands:
                if self.run_command(line, phase) == "skip":
                    return False

    def wait_time(self, phase: Phase, now: float) -> float:
        """Sleep exactly until the display next needs to change."""
        if phase.paused:
            wait = 1.0
        else:
            frac = phase.remaining - math.floor(phase.remaining)
            wait = (frac or 1.0) + 0.005
        anim = self.ui.clock.next_frame_in(now)
        if anim is not None:
            wait = min(wait, anim)
        _, until = self.toast
        if until > now:
            wait = min(wait, until - now + 0.01)
        return min(wait, 1.0)

    def ask_level(self, live: Live, inp: Input, focused_min: float,
                  activity: Tuple[int, int, int]) -> FocusLevel:
        if not inp.interactive:
            return FOCUS_LEVELS[2]
        self.rating_sel = 2
        by_key = {lvl.key: lvl for lvl in FOCUS_LEVELS}
        while True:
            live.update(self.ui.rating(focused_min, activity), refresh=True)
            keys, commands = inp.read(1.0)
            for ch in keys:
                if ch in ("\n", "\r"):
                    return FOCUS_LEVELS[self.rating_sel]
                low = ch.lower()
                if low == "q":
                    raise Quit
                if low == "h":
                    self.rating_sel = max(0, self.rating_sel - 1)
                elif low == "l":
                    self.rating_sel = min(len(FOCUS_LEVELS) - 1, self.rating_sel + 1)
                elif ch in by_key:
                    return by_key[ch]
            for line in commands:
                name, _, arg = line.lower().partition(" ")
                if name in ("q", "quit", "stop", "wq"):
                    raise Quit
                key = arg.strip() if name == "rate" else name
                if key in by_key:
                    return by_key[key]
                if name == "note" and arg.strip():
                    append_note(self.args.notes, line.partition(" ")[2].strip(),
                                self.args.task, self.repo)
                    self.stats.notes += 1

    def finish(self, phase: Phase, level: str = "", commits: int = 0) -> None:
        minutes = phase.elapsed / 60
        if phase.kind == "focus":
            self.stats.sessions += 1
            self.stats.focus_min += minutes
            self.stats.since_long_break += minutes
            self.stats.commits += commits
        else:
            self.stats.break_min += minutes
            if phase.kind == "long_break":
                self.stats.since_long_break = 0
        self.stats.history.append((phase.kind, phase.planned / 60, minutes, level,
                                   commits if phase.kind == "focus" else None))
        self.log.write(phase, self.args.task, self.repo, level, commits)
        self.current = None

    def level_up_messages(self) -> List[str]:
        """Refresh XP from the log and describe what changed."""
        if not self.progress:
            return []
        before, after = self.progress, replay(self.log.rows())
        self.progress = after
        news = []
        if after.xp > before.xp:
            news.append(f"+{after.xp - before.xp} XP")
        if after.combo >= 2:
            news.append(f"🔥 x{after.combo} combo")
        if after.level[0] > before.level[0]:
            news.append(f"⬆ level up: {after.level[1]}")
        names = {k: n for k, n, _ in ACHIEVEMENTS}
        news += [f"🏆 {names[k]}" for k in sorted(after.unlocked - before.unlocked)]
        return news

    def cycle(self, live: Live, inp: Input) -> None:
        bell = self.args.bell
        if self.repo:
            self.repo.refresh_branch()
        focus = Phase("focus", self.focus_min * 60)
        self.hook("focus_start", focus)
        self.run_phase(live, inp, focus)
        self.hook("focus_end", focus)
        focused_min = focus.elapsed / 60
        activity = self.repo.activity_since(focus.started_at) if self.repo else (0, 0, 0)
        notify("Focus session done", f"{fmt_minutes(focused_min)} focused", bell)

        # rate before logging so the level lands on the focus row
        level = self.ask_level(live, inp, focused_min, activity)
        self.finish(focus, level.name, activity[0])
        if level.delta:
            self.focus_min = clamp_focus(self.focus_min + level.delta)
        news = self.level_up_messages()
        if self.args.spicy:
            news.append(spicy_verdict(level.name, focused_min, activity[0], bool(self.repo)))
            self.break_line = random.choice(SPICY_BREAKS)
        if news:
            self.say("   ".join(news), 8)

        long_due = self.stats.since_long_break >= self.args.long_break_after
        if level.name == "Break" or long_due:
            brk = Phase("long_break", LONG_BREAK_MINUTES * 60)
            if long_due:
                self.say(f"{fmt_minutes(self.stats.since_long_break)} of focus. "
                         "You earned a long break.", 8)
                if self.args.spicy:
                    self.break_line = "log off. touch actual grass. 🌳"
        else:
            brk = Phase("break", max(60, round(focus.elapsed / 5)))
        self.hook("break_start", brk)
        self.run_phase(live, inp, brk)
        self.hook("break_end", brk)
        self.finish(brk)
        notify("Break over", f"Next: {fmt_minutes(self.focus_min)} of focus", bell)

    def run(self) -> None:
        try:
            with Input() as inp, Live(console=self.console, screen=True,
                                      auto_refresh=False, transient=True) as live:
                while True:
                    self.cycle(live, inp)
        except (Quit, KeyboardInterrupt):
            # keep whatever was done in the unfinished phase
            if self.current:
                self.hook("quit", self.current)
                if self.current.elapsed >= 30:
                    commits = 0
                    if self.repo and self.current.kind == "focus":
                        commits = self.repo.activity_since(self.current.started_at)[0]
                    self.finish(self.current, "stopped", commits)
        finally:
            self.publish(None)
            if self.args.title:
                sys.stdout.write("\x1b]2;\x07")
        self.summary()

    def summary(self) -> None:
        s = self.stats
        table = Table(box=box.SIMPLE_HEAD, show_edge=False, header_style=MUTED)
        table.add_column("#", style=MUTED, justify="right")
        table.add_column("phase")
        table.add_column("planned", justify="right")
        table.add_column("actual", justify="right")
        table.add_column("focus")
        if self.repo:
            table.add_column("commits", justify="right")
        for i, (kind, planned, actual, level, commits) in enumerate(s.history, 1):
            label, color, _ = PHASES[kind]
            row = [str(i), Text(label.title(), style=color),
                   fmt_minutes(planned), fmt_minutes(actual), level]
            if self.repo:
                row.append("" if commits is None else str(commits))
            table.add_row(*row)
        head = Text.assemble(
            ("focused ", MUTED), (fmt_minutes(s.focus_min), "bold #ff6b6b"),
            ("    breaks ", MUTED), (fmt_minutes(s.break_min), "bold #4ecdc4"),
            ("    sessions ", MUTED), (str(s.sessions), "bold"),
            ("    today ", MUTED),
            (fmt_minutes(s.today_before + s.focus_min), "bold #a78bfa"),
        )
        if self.repo:
            head.append("    commits ", style=MUTED)
            head.append(str(s.commits), style="bold #4ade80")
        body = [head]
        if self.progress:
            self.level_up_messages()
            _, title, _, _ = self.progress.level
            body.append(Text.assemble(
                ("level   ", MUTED), (title, "bold #facc15"),
                (f"   {self.progress.xp:,} XP", MUTED),
                (f"   +{self.progress.xp - self.xp_start} this run", "#facc15")))
        body.append(Text(""))
        body.append(table if s.history else Text("No sessions recorded.", style=MUTED))
        body += [Text(""), Text(f"log    {tilde(self.log.path)}", style=MUTED)]
        if s.notes:
            body.append(Text(f"notes  {tilde(self.args.notes)}", style=MUTED))
        body.append(Text("run `promo stats` for your focus history", style=MUTED))
        self.console.print(Panel(Group(*body), title="[bold] PROmodoro [/]",
                                 border_style=MUTED, box=box.ROUNDED,
                                 padding=(1, 2), expand=False))


# --------------------------------------------------------------------------
# promo stats
# --------------------------------------------------------------------------
HEAT = ["#2d333b", "#0e4429", "#006d32", "#26a641", "#39d353"]


def heat_level(minutes: float) -> int:
    if minutes <= 0:
        return 0
    for level, limit in enumerate((30, 90, 180), start=1):
        if minutes < limit:
            return level
    return 4


def cmd_stats(args) -> None:
    console = Console()
    log = Log(args.log)
    focus = [r for r in log.rows() if r.get("phase") == "focus"]
    if not focus:
        console.print(f"[{MUTED}]No focus sessions logged yet in {tilde(log.path)}.[/]")
        return

    by_day: Dict[date, float] = defaultdict(float)
    by_hour = [0.0] * 24
    for r in focus:
        try:
            day = date.fromisoformat(r["date"])
        except (KeyError, ValueError):
            continue
        mins = _num(r.get("actual_min"))
        by_day[day] += mins
        try:
            by_hour[int(r.get("start", "0")[:2])] += mins
        except ValueError:
            pass

    today = date.today()
    weeks = max(4, min(args.weeks, (console.size.width - 10) // 2))
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks - 1)

    # heatmap: rows are weekdays, columns are weeks
    months = [" "] * (weeks * 2)
    last_month = None
    for w in range(weeks):
        monday = start + timedelta(weeks=w)
        if monday.month != last_month and w * 2 + 3 <= len(months):
            if last_month is not None or monday.day <= 7:
                months[w * 2:w * 2 + 3] = monday.strftime("%b")
            last_month = monday.month
    heat = Text("    " + "".join(months) + "\n", style=MUTED)
    for wd, name in enumerate(["Mon", "", "Wed", "", "Fri", "", "Sun"]):
        heat.append(f"{name:<4}", style=MUTED)
        for w in range(weeks):
            day = start + timedelta(weeks=w, days=wd)
            if day > today:
                heat.append("  ")
            else:
                heat.append("■ ", style=HEAT[heat_level(by_day.get(day, 0))])
        heat.append("\n")
    heat.append("    less ", style=MUTED)
    for c in HEAT:
        heat.append("■ ", style=c)
    heat.append("more   (<30m, <1h30, <3h, 3h+ per day)", style=MUTED)

    # streak: consecutive days with focus, ending today (or yesterday)
    streak, day = 0, today if by_day.get(today) else today - timedelta(days=1)
    while by_day.get(day):
        streak += 1
        day -= timedelta(days=1)
    best_streak = run = 0
    prev = None
    for d in sorted(k for k, v in by_day.items() if v > 0):
        run = run + 1 if prev and d - prev == timedelta(days=1) else 1
        best_streak, prev = max(best_streak, run), d

    week_start = today - timedelta(days=today.weekday())
    this_week = sum(v for d, v in by_day.items() if d >= week_start)
    last_week = sum(v for d, v in by_day.items()
                    if week_start - timedelta(days=7) <= d < week_start)
    trend = ""
    if last_week:
        pct = (this_week - last_week) / last_week * 100
        trend = f"  ({'+' if pct >= 0 else ''}{pct:.0f}% vs last week)"

    lengths = [_num(r.get("actual_min")) for r in focus]
    levels = Counter(r.get("focus_level") for r in focus
                     if r.get("focus_level") in {lvl.name for lvl in FOCUS_LEVELS})

    summary = Table.grid(padding=(0, 2))
    summary.add_column(style=MUTED, justify="right")
    summary.add_column()
    summary.add_row("today", fmt_minutes(by_day.get(today, 0)))
    summary.add_row("this week", fmt_minutes(this_week) + trend)
    summary.add_row("streak", f"{streak} day{'s' if streak != 1 else ''}"
                    f"   (best {best_streak})")
    summary.add_row("sessions", f"{len(focus)}   avg {fmt_minutes(sum(lengths) / len(lengths))}"
                    f"   longest {fmt_minutes(max(lengths))}")
    if args.goal:
        met = sum(1 for v in by_day.values() if v >= args.goal)
        summary.add_row("goal", f"{fmt_minutes(args.goal)}/day met on {met} days")
    commits = sum(int(_num(r.get("commits"))) for r in focus
                  if r.get("date", "") >= week_start.isoformat())
    if commits:
        summary.add_row("commits", f"{commits} during focus this week")
    if levels:
        mood = Text()
        total = sum(levels.values())
        for lvl in FOCUS_LEVELS:
            n = levels.get(lvl.name, 0)
            if n:
                mood.append(f"{lvl.name} {n * 100 // total}%  ", style=lvl.style)
        summary.add_row("focus", mood)

    # when in the day do you focus?
    spark = " ▁▂▃▄▅▆▇█"
    peak = max(by_hour) or 1
    hours = Text()
    for mins in by_hour:
        hours.append(spark[min(8, math.ceil(mins / peak * 8))], style="#ff6b6b")
    best = max(range(24), key=lambda h: by_hour[h])
    hours_block = Group(hours, Text("0     6     12    18   23", style=MUTED),
                        Text(f"peak focus around {best:02d}:00", style=MUTED))

    # projects this week
    projects: Dict[str, float] = defaultdict(float)
    for r in focus:
        if r.get("date", "") >= (today - timedelta(days=6)).isoformat():
            projects[r.get("project") or r.get("task") or "(no project)"] += _num(r.get("actual_min"))
    proj = Table.grid(padding=(0, 2))
    proj.add_column(style="bold")
    proj.add_column()
    proj.add_column(justify="right", style=MUTED)
    top = max(projects.values(), default=0) or 1
    for name, mins in sorted(projects.items(), key=lambda kv: -kv[1])[:6]:
        proj.add_row(name[:24], Text("━" * max(1, int(mins / top * 24)), style="#a78bfa"),
                     fmt_minutes(mins))

    game = Table.grid(padding=(0, 2))
    game.add_column(style=MUTED, justify="right")
    game.add_column()
    prog = replay(log.rows())
    n, title, into, span = prog.level
    lvl = Table.grid(padding=(0, 1))
    nxt = f"{span - into:,} XP to {TITLES[n + 1]}" if n + 1 < len(TITLES) else "max level"
    lvl.add_row(Text(title, style="bold #facc15"),
                ProgressBar(total=span, completed=min(into, span), width=20,
                            complete_style="#facc15", finished_style="#facc15"),
                Text(f"{prog.xp:,} XP · {nxt}", style=MUTED))
    game.add_row("level", lvl)
    game.add_row("combo", f"🔥 x{prog.combo} now   (best x{prog.best_combo})")
    badges = Table.grid(padding=(0, 2))
    badges.add_column(no_wrap=True)
    badges.add_column(style=MUTED)
    for key, name, desc in ACHIEVEMENTS:
        got = key in prog.unlocked
        badges.add_row(Text.assemble(("🏆 " if got else "·  ", "" if got else MUTED),
                                     (name, "bold" if got else MUTED)), desc)
    game.add_row("achievements", Text(f"{len(prog.unlocked)}/{len(ACHIEVEMENTS)}"))

    console.print()
    console.print(Text("  PROmodoro · focus history", style="bold"))
    console.print()
    console.print(heat)
    console.print()
    console.print(summary)
    console.print()
    console.print(Text("  time of day", style="bold"))
    console.print(Panel(hours_block, box=box.SIMPLE, padding=(0, 1), expand=False))
    if projects:
        console.print(Text("  last 7 days by project", style="bold"))
        console.print(Panel(proj, box=box.SIMPLE, padding=(0, 1), expand=False))
    console.print(Text("  progress", style="bold"))
    console.print(Panel(Group(game, Text(""), badges), box=box.SIMPLE,
                        padding=(0, 1), expand=False))


# --------------------------------------------------------------------------
# promo status
# --------------------------------------------------------------------------
def running_state() -> Optional[dict]:
    """State of the running timer, or None when no timer is running."""
    try:
        with open(STATE_PATH) as f:
            st = json.load(f)
        os.kill(int(st["pid"]), 0)
        return st
    except (OSError, ValueError, KeyError, TypeError):
        return None


REMOTE_COMMANDS = ("toggle", "pause", "resume", "skip", "stop", "add", "sub",
                   "note", "task", "rate")


def cmd_remote(argv: List[str]) -> int:
    """`promo toggle`, `promo add 5`, `promo note "..."`: drive the running timer."""
    line = " ".join(argv).replace("\n", " ")
    try:
        fd = os.open(CONTROL_PATH, os.O_WRONLY | os.O_NONBLOCK)
    except OSError:
        if argv[0] == "note" and len(argv) > 1:  # notes work without a timer
            cfg = load_config()
            path = cfg.get("notes", os.path.join(DATA_DIR, "notes.md"))
            if append_note(path, " ".join(argv[1:]), "", Repo.detect()):
                print(f"note saved to {tilde(path)}")
                return 0
        print("promo: no timer running (start one with `promo`)", file=sys.stderr)
        return 1
    with os.fdopen(fd, "w") as f:
        f.write(line + "\n")
    return 0


def cmd_status(args) -> None:
    st = running_state()
    if st is None:
        if args.json:
            print(json.dumps({"text": "", "class": "idle"}))
        return
    remaining = (st["remaining"] if st.get("paused") or st.get("ends_at") is None
                 else max(0.0, st["ends_at"] - time.time()))
    label, _, icon = PHASES.get(st.get("phase"), ("", "", ""))
    fields = {
        "icon": "⏸" if st.get("paused") else icon,
        "time": fmt_clock(remaining),
        "phase": label.lower(),
        "task": st.get("task", ""),
        "project": st.get("project", ""),
        "branch": st.get("branch", ""),
        "session": st.get("session", ""),
        "combo": f"🔥{st['combo']}" if st.get("combo", 0) >= 2 else "",
    }
    text = " ".join(args.format.format(**fields).split())
    if args.json:  # waybar custom module
        tooltip = f"{label.title()} · session {fields['session']}"
        if fields["task"]:
            tooltip += f"\n{fields['task']}"
        print(json.dumps({"text": text, "tooltip": tooltip,
                          "class": "paused" if st.get("paused") else st.get("phase"),
                          "percentage": int(100 * (1 - remaining / (st.get("planned") or 1)))}))
    else:
        print(text)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def load_config() -> dict:
    cp = configparser.ConfigParser()
    try:
        cp.read(CONFIG_PATH)
    except configparser.Error as e:
        print(f"promo: ignoring invalid config {CONFIG_PATH}: {e}", file=sys.stderr)
        return {}
    return dict(cp["promo"]) if cp.has_section("promo") else {}


def _bool(value, default: bool) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def common_options(p: argparse.ArgumentParser, cfg: dict) -> None:
    p.add_argument("--log", default=cfg.get("log", os.path.join(DATA_DIR, "sessions.csv")),
                   metavar="PATH", help="CSV session log (default %(default)s)")
    p.add_argument("--goal", type=int, default=int(cfg.get("goal", 0)), metavar="MIN",
                   help="daily focus goal in minutes, 0 to disable (default %(default)s)")


def parse_args(argv: List[str]) -> argparse.Namespace:
    cfg = load_config()
    if argv and argv[0] == "stats":
        p = argparse.ArgumentParser(prog="promo stats",
                                    description="Focus heatmap, streaks and trends.")
        common_options(p, cfg)
        p.add_argument("--weeks", type=int, default=26, help="weeks in the heatmap")
        args = p.parse_args(argv[1:])
        args.command = "stats"
        return args
    if argv and argv[0] == "status":
        p = argparse.ArgumentParser(
            prog="promo status",
            description="Print the running timer for tmux, waybar, polybar or a prompt. "
                        "Prints nothing when no timer is running.")
        p.add_argument("--format", default=cfg.get("status_format", "{icon} {time}"),
                       help="placeholders: {icon} {time} {phase} {task} {project} "
                            "{branch} {session} {combo} (default: %(default)s)")
        p.add_argument("--json", action="store_true", help="waybar JSON output")
        args = p.parse_args(argv[1:])
        args.command = "status"
        return args

    p = argparse.ArgumentParser(
        prog="promo",
        description="Progressive Pomodoro timer: sessions grow with your focus.",
        epilog="subcommands: stats, status, and remote control for a running timer: "
               "toggle, pause, resume, skip, stop, add N, sub N, note TEXT, task TEXT, "
               "rate 1-5.  keys: space pause · s skip · +/- 1 min · n note · "
               "i details · : command · q quit.  "
               f"config: {CONFIG_PATH}",
    )
    p.add_argument("positional", nargs="*", metavar="[hours] [minutes] [task]",
                   help="length of the first session and what you are working on; "
                        "`promo 25 fix login` = 25 minutes, `promo 1 30` = 1h30")
    p.add_argument("-t", "--task", dest="task_opt", metavar="TASK",
                   help="what you are working on")
    common_options(p, cfg)
    p.add_argument("--long-break-after", type=int, metavar="MIN",
                   default=int(cfg.get("long_break_after", 180)),
                   help="focus minutes before a long break (default %(default)s)")
    p.add_argument("--notes", default=cfg.get("notes", os.path.join(DATA_DIR, "notes.md")),
                   metavar="PATH", help="where `n` notes go (default %(default)s)")
    p.add_argument("--hook", default=cfg.get("hook"), metavar="CMD",
                   help="shell command run on focus_start, focus_end, break_start, "
                        "break_end, pause, resume and quit (see README)")
    p.add_argument("--no-bell", dest="bell", action="store_false",
                   default=_bool(cfg.get("bell"), True), help="no terminal bell")
    p.add_argument("--no-git", dest="git", action="store_false",
                   default=_bool(cfg.get("git"), True), help="disable git integration")
    p.add_argument("--spicy", action="store_true", default=_bool(cfg.get("spicy"), False),
                   help="commentary with attitude (skill issue?)")
    p.add_argument("--no-game", dest="game", action="store_false",
                   default=_bool(cfg.get("game"), True),
                   help="hide XP, levels, combos and achievements")
    p.add_argument("--no-title", dest="title", action="store_false",
                   default=_bool(cfg.get("title"), True),
                   help="do not show the countdown in the terminal title")
    args = p.parse_args(argv)
    args.command = "timer"

    nums, words = [], list(args.positional)
    while words and len(nums) < 2 and re.fullmatch(r"\d+", words[0]):
        nums.append(int(words.pop(0)))
    if len(nums) == 2:
        total = nums[0] * 60 + nums[1]
    elif nums:
        total = nums[0]  # `promo 25` means 25 minutes
    else:
        total = int(cfg.get("minutes", 5))
    if total <= 0:
        p.error("the first session must be at least 1 minute")
    if args.long_break_after <= 0:
        p.error("--long-break-after must be positive")
    args.minutes = min(MAX_FOCUS_MINUTES, total)
    args.task = args.task_opt or " ".join(words) or cfg.get("task", "")
    return args


def main(argv: Optional[List[str]] = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in REMOTE_COMMANDS:
        sys.exit(cmd_remote(argv))
    args = parse_args(argv)
    if args.command == "stats":
        cmd_stats(args)
    elif args.command == "status":
        cmd_status(args)
    else:
        st = running_state()
        if st and int(st["pid"]) != os.getpid():
            sys.exit(f"promo is already running (pid {st['pid']}). "
                     "Control it with `promo toggle`, `promo skip` or `promo stop`.")
        App(args).run()


if __name__ == "__main__":
    main()
