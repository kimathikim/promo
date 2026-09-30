#!/bin/sh
# promo installer: curl -fsSL https://<this site>/install.sh | sh
#
# Installs the promo CLI into ~/.local/bin (override with PROMO_BIN=/path).
# Needs Python 3.7+. Installs the `rich` library if it isn't there yet.
set -eu

SRC="https://raw.githubusercontent.com/kimathikim/promo/main/promo.py"
BIN="${PROMO_BIN:-$HOME/.local/bin}"

say() { printf '%s\n' "$*"; }
fail() { printf 'promo install: %s\n' "$*" >&2; exit 1; }

# 1. Python 3.7+
command -v python3 >/dev/null 2>&1 || fail "python3 not found. Install Python 3.7 or newer first."
python3 -c 'import sys; sys.exit(sys.version_info < (3, 7))' \
  || fail "Python 3.7+ is required (found $(python3 -V 2>&1))."

# 2. rich (skip if already importable)
if python3 -c 'import rich' >/dev/null 2>&1; then
  say "✓ rich already installed"
elif python3 -m pip install --user --quiet rich >/dev/null 2>&1; then
  say "✓ installed rich"
else
  say "! couldn't install rich with pip (your system Python may be externally managed)."
  say "  Install it one of these ways, then run promo:"
  say "    sudo apt install python3-rich      # Debian / Ubuntu"
  say "    brew install python-rich           # macOS (Homebrew)"
  say "    pipx install rich                  # or any virtualenv"
fi

# 3. download promo
mkdir -p "$BIN"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
if command -v curl >/dev/null 2>&1; then
  curl -fsSL "$SRC" -o "$TMP" || fail "download failed: $SRC"
elif command -v wget >/dev/null 2>&1; then
  wget -qO "$TMP" "$SRC" || fail "download failed: $SRC"
else
  fail "need curl or wget to download promo."
fi
head -n 1 "$TMP" | grep -q python3 || fail "downloaded file doesn't look like promo; aborting."
mv "$TMP" "$BIN/promo"
chmod 755 "$BIN/promo"
trap - EXIT
say "✓ installed promo to $BIN/promo"

# 4. PATH
case ":$PATH:" in
  *":$BIN:"*)
    say ""
    say "Done. Try:  promo 25 \"ship the thing\""
    ;;
  *)
    case "${SHELL:-}" in
      */zsh) RC="$HOME/.zshrc" ;;
      */fish) RC="$HOME/.config/fish/config.fish" ;;
      *) RC="$HOME/.bashrc" ;;
    esac
    say ""
    say "$BIN is not on your PATH yet. Add it with:"
    if [ "${RC##*/}" = "config.fish" ]; then
      say "  echo 'fish_add_path $BIN' >> $RC"
    else
      say "  echo 'export PATH=\"$BIN:\$PATH\"' >> $RC"
    fi
    say "then open a new terminal and run:  promo 25 \"ship the thing\""
    ;;
esac
