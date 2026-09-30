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
import hashlib
import hmac
import html
import http.server
import json
import math
import os
import random
import re
import select
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
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


def focus_by_day(rows: List[dict]) -> Dict[date, float]:
    """Focus minutes per calendar day."""
    by_day: Dict[date, float] = defaultdict(float)
    for r in rows:
        if r.get("phase") != "focus":
            continue
        try:
            by_day[date.fromisoformat(r.get("date") or "")] += _num(r.get("actual_min"))
        except ValueError:
            continue
    return by_day


def current_streak(by_day: Dict[date, float]) -> int:
    """Consecutive days with focus, ending today (or yesterday)."""
    today = date.today()
    streak, day = 0, today if by_day.get(today) else today - timedelta(days=1)
    while by_day.get(day):
        streak += 1
        day -= timedelta(days=1)
    return streak


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


# --------------------------------------------------------------------------
# Sound: synthesised chimes, played with whatever the system already has
# --------------------------------------------------------------------------
# (frequency Hz, seconds) per note; 0 Hz is a rest
SOUNDS = {
    "focus_end": [(784, 0.16), (988, 0.16), (1175, 0.16), (1568, 0.55)],  # rising: done!
    "break_end": [(1047, 0.14), (0, 0.06), (1047, 0.14), (1568, 0.45)],   # back to work
    "long_break_end": [(659, 0.2), (784, 0.2), (1047, 0.6)],
    "kudos": [(1319, 0.08), (1760, 0.22)],
}
SOUND_PLAYERS = [  # first one found wins
    ("pw-play", []), ("paplay", []), ("aplay", ["-q"]), ("afplay", []),
    ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "quiet"]),
]
SAMPLE_RATE = 44100


def synth_wav(path: str, notes: List[Tuple[float, float]], volume: float, repeat: int) -> None:
    """Write a bell-like chime: a few harmonics with a fast attack and soft decay."""
    import struct
    import wave
    frames = bytearray()
    for r in range(repeat):
        for freq, length in notes:
            n = int(SAMPLE_RATE * length)
            for i in range(n):
                t = i / SAMPLE_RATE
                if not freq:
                    frames += b"\0\0"
                    continue
                env = min(1.0, t / 0.005) * math.exp(-t / (length * 0.45 + 0.05))
                v = (math.sin(2 * math.pi * freq * t)
                     + 0.35 * math.sin(4 * math.pi * freq * t)
                     + 0.12 * math.sin(6 * math.pi * freq * t)) / 1.47
                frames += struct.pack("<h", int(32767 * volume * env * v))
        if r < repeat - 1:
            frames += b"\0\0" * int(SAMPLE_RATE * 0.6)
    ensure_dir(path)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(bytes(frames))


def sound_player() -> Optional[List[str]]:
    for exe, extra in SOUND_PLAYERS:
        found = shutil.which(exe)
        if found:
            return [found, *extra]
    return None


