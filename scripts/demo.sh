#!/usr/bin/env bash
# Walks through what the tool does, slowly enough to screen-record.
# The portal will not save the app without a demo video attached, so this
# exists to fill that field; it is not meant for an actual app review.
set -euo pipefail
cd "$(dirname "$0")/.."

step() { printf '\n\033[1;36m$ %s\033[0m\n' "$*"; sleep 2; }

step "python -m tiktok_poster status"
.venv/bin/python -m tiktok_poster status
sleep 4

step "python -m tiktok_poster post --dry-run --count 1"
.venv/bin/python -m tiktok_poster post --dry-run --count 1
sleep 4
