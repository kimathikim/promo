"""Render docs/demo.gif: the flip clock ticking, the focus rating, then a break.

Draws promo's real UI with rich, turns each frame into a PNG with a headless
Chromium (Playwright) and stitches them with Pillow. No terminal recording, so
the result is the same on every machine.

    pip install playwright pillow && playwright install chromium
    python3 scripts/demo.py               # writes docs/demo.gif

Set CHROMIUM=/path/to/chrome to use an existing browser.
"""
import io
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TMP = tempfile.mkdtemp(prefix="promo-demo-")
for var in ("XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_CONFIG_HOME"):
    os.environ[var] = os.path.join(TMP, var.lower())  # never touch real history
sys.path.insert(0, ROOT)

import promo  # noqa: E402
from PIL import Image  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402
from rich.console import Console  # noqa: E402
from rich.terminal_theme import MONOKAI  # noqa: E402

W, H = 96, 30


def svg(renderable, title="promo") -> str:
    c = Console(record=True, width=W, height=H, force_terminal=True,
                color_system="truecolor", file=open(os.devnull, "w"))
    c.print(renderable)
    return c.export_svg(title=title, theme=MONOKAI)


def build_frames():
    args = promo.parse_args(["45", "fix", "login", "bug", "--no-sound", "--no-bell"])
    app = promo.App(args)
    app.console = Console(width=W, height=H)
    app.ui.console = app.console
    app.repo = promo.Repo("/x", "api-server", "feat/login-fix", None)
    app.progress = promo.Progress(xp=1720, combo=3, best_combo=6)
    app.stats.sessions = 2
    frames = []  # (svg, milliseconds)

    # 1. focus: the clock ticks down, each digit flipping
    planned, left = 2700, 18 * 60 + 34
    t = time.time()
    app.ui.clock.update(promo.fmt_clock(left), t - 10)
    for i in range(6):
        ph = promo.Phase("focus", planned, elapsed=planned - (left - i) + 0.4)
        now = t + i
        frames.append((svg(app.ui.timer(ph, now)), 90))           # mid-flip
        frames.append((svg(app.ui.timer(ph, now + 0.3)), 910))   # settled

    # 2. session done: pick a rating
    app.focus_min = 45
    for sel, ms in ((1, 500), (2, 500), (3, 1600)):
        app.rating_sel = sel
        frames.append((svg(app.ui.rating(45, (3, 128, 41))), ms))

    # 3. break, with the XP and combo news
    app.progress = promo.Progress(xp=1790, combo=4, best_combo=6)
    app.say("+70 XP   🔥 x4 combo   🏆 In The Zone", 60)
    brk = promo.Phase("break", 540, elapsed=12)
    app.ui.clock.update(promo.fmt_clock(brk.remaining), t - 10)
    frames.append((svg(app.ui.timer(brk, t + 20)), 2800))
    return frames


def main() -> None:
    frames = build_frames()
    images = []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM") or None)
        page = browser.new_page(device_scale_factor=1)
        for markup, _ in frames:
            page.set_content(f"<body style='margin:0;background:#fff'>{markup}</body>")
            png = page.query_selector("svg").screenshot()
            images.append(Image.open(io.BytesIO(png)).convert("RGB"))
        browser.close()
    # one shared palette keeps colours stable between frames
    palette = images[0].quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    gif = [im.quantize(palette=palette, dither=Image.Dither.NONE) for im in images]
    out = os.path.join(ROOT, "docs", "demo.gif")
    gif[0].save(out, save_all=True, append_images=gif[1:], loop=0, optimize=True,
                duration=[ms for _, ms in frames], disposal=1)
    print(f"wrote {out} ({os.path.getsize(out) // 1024} KB, {len(gif)} frames)")


if __name__ == "__main__":
    main()
