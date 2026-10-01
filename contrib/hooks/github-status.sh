#!/bin/sh
# Show a 🍅 "Focusing" status on your GitHub profile while you focus.
#
#   hook = ~/promo/contrib/hooks/github-status.sh
#
# Needs the GitHub CLI (`gh auth login`, with the `user` scope:
# `gh auth refresh -s user`).
command -v gh >/dev/null 2>&1 || exit 0

set_status() {
  gh api graphql -f query='
    mutation($msg: String!, $emoji: String!, $busy: Boolean!) {
      changeUserStatus(input: {message: $msg, emoji: $emoji, limitedAvailability: $busy}) { clientMutationId }
    }' -f msg="$1" -f emoji="$2" -F busy="$3" >/dev/null 2>&1
}

case "$PROMO_EVENT:$PROMO_PHASE" in
  focus_start:*|resume:focus) set_status "Focusing${PROMO_PROJECT:+ on $PROMO_PROJECT}" ":tomato:" true ;;
  *) set_status "" "" false ;;
esac
