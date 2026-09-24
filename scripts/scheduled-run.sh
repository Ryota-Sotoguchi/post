#!/usr/bin/env bash
# What Task Scheduler runs, at 08:00/12:00/16:00/20:00 and at logon.
#
# Every step is idempotent, so running this when nothing is due costs a few
# seconds. That is what makes the logon trigger safe: after the PC has been
# off, whatever was missed gets done, and on an ordinary boot nothing happens.
#
#   pull      pick up the send state and approval marker Actions committed
#   generate  any slots from yesterday and today that did not run
#   store     convert to JPEG, publish to Pages, commit the generator state
#   cleanup   drop local images for themes fully sent long ago
#   post      if today's drafts are short, start the Actions posting run
#
# Steps do not stop at the first failure. A failed generation should not also
# stop the day's posting when there are two weeks of carousels in stock. Any
# failure still sets the exit code, so Task Scheduler records it.

set -u
cd "$(dirname "$0")/.."
PY=.venv-linux/bin/python
status=0

step() {
    local name=$1
    shift
    echo "[$(date '+%F %T')] ${name}"
    "$@"
    local code=$?
    if [ "$code" -ne 0 ]; then
        echo "[$(date '+%F %T')] ${name} FAILED (exit ${code})"
        status=1
    fi
}

# The approval marker is published by whoever approved last - the phone through
# the authorize workflow, or this PC through `daily`. A local copy left over
# from an approval that was already pushed is not worth a merge conflict that
# stops the pull, and with it the day's syncing and posting.
git checkout -- docs/authorized.json 2>/dev/null || true

step pull     git pull --rebase --autostash origin main
step generate "$PY" -m mbti_tiktok_bot run-daemon --run-once --no-reconcile
step store    "$PY" -m tiktok_poster sync
step cleanup  "$PY" -m tiktok_poster cleanup
step post     "$PY" -m tiktok_poster catch-up

echo "[$(date '+%F %T')] done (exit ${status})"
exit "$status"
