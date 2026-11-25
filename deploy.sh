#!/usr/bin/env bash
# Copies the app to Beulah and (re)starts the weekend-planner container. Data in ~/weekend-planner/data is kept.
set -euo pipefail
HOST="${1:-beulah}"
cd "$(dirname "$0")"
tar czf - server.py Dockerfile docs | ssh "$HOST" '
  set -e
  mkdir -p ~/weekend-planner/data && cd ~/weekend-planner
  rm -rf docs && tar xzf -
  docker build -q -t weekend-planner .
  docker rm -f weekend-planner >/dev/null 2>&1 || true
  docker run -d --name weekend-planner --restart unless-stopped -p 8090:8090 \
    --user "$(id -u):$(id -g)" -v ~/weekend-planner/data:/data weekend-planner
'