def play_sound(kind: str, volume: float = 0.7, repeat: int = 1,
               custom: str = "") -> bool:
    """Play a chime (or the user's own file) without blocking. False if silent."""
    path = os.path.expanduser(custom) if custom else os.path.join(
        CACHE_DIR, "sounds", f"{kind}-{int(volume * 100)}-{repeat}.wav")
    try:
        if not custom and not os.path.exists(path):
            synth_wav(path, SOUNDS[kind], max(0.0, min(1.0, volume)), max(1, repeat))
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            return True
        player = sound_player()
        if not player or not os.path.exists(path):
            return False
        subprocess.Popen([*player, path], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return True
    except (OSError, KeyError, RuntimeError):
        return False


def cmd_sound(argv: List[str]) -> int:
    """`promo sound [kind]`: preview the chimes and show which player is used."""
    cfg = load_config()
    kinds = argv or list(SOUNDS)
    bad = [k for k in kinds if k not in SOUNDS]
    if bad:
        print(f"promo: unknown sound {bad[0]!r}; choose from {', '.join(SOUNDS)}",
              file=sys.stderr)
        return 1
    player = "winsound" if sys.platform == "win32" else (sound_player() or [None])[0]
    if not player:
        print("promo: no audio player found. Install one of: "
              + ", ".join(exe for exe, _ in SOUND_PLAYERS)
              + " (e.g. `sudo apt install pulseaudio-utils` or `alsa-utils`)", file=sys.stderr)
        return 1
    volume = float(cfg.get("volume", 0.7))
    for kind in kinds:
        custom = cfg.get(f"sound_{kind}", "")
        print(f"♪ {kind:<15} {tilde(custom) if custom else 'built-in chime'}  via {os.path.basename(player)}")
        play_sound(kind, volume, 1, custom)
        time.sleep(sum(d for _, d in SOUNDS[kind]) + 0.6)
    return 0


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
            if app.joined:
                top.append(f"   👥 with {app.joined}", style="#4ecdc4")
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
        return Group(top, sub, self._presence(phase)) if app.squad else Group(top, sub)

    def _presence(self, phase: Phase) -> Text:
        """Who else in the squad is online: 'alice 🍅 12m · bob ☕ 3m'."""
        sq = self.app.squad
        line = Text(justify="center", style=MUTED)
        if sq.error and not sq.snap:
            line.append("👥 squad unreachable")
            return line
        if not sq.snap:
            line.append("👥 connecting…")
            return line
        now = time.time()
        others = [m for m in sq.snap["members"]
                  if m["online"] and m["name"] != sq.client.name]
        line.append("👥 ")
        if not others:
            line.append("no one else online")
        for i, m in enumerate(others[:4]):
            if i:
                line.append(" · ")
            focusing = (m.get("state") or {}).get("phase") == "focus"
            line.append(m["name"], style="#ff6b6b" if focusing else MUTED)
            badge = member_badge(m, now)
            if badge:
                line.append(f" {badge}")
        if len(others) > 4:
            line.append(f" +{len(others) - 4}")
        waiting = len(sq.inbox)
        if waiting and phase.kind == "focus":
            line.append(f"   📨 {waiting} on your break", style="#facc15")
        return line

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
        if app.squad and app.squad.snap:
            board = Text()
            now = time.time()
            ranked = sorted(((m, fresh_stats(m, now)) for m in app.squad.snap["members"]),
                            key=lambda ms: -ms[1].get("today_min", 0))
            for i, (m, st) in enumerate(ranked[:5], 1):
                if i > 1:
                    board.append("\n")
                me = m["name"] == app.squad.client.name
                board.append(f"{i}. ", style=MUTED)
                board.append(f"{m['name']:<14}", style="bold" if me else "")
                board.append(f"{fmt_minutes(st.get('today_min', 0)):>7}")
                board.append(f"  {st.get('streak', 0)}d  {st.get('level', '')}", style=MUTED)
            grid.add_row("squad today", board)
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
        self.first_seconds: Optional[float] = getattr(args, "first_seconds", None)
        self.joined: str = getattr(args, "joined", "")
        self.squad: Optional[SquadSync] = None
        if args.squad_client:
            self.squad = SquadSync(args.squad_client)
            self.push_stats()
            self.squad.start()
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

    def alert(self, kind: str, title: str = "", body: str = "") -> None:
        """Chime, terminal bell and desktop notification for an event."""
        a = self.args
        if a.sound:
            play_sound(kind, a.volume, a.sound_repeat if kind != "kudos" else 1,
                       a.sound_files.get(kind, ""))
        if title:
            notify(title, body, a.bell)
        elif a.bell:
            sys.stdout.write("\a")
            sys.stdout.flush()

    def push_stats(self) -> None:
        if self.squad:
            self.squad.stats = squad_stats(self.log.rows(), self.progress)

    def publish(self, phase: Optional[Phase]) -> None:
        """Share state with `promo status` (tmux, waybar, polybar...) and the squad."""
        if phase is None:
            write_state(None)
            if self.squad:
                self.squad.update(None)
            return
        if self.squad:
            self.squad.update({
                "phase": phase.kind, "paused": phase.paused,
                "ends_at": None if phase.paused else time.time() + phase.remaining,
                "remaining": phase.remaining, "planned": phase.planned,
                "task": self.args.task if self.args.share_task else "",
                "project": self.repo.name if self.repo and self.args.share_task else "",
                "combo": self.progress.combo if self.progress else 0,
            })
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
        elif name == "kudos":
            if not self.squad:
                self.say("no squad configured")
            elif not NAME_RE.fullmatch(arg):
                self.say("usage: :kudos NAME")
            else:
                self.squad.emit("kudos", to=arg)
                self.say(f"🔥 sent to {arg}")
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
            if self.squad and phase.kind != "focus" and not self.current_toast():
                news = self.squad.take_inbox()
                if news:
                    me = self.squad.client.name
                    self.say("   ".join(describe_event(e, me) for e in news[-3:]), 8)
                    if any(e["type"] == "kudos" for e in news):
                        self.alert("kudos")
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
            if self.squad:
                self.squad.emit("level_up", title=after.level[1])
        names = {k: n for k, n, _ in ACHIEVEMENTS}
        for k in sorted(after.unlocked - before.unlocked):
            news.append(f"🏆 {names[k]}")
            if self.squad:
                self.squad.emit("achievement", title=names[k])
        return news

    def cycle(self, live: Live, inp: Input) -> None:
        if self.repo:
            self.repo.refresh_branch()
        focus = Phase("focus", self.first_seconds or self.focus_min * 60)
        self.first_seconds = None
        self.hook("focus_start", focus)
        self.run_phase(live, inp, focus)
        self.hook("focus_end", focus)
        focused_min = focus.elapsed / 60
        activity = self.repo.activity_since(focus.started_at) if self.repo else (0, 0, 0)
        self.alert("focus_end", "Focus session done", f"{fmt_minutes(focused_min)} focused")

        # rate before logging so the level lands on the focus row
        level = self.ask_level(live, inp, focused_min, activity)
        self.finish(focus, level.name, activity[0])
        self.joined = ""
        if self.squad and focused_min >= 1:
            self.squad.emit("session", minutes=round(focused_min), level=level.name,
                            commits=activity[0])
        if level.delta:
            self.focus_min = clamp_focus(self.focus_min + level.delta)
        news = self.level_up_messages()
        self.push_stats()
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
        self.alert("long_break_end" if brk.kind == "long_break" else "break_end",
                   "Break over", f"Next: {fmt_minutes(self.focus_min)} of focus")

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
            if self.squad:
                self.push_stats()
                self.squad.stop()
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
# Squad: see how your friends are doing. Self-hosted, standard library only.
#
#   promo serve                  run a squad server (one per team / community)
#   squad = http://host:8787/r/ROOM   in config.ini to join a room
# --------------------------------------------------------------------------
NAME_RE = re.compile(r"[A-Za-z0-9_.-]{1,24}")
ROOM_RE = re.compile(r"[A-Za-z0-9_.-]{1,40}")
ONLINE_SECONDS = 90
HEARTBEAT_SECONDS = 30
EVENT_TYPES = {"session", "achievement", "level_up", "kudos"}
MAX_BODY = 16 * 1024


def clean_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]", "", re.sub(r"\s+", "-", str(value).strip()))
    return value[:24] or "anon"


