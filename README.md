# PROmodoro — a progressive Pomodoro timer for developers

![PROmodoro focus screen](docs/focus.png)

PROmodoro is a distraction-free terminal timer built around the Pomodoro Technique, with one twist: session length isn't fixed. After every session you rate how focused you were and the next one grows or shrinks, so short attention spans can build up into long flow states.

It's made for people who live in the terminal: it knows which git repo and branch you're in, counts the commits you make while focused, lets you jot down a stray thought without leaving the timer, and plugs into tmux, waybar and your own scripts.

***For better grasp of the idea***

[00:00](https://www.youtube.com/watch?v=qtoysJSQTn8&t)

## Features

**A clean, flip-clock style screen**
- Big flip-card digits that animate as they change, a slim progress bar, and nothing else on screen until you ask for it.
- Press `i` for details: today's total against your daily goal, this run's sessions, time left until the long break, and git activity.
- The countdown also appears in your terminal tab title.

**Progressive sessions**
- After each focus session you rate your focus, and the next session is resized (see [Workflow](#workflow)).
- Breaks are one fifth of the time you *actually* focused. A 30-minute long break comes after 3 hours of focus.

**Built for developers**
- **Git context**: shows the repo and branch you're working in and logs them with every session.
- **Commit capture**: counts the commits and lines changed during each focus session (only your own, matched by `git config user.email`).
- **Quick notes**: press `n`, type a thought ("check null user in middleware"), press `enter`, and you're back to work. Notes go to a Markdown checklist with the time, repo and task.
- **`promo stats`**: a GitHub-style focus heatmap, streaks, week-over-week trend, a focus-level breakdown, your peak hour of the day, and time per project.
- **`promo status`**: a one-line status for tmux, waybar, polybar or your shell prompt.
- **Hooks**: run your own command when a session starts or ends, e.g. to turn on Do Not Disturb or set your Slack status.
- Desktop notifications (`notify-send` on Linux, `osascript` on macOS) plus the terminal bell.

![Details view](docs/details.png)

## Usage

```sh
promo [hours] [minutes] [task]
```

```sh
promo                         # 5-minute warm-up session
promo 25                      # one number = minutes
promo 1 30                    # 1h30
promo 25 fix login bug        # with a task label
promo -t "review PR #42" 45
```

| Key | Action |
|---|---|
| `space` / `p` | pause / resume |
| `s` | skip the current phase |
| `+` / `-` | add / remove a minute |
| `n` | capture a note (`enter` saves, `esc` cancels) |
| `i` | show / hide details |
| `q` / `Ctrl-C` | quit and show the summary |

### Stats

```sh
promo stats            # last 26 weeks
promo stats --weeks 52
```

![promo stats](docs/stats.png)

### Status bar integration

`promo status` prints the running timer (for example `🍅 18:33`), and nothing when no timer is running.

```sh
# tmux (~/.tmux.conf)
set -g status-right '#(promo status) %H:%M'
set -g status-interval 1

# waybar module
"custom/promo": { "exec": "promo status --json", "return-type": "json", "interval": 1 }

# custom format; placeholders: {icon} {time} {phase} {task} {project} {branch} {session}
promo status --format "{icon} {time} {task}"
```

### Hooks

`--hook CMD` (or `hook =` in the config file) runs a shell command on each of these events: `focus_start`, `focus_end`, `break_start`, `break_end`, `pause`, `resume` and `quit`. It gets the environment variables `PROMO_EVENT`, `PROMO_PHASE`, `PROMO_MINUTES`, `PROMO_TASK`, `PROMO_PROJECT` and `PROMO_BRANCH`.

```sh
#!/bin/sh
# ~/bin/promo-dnd: silence notifications while focusing (dunst)
case "$PROMO_EVENT" in
  focus_start|resume) dunstctl set-paused true ;;
  *)                  dunstctl set-paused false ;;
esac
```

### Config file

Defaults can be set in `~/.config/promo/config.ini`; command-line flags override them.

```ini
[promo]
minutes = 25              ; first session length
goal = 240                ; daily focus goal in minutes (0 = off)
long_break_after = 180
hook = ~/bin/promo-dnd
bell = true
git = true
title = true
status_format = {icon} {time}
```

## Workflow

1. A focus session starts with the length you gave.
2. When it ends (or you skip it), rate your focus:

   ![Rating screen](docs/rating.png)

   | Key | Level      | Next focus session  |
   |-----|------------|---------------------|
   | 1   | Break      | long break (30 min) |
   | 2   | Distracted | −5 minutes          |
   | 3   | Normal     | +5 minutes (`enter`)|
   | 4   | Focused    | +10 minutes         |
   | 5   | Flow       | +20 minutes         |

   Sessions stay between 5 minutes and 3 hours.
3. A short break of one fifth of the focused time follows, or a long break when one is due.
4. The cycle repeats until you press `q` or `Ctrl-C`. A phase you stop partway through is still logged if it ran for at least 30 seconds.

## Data

| File | Contents |
|---|---|
| `~/.local/share/promo/sessions.csv` | one row per phase: `date, start, end, phase, planned_min, actual_min, focus_level, task, project, branch, commits` |
| `~/.local/share/promo/notes.md` | notes captured with `n` |
| `~/.cache/promo/state.json` | the running timer, read by `promo status` |

`XDG_DATA_HOME`, `XDG_CACHE_HOME` and `XDG_CONFIG_HOME` are respected. Use `--log` / `--notes` to use other paths.

## Installation

Requires Python 3.7+ and [`rich`](https://github.com/Textualize/rich). Keyboard controls need a Unix-like terminal (Linux or macOS). A terminal with true colour and a font that has block characters looks best.

```sh
git clone https://github.com/kimathikim/promo.git ~/promo
cd ~/promo
pip install -r requirements.txt
sudo cp promo.py /usr/local/bin/promo
sudo chmod +x /usr/local/bin/promo
```

## Contributing

Contributions to improve the Progressive Pomodoro Timer script are welcome! If you find any issues or have suggestions for enhancements, please create a new issue or submit a pull request on the repository.
