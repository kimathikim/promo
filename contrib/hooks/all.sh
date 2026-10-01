#!/bin/sh
# Run several hooks at once. promo takes one `hook =` command, so point it here
# and list the scripts you want below.
#
#   hook = ~/promo/contrib/hooks/all.sh
dir=$(dirname "$0")
for h in linux-dnd.sh github-status.sh; do   # edit this list
  [ -x "$dir/$h" ] && "$dir/$h" &
done
wait