def default_squad_name(cfg: dict) -> str:
    if cfg.get("squad_name"):
        return clean_name(cfg["squad_name"])
    return clean_name(git("config", "--global", "user.name")
                      or os.environ.get("USER") or "anon")


def _clip(value, kind, limit):
    """Coerce untrusted JSON values: kind is str, int or float."""
    try:
        if kind is str:
            return str(value)[:limit] if value is not None else ""
        v = kind(value)
        return max(-limit, min(limit, v))
    except (TypeError, ValueError):
        return kind() if kind is not str else ""


def _clean_state(st) -> Optional[dict]:
    if not isinstance(st, dict) or st.get("phase") not in PHASES:
        return None
    return {
        "phase": st["phase"],
        "paused": bool(st.get("paused")),
        "ends_at": _clip(st.get("ends_at"), float, 1e10) if st.get("ends_at") else None,
        "remaining": _clip(st.get("remaining"), float, 86400),
        "planned": _clip(st.get("planned"), float, 86400),
        "task": _clip(st.get("task"), str, 80),
        "project": _clip(st.get("project"), str, 40),
        "combo": _clip(st.get("combo"), int, 10000),
    }


def _clean_stats(st) -> dict:
    st = st if isinstance(st, dict) else {}
    out = {"today_min": _clip(st.get("today_min"), float, 1440),  # nobody does 25h days
           "week_min": _clip(st.get("week_min"), float, 10080)}
    out.update({k: _clip(st.get(k), int, 10 ** 7)
                for k in ("streak", "xp", "sessions", "best_combo")})
    out["level"] = st.get("level") if st.get("level") in TITLES else TITLES[0]
    out["day"] = st.get("day") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(st.get("day"))) else ""
    out["week"] = st.get("week") if re.fullmatch(r"\d{4}-W\d{2}", str(st.get("week"))) else ""
    return out


def fresh_stats(m: dict, now: float) -> dict:
    """Stats with stale periods zeroed: yesterday's 'today' must not keep
    someone on top (same rules as the web leaderboard)."""
    st = dict(m.get("stats") or {})
    seen = now - (m.get("last_seen") or 0)
    today = date.today()
    try:
        day_gap = abs((date.fromisoformat(st.get("day", "")) - today).days)
    except ValueError:
        day_gap = None
    if not (day_gap == 0 or (day_gap is not None and day_gap <= 1 and seen < 43200)
            or (day_gap is None and seen < 86400)):
        st["today_min"] = 0
    iso = today.isocalendar()
    if not (st.get("week") == f"{iso[0]}-W{iso[1]:02d}" or seen < 86400
            or (not st.get("week") and seen < 604800)):
        st["week_min"] = 0
    if seen >= 172800:
        st["streak"] = 0
    return st


def _clean_event(ev) -> Optional[dict]:
    if not isinstance(ev, dict) or ev.get("type") not in EVENT_TYPES:
        return None
    data = {}
    for key in ("title", "level", "to"):
        if key in ev:
            data[key] = _clip(ev[key], str, 40)
    for key in ("minutes", "commits"):
        if key in ev:
            data[key] = _clip(ev[key], int, 100000)
    if ev["type"] == "kudos" and not NAME_RE.fullmatch(data.get("to", "")):
        return None
    return {"type": ev["type"], **data}


class SquadStore:
    """Rooms, members and a short event feed, persisted to one JSON file."""

    def __init__(self, path: str):
        self.path = os.path.expanduser(path)
        self.lock = threading.Lock()
        self.rooms: Dict[str, dict] = {}
        self._saved = 0.0
        try:
            with open(self.path) as f:
                self.rooms = json.load(f).get("rooms", {})
        except (OSError, ValueError):
            pass

    def _room(self, name: str) -> dict:
        return self.rooms.setdefault(name, {"members": {}, "events": [], "seq": 0})

    def _save(self, force: bool = False) -> None:
        if not force and time.time() - self._saved < 10:
            return
        try:
            ensure_dir(self.path)
            tmp = self.path + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"rooms": self.rooms}, f)
            os.replace(tmp, self.path)
            self._saved = time.time()
        except OSError:
            pass

    def _add_events(self, room: dict, name: str, events) -> bool:
        added = False
        for ev in (events if isinstance(events, list) else [])[:20]:
            ev = _clean_event(ev)
            if ev:
                room["seq"] += 1
                room["events"].append({"seq": room["seq"], "t": time.time(),
                                       "name": name, **ev})
                added = True
        room["events"] = room["events"][-300:]
        return added

    def snapshot(self, room_name: str, since: int = 0) -> dict:
        with self.lock:
            room = self._room(room_name)
            now = time.time()
            members = []
            for m in room["members"].values():
                online = not m.get("offline") and now - m.get("last_seen", 0) < ONLINE_SECONDS
                members.append({"name": m["name"], "online": online,
                                "last_seen": m.get("last_seen", 0),
                                "state": m.get("state") if online else None,
                                "stats": m.get("stats", {})})
            members.sort(key=lambda m: -m["stats"].get("today_min", 0))
            events = [e for e in room["events"] if e["seq"] > since][-50:]
            return {"room": room_name, "now": now, "cursor": room["seq"],
                    "heartbeat": HEARTBEAT_SECONDS, "members": members, "events": events}

    @staticmethod
    def _claim(member: dict, key: str) -> None:
        """The first client to use a name owns it; later writes need its key."""
        digest = hashlib.sha256(key.encode()).hexdigest() if key else ""
        if member.get("key") and not hmac.compare_digest(member["key"], digest):
            raise PermissionError(f"the name {member['name']!r} is taken in this room")
        if digest:
            member["key"] = digest

    def heartbeat(self, room_name: str, body: dict, key: str = "") -> dict:
        name = body.get("name", "")
        if not NAME_RE.fullmatch(str(name)):
            raise ValueError("invalid name")
        with self.lock:
            room = self._room(room_name)
            member = room["members"].get(name, {"name": name})
            self._claim(member, key)
            room["members"][name] = member
            member["last_seen"] = time.time()
            member["offline"] = bool(body.get("offline"))
            member["state"] = _clean_state(body.get("state"))
            if "stats" in body:
                member["stats"] = _clean_stats(body.get("stats"))
            added = self._add_events(room, name, body.get("events"))
            self._save(force=added)
        return self.snapshot(room_name, _clip(body.get("since"), int, 10 ** 12))

    def post_events(self, room_name: str, body: dict, key: str = "") -> dict:
        name = body.get("name", "")
        if not NAME_RE.fullmatch(str(name)):
            raise ValueError("invalid name")
        with self.lock:
            member = self._room(room_name)["members"].get(name)
            if member:
                self._claim(member, key)
            if self._add_events(self._room(room_name), name, body.get("events")):
                self._save(force=True)
        return {"ok": True}


