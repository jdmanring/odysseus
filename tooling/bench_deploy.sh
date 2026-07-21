#!/usr/bin/env bash
# Deploy a wrapper file to the macOS bench, restart the app, and tail the
# lifecycle log — the loop otherwise run by hand as scp + ssh pkill/open + grep.
#
#   tooling/bench_deploy.sh                       # deploy mac_wrapper.py to `macos`, restart, tail
#   tooling/bench_deploy.sh -f qt_wrapper.py      # a different file
#   tooling/bench_deploy.sh -H macos -n           # deploy only, no restart
#   tooling/bench_deploy.sh -g '\[LIFECYCLE\]' -t 30
#
# Assumes an SSH host alias (default `macos`) with the checkout at ~/odysseus and
# the app installed at /Applications/Odysseus.app. macOS bench only: it uses
# `open` and the server's :7000 readiness check.
set -euo pipefail

HOST=macos
FILE=mac_wrapper.py
REMOTE_DIR=odysseus
APP=/Applications/Odysseus.app
RESTART=1
TAIL=16
GREP='\[LIFECYCLE\]'
LOG='~/odysseus/logs/wrapper_system.log'

usage() { sed -n '2,15p' "$0"; exit "${1:-0}"; }

while [ $# -gt 0 ]; do
  case "$1" in
    -H|--host)   HOST=$2; shift 2 ;;
    -f|--file)   FILE=$2; shift 2 ;;
    -n|--no-restart) RESTART=0; shift ;;
    -t|--tail)   TAIL=$2; shift 2 ;;
    -g|--grep)   GREP=$2; shift 2 ;;
    -h|--help)   usage 0 ;;
    *) echo "unknown arg: $1" >&2; usage 1 ;;
  esac
done

[ -f "$FILE" ] || { echo "no such file: $FILE" >&2; exit 1; }

echo ">> deploying $FILE -> $HOST:$REMOTE_DIR/"
scp -q "$FILE" "$HOST:$REMOTE_DIR/$(basename "$FILE")"

if [ "$RESTART" = 1 ]; then
  echo ">> restarting app on $HOST"
  # shellcheck disable=SC2029  # expansion is intentional (built here, run there)
  ssh "$HOST" "
    pkill -f '$(basename "$FILE")' 2>/dev/null || true
    sleep 3
    open '$APP'
    for i in \$(seq 1 12); do
      sleep 2
      curl -s -o /dev/null -w '%{http_code}' http://localhost:7000/ 2>/dev/null \
        | grep -qE '200|30' && break
    done
    sleep 2
    echo \"   pid=\$(pgrep -f '$(basename "$FILE")')\"
  "
fi

echo ">> tail ($TAIL lines matching /$GREP/):"
ssh "$HOST" "grep -E '$GREP' $LOG 2>/dev/null | tail -$TAIL || echo '   (no matching log lines yet)'"
