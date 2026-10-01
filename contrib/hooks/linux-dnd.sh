#!/bin/sh
# Silence desktop notifications while you focus (GNOME, dunst or mako).
#
#   hook = ~/promo/contrib/hooks/linux-dnd.sh
case "$PROMO_EVENT:$PROMO_PHASE" in
  focus_start:*|resume:focus) on=true ;;
  *) on=false ;;
esac

if command -v gsettings >/dev/null 2>&1 && [ "$XDG_CURRENT_DESKTOP" != "${XDG_CURRENT_DESKTOP#*GNOME}" ]; then
  # GNOME: show-banners=false is "Do Not Disturb"
  [ "$on" = true ] && banners=false || banners=true
  gsettings set org.gnome.desktop.notifications show-banners "$banners"
elif command -v dunstctl >/dev/null 2>&1; then
  dunstctl set-paused "$on"
elif command -v makoctl >/dev/null 2>&1; then
  if [ "$on" = true ]; then makoctl mode -a do-not-disturb; else makoctl mode -r do-not-disturb; fi
fi
