#!/bin/sh
# Turn a macOS Focus mode on and off with promo.
#
#   hook = ~/promo/contrib/hooks/macos-focus.sh
#
# One-time setup in the Shortcuts app: create two shortcuts named
# "promo focus on" (Set Focus: Do Not Disturb, On) and
# "promo focus off" (Set Focus: Do Not Disturb, Off).
command -v shortcuts >/dev/null 2>&1 || exit 0
case "$PROMO_EVENT:$PROMO_PHASE" in
  focus_start:*|resume:focus) shortcuts run "promo focus on" ;;
  *) shortcuts run "promo focus off" ;;
esac