def describe_event(ev: dict, me: str = "") -> str:
    who, kind = ev.get("name", "?"), ev.get("type")
    if kind == "session":
        text = f"{who} finished {fmt_minutes(ev.get('minutes', 0))}"
        if ev.get("level"):
            text += f" ({ev['level']})"
        return text
    if kind == "achievement":
        return f"🏆 {who} unlocked {ev.get('title', '?')}"
    if kind == "level_up":
        return f"⬆ {who} is now {ev.get('title', '?')}"
    if kind == "kudos":
        to = ev.get("to", "?")
        return f"🔥 {who} sent you kudos" if to == me else f"{who} sent 🔥 to {to}"
    return f"{who}: {kind}"


def member_badge(m: dict, now: float) -> str:
    """'🍅 12m' for a member's current state, '' when idle."""
    st = m.get("state")
    if not st:
        return ""
    if st.get("paused"):
        return "⏸"
    remaining = st.get("remaining", 0)
    if st.get("ends_at"):
        remaining = st["ends_at"] - now
    if remaining <= 0:
        return "✔ done" if st["phase"] == "focus" else "back soon"
    return f"{PHASES[st['phase']][2]} {math.ceil(remaining / 60)}m"


DASHBOARD = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="15"><meta name="theme-color" content="#141110">
<title>promo · {room}</title>
<style>
:root{{--tomato:#c4361c;--ink:#141110;--cream:#fff4e6;--fg2:#c9bfb3;--line:rgba(255,244,230,.16);--leaf:#9be564}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--ink);color:var(--cream);
font:16px/1.7 "Archivo","Helvetica Neue",Arial,sans-serif;-webkit-font-smoothing:antialiased}}
::selection{{background:var(--leaf);color:var(--ink)}}
main{{max-width:1100px;margin:auto;padding:56px 24px}}
h1,h2{{font-family:"Newsreader","Times New Roman",Georgia,serif;font-weight:300;
text-transform:uppercase;letter-spacing:.03em;margin:0}}
h1{{font-size:clamp(48px,8vw,104px);line-height:.95}}
h2{{font-size:clamp(28px,4vw,48px);margin:64px 0 20px;padding-bottom:14px;border-bottom:1px solid var(--line)}}
.eyebrow,th,.cap{{font-size:13px;font-weight:500;text-transform:uppercase;letter-spacing:.1em;color:var(--fg2)}}
.eyebrow{{font-family:"Courier Prime","Courier New",monospace;margin:0 0 20px}}
table{{width:100%;border-collapse:collapse}}
th,td{{padding:12px 10px;text-align:left;border-bottom:1px solid var(--line)}}
td{{font-weight:600;text-transform:uppercase;letter-spacing:.06em}}
.num{{text-align:right;font-family:"Newsreader","Times New Roman",Georgia,serif;font-weight:300;
font-size:22px;letter-spacing:.02em;text-transform:none}}
.rank{{font-family:"Newsreader","Times New Roman",Georgia,serif;font-weight:300;font-size:28px;color:var(--cream)}}
h1{{color:var(--tomato)}}
.lvl{{font:400 13px "Courier Prime","Courier New",monospace;color:var(--fg2);letter-spacing:.08em}}
.on{{display:inline-block;width:8px;height:8px;margin-left:8px;background:var(--leaf)}}
.now{{font-size:20px}}.now b{{color:var(--leaf);font-weight:600}}
ul{{list-style:none;margin:0;padding:0;font:15px/1.6 "Courier Prime","Courier New",monospace}}
li{{padding:10px 0;border-bottom:1px solid var(--line)}}li time{{color:var(--fg2);margin-right:16px}}
code{{font-family:"Courier Prime","Courier New",monospace}}
th.r{{text-align:right}}.now span{{color:var(--fg2);font:400 14px "Courier Prime","Courier New",monospace;letter-spacing:.08em;text-transform:uppercase}}
footer{{margin-top:48px}}
</style></head><body><main>
<p class="eyebrow">promo squad / {room}</p>
<h1>Focus,<br>together.</h1>
<h2>Right now</h2><p class="now">{now}</p>
<h2>Today</h2><table><tr><th>Rank</th><th>Developer</th><th class="r">Today</th>
<th class="r">Week</th><th class="r">Streak</th><th>Level</th></tr>{rows}</table>
<h2>The feed</h2><ul>{feed}</ul>
<footer class="cap">Refreshes every 15 s · join with <code>promo squad join {url}</code></footer>
</main></body></html>"""


def render_dashboard(snap: dict, url: str) -> str:
    esc = html.escape
    now = snap["now"]
    def badge(m):  # "focus 12m" instead of the terminal's emoji
        text = re.sub(r"^[^A-Za-z0-9]+", "", member_badge(m, now))
        return f"{PHASES[m['state']['phase']][0].lower()} {text}" if text[:1].isdigit() else text
    focusing = [f"<b>{esc(m['name'])}</b> <span>{esc(badge(m))}</span>"
                for m in snap["members"] if m["online"] and m.get("state")]
    ranked = sorted(((m, fresh_stats(m, now)) for m in snap["members"]),
                    key=lambda ms: -ms[1].get("today_min", 0))
    rows = "".join(
        f"<tr><td class='rank'>{i:02d}</td><td>{esc(m['name'])}"
        f"{'<span class=on></span>' if m['online'] else ''}</td>"
        f"<td class='num'>{esc(fmt_minutes(st.get('today_min', 0)))}</td>"
        f"<td class='num'>{esc(fmt_minutes(st.get('week_min', 0)))}</td>"
        f"<td class='num'>{st.get('streak', 0)}d</td>"
        f"<td class='lvl'>{esc(st.get('level', ''))}</td></tr>"
        for i, (m, st) in enumerate(ranked, 1))
    # the web look is text-only: drop the leading emoji the terminal uses
    feed = "".join(
        f"<li><time>{esc(datetime.fromtimestamp(e['t']).strftime('%a %H:%M'))}</time>"
        f"{esc(re.sub(r'^[^A-Za-z0-9]+', '', describe_event(e)))}</li>"
        for e in reversed(snap["events"][-20:]))
    return DASHBOARD.format(room=esc(snap["room"]), url=esc(url),
                            now=" · ".join(focusing) or "Nobody is focusing right now.",
                            rows=rows or "<tr><td colspan=6>No members yet</td></tr>",
                            feed=feed or "<li>Nothing yet</li>")


def make_squad_handler(store: SquadStore, token: str):
    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "promo-squad"

        def log_message(self, fmt, *a):  # quiet access log
            pass

        def _send(self, code: int, body, ctype="application/json") -> None:
            data = (json.dumps(body) if ctype == "application/json" else body).encode()
            self.send_response(code)
            self.send_header("Content-Type", f"{ctype}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _route(self):
            url = urllib.parse.urlsplit(self.path)
            m = re.fullmatch(r"/r/([^/]+)(/api(?:/(heartbeat|event))?)?/?", url.path)
            if not m or not ROOM_RE.fullmatch(m.group(1)):
                return None
            query = urllib.parse.parse_qs(url.query)
            return m.group(1), bool(m.group(2)), m.group(3), query

        def _authorized(self, query) -> bool:
            if not token:
                return True
            supplied = self.headers.get("Authorization", "")
            if supplied.startswith("Bearer "):
                supplied = supplied[7:]
            else:
                supplied = (query.get("key") or [""])[0]
            return hmac.compare_digest(supplied.encode(), token.encode())

        def do_GET(self):
            route = self._route()
            if not route:
                return self._send(404, {"error": "use /r/<room>"})
            room, api, action, query = route
            if not self._authorized(query):
                return self._send(401, {"error": "bad or missing token"})
            since = _clip((query.get("since") or ["0"])[0], int, 10 ** 12)
            snap = store.snapshot(room, since)
            if api:
                return self._send(200, snap)
            host = self.headers.get("Host", "localhost")
            self._send(200, render_dashboard(snap, f"http://{host}/r/{room}"), "text/html")

        def do_POST(self):
            route = self._route()
            if not route or not route[1] or not route[2]:
                return self._send(404, {"error": "not found"})
            room, _, action, query = route
            if not self._authorized(query):
                return self._send(401, {"error": "bad or missing token"})
            length = _clip(self.headers.get("Content-Length"), int, 10 ** 9)
            if length <= 0 or length > MAX_BODY:
                return self._send(413, {"error": "body too large"})
            try:
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError("expected an object")
                key = self.headers.get("X-Promo-Key", "")
                result = (store.heartbeat(room, body, key) if action == "heartbeat"
                          else store.post_events(room, body, key))
            except PermissionError as e:
                return self._send(403, {"error": str(e)})
            except ValueError as e:
                return self._send(400, {"error": str(e)})
            self._send(200, result)

    return Handler


def cmd_serve(argv: List[str]) -> None:
    cfg = load_config()
    p = argparse.ArgumentParser(prog="promo serve",
                                description="Run a squad server your friends can join.")
    p.add_argument("--host", default=cfg.get("serve_host", "127.0.0.1"),
                   help="interface to listen on; 0.0.0.0 for everyone (default %(default)s)")
    p.add_argument("--port", type=int, default=int(cfg.get("serve_port", 8787)))
    p.add_argument("--token", default=os.environ.get("PROMO_SQUAD_TOKEN")
                   or cfg.get("serve_token", ""),
                   help="shared secret members must send (or set PROMO_SQUAD_TOKEN)")
    p.add_argument("--data", default=os.path.join(DATA_DIR, "squad.json"),
                   help="where rooms are stored (default %(default)s)")
    args = p.parse_args(argv)
    store = SquadStore(args.data)
    server = http.server.ThreadingHTTPServer((args.host, args.port),
                                             make_squad_handler(store, args.token))
    shown = "localhost" if args.host in ("0.0.0.0", "127.0.0.1", "") else args.host
    print(f"promo squad server on http://{args.host}:{args.port}")
    print(f"  dashboard   http://{shown}:{args.port}/r/<room>"
          + ("?key=<token>" if args.token else ""))
    print(f"  members add to ~/.config/promo/config.ini:\n"
          f"      squad = http://{shown}:{args.port}/r/<room>")
    if args.token:
        print("      squad_token = <token>")
    else:
        print("  warning: no --token set, anyone who can reach this port can join")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        with store.lock:
            store._save(force=True)


def member_key() -> str:
    """Random per-install secret that proves you own your squad name."""
    path = os.path.join(DATA_DIR, "member.key")
    try:
        with open(path) as f:
            key = f.read().strip()
        if key:
            return key
    except OSError:
        pass
    key = os.urandom(24).hex()
    try:
        ensure_dir(path)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(key)
    except OSError:
        pass
    return key


class SquadClient:
    def __init__(self, url: str, token: str, name: str):
        self.base, self.token, self.name = url.rstrip("/"), token, name
        self.key = member_key()

    def request(self, path: str, body: Optional[dict] = None, timeout: float = 4) -> dict:
        req = urllib.request.Request(
            self.base + path, method="POST" if body is not None else "GET",
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", "User-Agent": "promo",
                     "X-Promo-Key": self.key,
                     **({"Authorization": f"Bearer {self.token}"} if self.token else {})})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read()).get("error", "")
            except ValueError:
                detail = ""
            raise OSError(f"squad server said {e.code} {detail}".strip()) from None
        except (urllib.error.URLError, ValueError) as e:
            raise OSError(f"squad unreachable: {getattr(e, 'reason', e)}") from None

    def snapshot(self) -> dict:
        return self.request("/api")

    def send(self, events: List[dict]) -> None:
        self.request("/api/event", {"name": self.name, "events": events})


class SquadSync(threading.Thread):
    """Background heartbeat so the timer never waits on the network."""

    def __init__(self, client: SquadClient):
        super().__init__(daemon=True)
        self.client = client
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.state: Optional[dict] = None
        self.stats: dict = {}
        self.outbox: List[dict] = []
        self.snap: Optional[dict] = None
        self.inbox: List[dict] = []
        self.error = ""
        self.since: Optional[int] = None
        self._stopping = False
        self._beat_lock = threading.Lock()  # the offline beat must land last

    def update(self, state: Optional[dict], stats: Optional[dict] = None) -> None:
        with self.lock:
            self.state = state
            if stats is not None:
                self.stats = stats
        self.wake.set()

    def emit(self, kind: str, **data) -> None:
        with self.lock:
            self.outbox.append({"type": kind, **data})
        self.wake.set()

    def take_inbox(self) -> List[dict]:
        with self.lock:
            items, self.inbox = self.inbox, []
        return items

    def beat(self, offline: bool = False) -> None:
        with self._beat_lock:
            if self._stopping and not offline:
                return
            self._beat(offline)

    def _beat(self, offline: bool) -> None:
        with self.lock:
            events, self.outbox = self.outbox, []
            payload = {"name": self.client.name, "state": None if offline else self.state,
                       "stats": self.stats, "events": events, "since": self.since or 0,
                       "offline": offline}
        try:
            snap = self.client.request("/api/heartbeat", payload, timeout=2 if offline else 4)
        except OSError as e:
            with self.lock:
                self.error = str(e)
                self.outbox = events + self.outbox  # retry next beat
            return
        with self.lock:
            self.error = ""
            self.snap = snap
            if self.since is not None:  # history before we joined is not news
                self.inbox += [e for e in snap["events"]
                               if e["name"] != self.client.name
                               and (e["type"] != "kudos" or e.get("to") == self.client.name)]
            self.since = snap["cursor"]

    def run(self) -> None:
        while not self._stopping:
            self.beat()
            interval = (self.snap or {}).get("heartbeat", HEARTBEAT_SECONDS)
            self.wake.wait(max(10, min(600, _clip(interval, int, 600))))
            self.wake.clear()

    def stop(self) -> None:
        self._stopping = True
        self.wake.set()
        self.beat(offline=True)


def squad_client(cfg: dict) -> Optional[SquadClient]:
    url = cfg.get("squad", "")
    if not url:
        return None
    return SquadClient(url, cfg.get("squad_token", ""), default_squad_name(cfg))


def squad_stats(rows: List[dict], progress: Optional[Progress]) -> dict:
    by_day = focus_by_day(rows)
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    out = {"today_min": round(by_day.get(today, 0), 1),
           "week_min": round(sum(v for d, v in by_day.items() if d >= week_start), 1),
           "streak": current_streak(by_day),
           "sessions": sum(1 for r in rows if r.get("phase") == "focus"),
           "day": today.isoformat(),
           "week": "{}-W{:02d}".format(*today.isocalendar()[:2])}
    if progress:
        out.update(xp=progress.xp, level=progress.level[1], best_combo=progress.best_combo)
    return out


def cmd_squad_join(argv: List[str]) -> int:
    """`promo squad join URL [--name N] [--token T]`: write the squad config."""
    p = argparse.ArgumentParser(prog="promo squad join",
                                description="Join a squad room or the public leaderboard.")
    p.add_argument("url", help="room URL, e.g. https://promo-seven-virid.vercel.app/r/global")
    p.add_argument("--name", help="your name on the board (default: git user.name)")
    p.add_argument("--token", default="", help="token for a private room")
    args = p.parse_args(argv)
    url = args.url.rstrip("/")
    if not re.match(r"https?://[^/]+/r/[A-Za-z0-9_.-]{1,40}$", url):
        if re.match(r"https?://[^/]+$", url):
            url += "/r/global"
        else:
            p.error("expected a room URL like https://host/r/room")
    values = {"squad": url, "squad_name": clean_name(args.name or default_squad_name(load_config()))}
    if args.token:
        values["squad_token"] = args.token
    try:
        with open(CONFIG_PATH) as f:
            lines = f.read().splitlines()
    except OSError:
        lines = []
    if not any(line.strip() == "[promo]" for line in lines):
        lines = ["[promo]"] + lines
    for key, value in values.items():
        pattern = re.compile(rf"^\s*{key}\s*=")
        hit = [i for i, line in enumerate(lines) if pattern.match(line)]
        if hit:
            lines[hit[0]] = f"{key} = {value}"
        else:
            lines.insert(lines.index("[promo]") + 1, f"{key} = {value}")
    ensure_dir(CONFIG_PATH)
    with open(CONFIG_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    cfg = load_config()
    client = squad_client(cfg)
    rows = Log(cfg.get("log", os.path.join(DATA_DIR, "sessions.csv"))).rows()
    try:
        client.request("/api/heartbeat", {"name": client.name, "state": None,
                                          "stats": squad_stats(rows, replay(rows))})
    except OSError as e:
        print(f"saved to {tilde(CONFIG_PATH)}, but the server said: {e}", file=sys.stderr)
        return 1
    print(f"✓ joined {url} as {client.name}. Your next `promo` session shows up on the board.")
    return 0


def cmd_squad(argv: List[str]) -> int:
    if argv and argv[0] == "join":
        return cmd_squad_join(argv[1:])
    cfg = load_config()
    p = argparse.ArgumentParser(prog="promo squad", description="Your squad's leaderboard.")
    p.add_argument("--watch", action="store_true", help="refresh every 5 seconds")
    args = p.parse_args(argv)
    client = squad_client(cfg)
    if not client:
        print("promo: no squad configured. Add `squad = http://host:8787/r/<room>` to "
              f"{tilde(CONFIG_PATH)} (see `promo serve --help`).", file=sys.stderr)
        return 1
    console = Console()

    def render():
        snap = client.snapshot()
        now = snap["now"]
        board = Table(box=box.SIMPLE_HEAD, show_edge=False, header_style=MUTED)
        for col, kw in (("#", {"style": MUTED, "justify": "right"}), ("dev", {}),
                        ("now", {}), ("today", {"justify": "right"}),
                        ("week", {"justify": "right"}), ("streak", {"justify": "right"}),
                        ("level", {}), ("best combo", {"justify": "right"})):
            board.add_column(col, **kw)
        members = sorted(snap["members"], key=lambda m: -fresh_stats(m, now).get("today_min", 0))
        for i, m in enumerate(members, 1):
            st = fresh_stats(m, now)
            name = Text(m["name"], style="bold" if m["name"] == client.name else "")
            if m["online"]:
                name.append(" ●", style=PHASES["focus"][1])
            board.add_row(str(i), name, member_badge(m, now),
                          fmt_minutes(st.get("today_min", 0)),
                          fmt_minutes(st.get("week_min", 0)),
                          f"{st.get('streak', 0)}d", Text(st.get("level", ""), style="#facc15"),
                          f"x{st.get('best_combo', 0)}")
        feed = Text()
        for e in reversed(snap["events"][-8:]):
            feed.append(f"{datetime.fromtimestamp(e['t']):%a %H:%M}  ", style=MUTED)
            feed.append(describe_event(e, client.name) + "\n")
        return Group(Text(f"  🍅 squad · {snap['room']}", style="bold"), Text(""),
                     board if snap["members"] else Text("  no members yet", style=MUTED),
                     Text(""), Text("  feed", style="bold"),
                     Panel(feed if feed.plain else Text("nothing yet", style=MUTED),
                           box=box.SIMPLE, expand=False))
    try:
        if not args.watch:
            console.print(render())
            return 0
        with Live(render(), console=console, auto_refresh=False) as live:
            while True:
                time.sleep(5)
                live.update(render(), refresh=True)
    except OSError as e:
        print(f"promo: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0


def cmd_kudos(argv: List[str]) -> int:
    client = squad_client(load_config())
    if not client or len(argv) != 1 or not NAME_RE.fullmatch(argv[0]):
        print("usage: promo kudos NAME   (needs `squad =` in your config)", file=sys.stderr)
        return 1
    try:
        client.send([{"type": "kudos", "to": argv[0]}])
    except OSError as e:
        print(f"promo: {e}", file=sys.stderr)
        return 1
    print(f"🔥 sent to {argv[0]}")
    return 0


def find_focusing(client: SquadClient, name: str) -> float:
    """Seconds left in `name`'s focus session, for `promo join`."""
    snap = client.snapshot()
    for m in snap["members"]:
        if m["name"].lower() == name.lower():
            st = m.get("state")
            if not m["online"] or not st or st["phase"] != "focus":
                raise OSError(f"{m['name']} is not focusing right now")
            if st.get("paused") or not st.get("ends_at"):
                raise OSError(f"{m['name']} is paused")
            left = st["ends_at"] - snap["now"]
            if left < 60:
                raise OSError(f"{m['name']}'s session ends in under a minute, catch the next one")
            return left
    raise OSError(f"no one called {name} in this squad")


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

    by_day = focus_by_day(focus)
    by_hour = [0.0] * 24
    for r in focus:
        try:
            by_hour[int(r.get("start", "0")[:2])] += _num(r.get("actual_min"))
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

    streak = current_streak(by_day)
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
# promo card: an SVG stats card for your GitHub profile README
# --------------------------------------------------------------------------
def cmd_card(argv: List[str]) -> int:
    cfg = load_config()
    p = argparse.ArgumentParser(prog="promo card",
                                description="Write an SVG stats card for a README.")
    p.add_argument("-o", "--output", default="promo-card.svg")
    p.add_argument("--log", default=cfg.get("log", os.path.join(DATA_DIR, "sessions.csv")))
    p.add_argument("--name", default=default_squad_name(cfg))
    args = p.parse_args(argv)
    rows = Log(args.log).rows()
    prog, by_day = replay(rows), focus_by_day(rows)
    today = date.today()
    week = sum(v for d, v in by_day.items() if d > today - timedelta(days=7))
    n, title, into, span = prog.level
    esc = html.escape
    weeks = 17
    start = today - timedelta(days=today.weekday()) - timedelta(weeks=weeks - 1)
    # one hue rising in brightness (colour-blind safe): ink -> tomato -> cream
    heat = ["rgba(255,244,230,0.07)", "rgba(196,54,28,0.4)", "rgba(196,54,28,0.7)",
            "#c4361c", "#ffb59e"]
    cells = []
    for w in range(weeks):
        for wd in range(7):
            d = start + timedelta(weeks=w, days=wd)
            if d <= today:
                cells.append(f'<rect x="{276 + w * 11}" y="{146 + wd * 11}" width="9" '
                             f'height="9" fill="{heat[heat_level(by_day.get(d, 0))]}"/>')
    bar = 200 * min(1.0, into / span) if span else 200
    stats = [("This week", fmt_minutes(week)), ("Streak", f"{current_streak(by_day)} days"),
             ("Sessions", str(sum(1 for r in rows if r.get("phase") == "focus"))),
             ("Best combo", f"×{prog.best_combo}"),
             ("Achievements", f"{len(prog.unlocked)}/{len(ACHIEVEMENTS)}")]
    lines = "".join(
        f'<text x="24" y="{146 + i * 15}" class="k">{k}</text>'
        f'<text x="244" y="{146 + i * 15}" class="v" text-anchor="end">{esc(v)}</text>'
        for i, (k, v) in enumerate(stats))
    serif = "Newsreader,'Times New Roman',Georgia,serif"
    sans = "Archivo,'Helvetica Neue',Arial,sans-serif"
    mono = "'Courier Prime','Courier New',monospace"
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="480" height="230" viewBox="0 0 480 230">
<style>
.e{{font:400 10px {mono};letter-spacing:.1em;fill:#c9bfb3;text-transform:uppercase}}
.d{{font:300 28px {serif};letter-spacing:.03em;fill:#fff4e6;text-transform:uppercase}}
.k{{font:500 10px {sans};letter-spacing:.1em;fill:#c9bfb3;text-transform:uppercase}}
.v{{font:300 14px {serif};letter-spacing:.02em;fill:#fff4e6}}
.x{{font:400 10px {mono};letter-spacing:.08em;fill:#9be564}}
</style>
<rect width="480" height="230" fill="#141110"/>
<rect width="480" height="4" fill="#c4361c"/>
<text x="24" y="32" class="e">PROMO / {esc(args.name.upper())}</text>
<text x="24" y="76" class="d">{esc(title.upper())}</text>
<rect x="24" y="92" width="200" height="2" fill="rgba(255,244,230,0.16)"/>
<rect x="24" y="92" width="{bar:.0f}" height="2" fill="#c4361c"/>
<text x="24" y="112" class="x">{prog.xp:,} XP</text>
<line x1="24" y1="126" x2="244" y2="126" stroke="rgba(255,244,230,0.16)"/>
{lines}
<text x="276" y="134" class="k">Last {weeks} weeks</text>
{"".join(cells)}
</svg>
"""
    with open(args.output, "w") as f:
        f.write(svg)
    print(f"wrote {args.output}")
    return 0


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
        epilog="subcommands: stats, status, sound, card, squad, serve, join NAME, kudos NAME, "
               "and remote control for a running timer: "
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
    p.add_argument("--no-sound", dest="sound", action="store_false",
                   default=_bool(cfg.get("sound"), True),
                   help="no chime when a phase ends (preview with `promo sound`)")
    p.add_argument("--no-git", dest="git", action="store_false",
                   default=_bool(cfg.get("git"), True), help="disable git integration")
    p.add_argument("--no-squad", dest="squad", action="store_false", default=True,
                   help="don't connect to the squad for this run")
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
    args.share_task = _bool(cfg.get("share_task"), False)
    try:
        args.volume = max(0.0, min(1.0, float(cfg.get("volume", 0.7))))
        args.sound_repeat = max(1, min(10, int(cfg.get("sound_repeat", 2))))
    except ValueError:
        p.error("config: volume must be 0-1 and sound_repeat a whole number")
    args.sound_files = {k: cfg[f"sound_{k}"] for k in SOUNDS if cfg.get(f"sound_{k}")}
    args.squad_client = squad_client(cfg) if args.squad else None
    return args


def main(argv: Optional[List[str]] = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in REMOTE_COMMANDS:
        sys.exit(cmd_remote(argv))
    simple = {"serve": cmd_serve, "squad": cmd_squad, "kudos": cmd_kudos, "card": cmd_card,
              "sound": cmd_sound}
    if argv and argv[0] in simple:
        sys.exit(simple[argv[0]](argv[1:]) or 0)
    joined, first_seconds = "", None
    if argv and argv[0] == "join":
        client = squad_client(load_config())
        if not client or len(argv) < 2:
            sys.exit("usage: promo join NAME [task]   (needs `squad =` in your config)")
        try:
            first_seconds = find_focusing(client, argv[1])
        except OSError as e:
            sys.exit(f"promo: {e}")
        joined, argv = argv[1], [str(max(MIN_FOCUS_MINUTES, round(first_seconds / 60)))] + argv[2:]
    args = parse_args(argv)
    args.joined, args.first_seconds = joined, first_seconds
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
