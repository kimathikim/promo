# Contributing to promo

Thanks for helping. promo is small on purpose: one Python file for the CLI, one
Lua file for the Neovim plugin, and a static site with two serverless functions.
You can read the part you need in an evening.

New here? Look for issues labelled
[`good first issue`](https://github.com/kimathikim/promo/labels/good%20first%20issue).
In October, PRs that get merged count for [Hacktoberfest](https://hacktoberfest.com).
Comment on an issue before you start so two people don't build the same thing.

## Set up

```sh
git clone https://github.com/kimathikim/promo && cd promo
uv tool install --editable .     # or: pipx install --editable .   or: pip install --user rich
promo --version
```

Keep your real history safe while you hack by pointing promo at a scratch
directory:

```sh
export XDG_DATA_HOME=/tmp/promo-dev/data XDG_CACHE_HOME=/tmp/promo-dev/cache XDG_CONFIG_HOME=/tmp/promo-dev/config
promo 1 "testing"                # a 1-minute session
```

The website: `node scripts/dev.js` serves `public/` and the API with
in-memory storage at http://localhost:3000. No `npm install` needed.

## Where things live

`promo.py` is split into sections with banner comments. Search for the banner
(`# Game:`, `# Squad:` and so on) rather than trusting line numbers.

| Section in `promo.py` | What it does |
|---|---|
| Clock rendering | the flip-clock digits (`FLIP_FONT`, `SMALL_FONT`, `FlipClock`) |
| Game | XP, levels, combos, achievements (`ACHIEVEMENTS`, `replay()`), `--spicy` lines |
| Git context | repo, branch and commits during a session (`Repo`) |
| Terminal input | raw keyboard input plus the remote-control FIFO (`Input`) |
| Storage | the session CSV (`Log`), streaks (`streaks()`), notes, state file |
| Sound | synthesised chimes (`SOUNDS`, `synth_wav`, `play_sound`) |
| UI | everything drawn on screen (`UI`) |
| App | the focus → rate → break loop, hooks, remote commands (`App`) |
| Squad | `promo serve`, the client, join/leave/forget, kudos (`SquadStore`, `SquadClient`) |
| promo stats / card / status | the subcommands of the same name |
| CLI | config file, flags and `main()` |

Elsewhere:

| Path | What it is |
|---|---|
| `lua/promo/init.lua` | Neovim plugin |
| `contrib/hooks/` | example hook scripts (Slack, GitHub status, DND) |
| `public/` | the leaderboard site (plain HTML, CSS and JS, no build step) |
| `api/squad.js` | the squad API on Vercel; same protocol and rules as `promo serve` |
| `api/contributors.js` | the "Built by" section |
| `scripts/dev.js` | local stand-in for Vercel |
| `scripts/demo.py` | renders `docs/demo.gif` from the real UI |

If you change the squad protocol or its rules, change both `api/squad.js` and
`SquadStore` in `promo.py`, so self-hosted and hosted squads behave the same.

## Before you open a PR

CI runs these; run them first:

```sh
python3 -m py_compile promo.py
promo --help >/dev/null && promo stats >/dev/null && promo status
for f in public/app.js api/*.js; do node --check "$f"; done
```

Then try your change for real: run a short session, open `promo stats`, or
load the site. For UI changes, include a screenshot or a short GIF.
If you change how the timer looks, regenerate the README's GIF with
`python3 scripts/demo.py` (needs `pip install playwright pillow`).

## Style

- Standard library plus `rich` only. A new dependency needs a very good reason.
- Python 3.7 compatible (no `match`, no walrus).
- Match the code around you: type hints on functions, short docstrings that say why.
- Privacy is a feature. Anything new that leaves the machine must be opt-in and
  listed in the README's "What leaves your machine" table and on `/privacy`.
- The game should reward sustainable focus. No mechanics that pay for
  14-hour days or punish rest.

## Easy ways to help

- **Achievements:** add a row to `ACHIEVEMENTS` and a check in `replay()`.
- **Spicy lines:** add to `SPICY_BREAKS` or the verdicts in `spicy_verdict()`. Keep them kind underneath.
- **Hooks:** a script in `contrib/hooks/` for a tool you use.
- **Packaging:** AUR, Nix, a Homebrew formula.
- **Docs:** anything that confused you is worth a PR.

## Releasing (maintainers)

Bump `__version__` in `promo.py`, merge, then push a tag `vX.Y.Z`. The Release
workflow checks the tag matches, publishes `promo-cli` to PyPI and creates a
GitHub release.
