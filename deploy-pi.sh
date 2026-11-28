#!/usr/bin/env bash
# Copies the app to the Pi and (re)starts its weekend-planner service. Data in ~/weekend-planner/data is kept.
set -euo pipefail
HOST="${1:-pi4}"  # an ssh host alias; set it up in ~/.ssh/config
cd "$(dirname "$0")"
tar czf - server.py docs weekend-planner.service | ssh "$HOST" '
  set -e
  mkdir -p ~/weekend-planner/data && cd ~/weekend-planner
  rm -rf docs && tar xzf -
  sudo install -m 644 weekend-planner.service /etc/systemd/system/weekend-planner.service
  sudo systemctl daemon-reload
  sudo systemctl enable weekend-planner >/dev/null 2>&1
  sudo systemctl restart weekend-planner
'
