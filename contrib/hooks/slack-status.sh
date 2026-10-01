#!/bin/sh
# Set your Slack status and snooze notifications while you focus.
#
#   hook = ~/promo/contrib/hooks/slack-status.sh        (in ~/.config/promo/config.ini)
#
# Needs a Slack user token (xoxp-...) with the users.profile:write and
# dnd:write scopes, in SLACK_TOKEN. Create one at https://api.slack.com/apps.
[ -n "$SLACK_TOKEN" ] || exit 0

slack() {
  curl -fsS -X POST "https://slack.com/api/$1" \
    -H "Authorization: Bearer $SLACK_TOKEN" \
    -H "Content-Type: application/json; charset=utf-8" \
    -d "$2" >/dev/null
}

case "$PROMO_EVENT:$PROMO_PHASE" in
  focus_start:*|resume:focus)
    mins=${PROMO_MINUTES%.*}
    until=$(( $(date +%s) + ${mins:-25} * 60 ))
    slack users.profile.set "{\"profile\":{\"status_text\":\"Focusing, back in ${mins:-25}m\",\"status_emoji\":\":tomato:\",\"status_expiration\":$until}}"
    slack dnd.setSnooze "{\"num_minutes\":${mins:-25}}"
    ;;
  *)
    slack users.profile.set '{"profile":{"status_text":"","status_emoji":""}}'
    slack dnd.endSnooze '{}'
    ;;
esac
