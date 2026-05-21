#!/usr/bin/env bash
# Run the surf checker locally. Loads .env if present.
#
# Usage:
#   ./run_local.sh              # one run
#   ./run_local.sh --loop       # run every 15 minutes
#   ./run_local.sh --dry-run    # don't send notifications
#   ./run_local.sh --test-alert # force-send a test notification, ignoring rules
set -euo pipefail

cd "$(dirname "$0")"

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a; source .env; set +a
fi

LOOP=0
TEST_ALERT=0
for arg in "$@"; do
  case "$arg" in
    --loop) LOOP=1 ;;
    --dry-run) export DRY_RUN=1 ;;
    --test-alert) TEST_ALERT=1 ;;
    *) echo "unknown arg: $arg" >&2; exit 2 ;;
  esac
done

if [[ "$TEST_ALERT" == 1 ]]; then
  python3 - <<'PY'
import os, sys
sys.path.insert(0, "scripts")
from notify import notify_all
r = notify_all(
    subject="🌊 Test alert — Rory Surf Alerts is wired up",
    body="If you got this, your local setup works. Surf-up alerts will arrive the same way.",
    push_title="🌊 Test alert",
)
print(f"email_sent={r.email_sent} email_error={r.email_error}")
print(f"push_sent={r.push_sent}  push_error={r.push_error}")
PY
  exit 0
fi

run_once() {
  echo "=== $(date -u +%FT%TZ) ==="
  python3 scripts/check_surf.py || echo "(check_surf exited non-zero)"
}

if [[ "$LOOP" == 1 ]]; then
  while true; do
    run_once
    echo "sleeping 15 min…"
    sleep 900
  done
else
  run_once
fi
