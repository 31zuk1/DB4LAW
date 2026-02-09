#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

CURRENT_SHELL_PID="$$"
RUNNING_PIDS="$(pgrep -f "$ROOT_DIR/node_modules/.bin/next dev" || true)"

for pid in $RUNNING_PIDS; do
  if [[ "$pid" != "$CURRENT_SHELL_PID" ]]; then
    echo "Stopping existing apps/ui dev server (pid: $pid)..." >&2
    kill "$pid" || true
    for _ in {1..20}; do
      if ! kill -0 "$pid" 2>/dev/null; then
        break
      fi
      sleep 0.1
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" || true
    fi
  fi
done

rm -rf .next
exec next dev "$@"
