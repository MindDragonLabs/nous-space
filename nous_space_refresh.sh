#!/bin/bash
# Local data loop for the nous-space page — fetch + render ONLY.
#
# HARD RULES (InfraBoss directive 2026-09-27, Vercel cost incident):
#   1. This loop NEVER calls `vercel deploy` and NEVER calls `git push`.
#      The deploy step was physically removed from this script; do not
#      reintroduce it. Public Vercel releases are human-initiated only.
#   2. Re-render is throttled: a render runs only when the data hash
#      changed AND at least 20 minutes passed since the last render,
#      so the Mac does not churn CPU on every GitHub tick.
#
# Data:   fetch_state.py -> state.json   (live GitHub data + quality bridge)
# Render: build.py       -> index.html   (block row + panels)
# Serve:  ai.hermes.nous-space-dev — python http.server on 127.0.0.1:8791
#         serving this directory. Local-only, no network egress, no deploy.
#
# Invoked every 5 minutes by LaunchAgent com.hermes.nous-space-refresh.
# crontab cannot read the gh login keychain, so this is not scheduled there.
set -u
export HOME="${HOME:-/Users/jefferson}"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
ROOT="/Users/jefferson/nous-space"
LOG="$HOME/.hermes/logs/nous-space-refresh.log"
LOCK="$ROOT/.refresh.lock"
STAMP="$ROOT/.local-render-stamp"
HASHFILE="$ROOT/.local-render-hash"
KVSTAMP="$ROOT/.kv-push-stamp"
MIN_INTERVAL=1200   # seconds between allowed re-renders (20 min)

mkdir -p "$(dirname "$LOG")"
if [ -f "$LOG" ]; then
  bytes=$(wc -c < "$LOG" | tr -d ' ')
  if [ "$bytes" -gt 524288 ]; then
    tail -c 262144 "$LOG" > "$LOG.trim"
    mv "$LOG.trim" "$LOG"
  fi
fi

take_lock() {
  if mkdir "$LOCK" 2>/dev/null; then
    return 0
  fi
  oldpid=$(cat "$LOCK/pid" 2>/dev/null || true)
  oldstart=$(cat "$LOCK/start" 2>/dev/null || echo 0)

  now=$(date +%s)
  alive=0
  if [ -n "$oldpid" ] && kill -0 "$oldpid" 2>/dev/null; then
    alive=1
  fi
  age=$((now - oldstart))
  if [ "$alive" -eq 1 ] && [ "$age" -lt 900 ]; then
    echo "$(date -u +%FT%TZ) skip: refresh already running pid=$oldpid" >> "$LOG"
    return 1
  fi
  echo "$(date -u +%FT%TZ) taking stale lock pid=${oldpid:-none} age=${age}s" >> "$LOG"
  rm -rf "$LOCK"
  mkdir "$LOCK"
}
if ! take_lock; then
  exit 0
fi
echo $$ > "$LOCK/pid"
date +%s > "$LOCK/start"
cleanup() { rm -rf "$LOCK" 2>/dev/null || true; }
trap cleanup EXIT

# --- nous-index nightly rebuild (added 2026-09-28) ---
IDX_STAMP="$HOME/nous-space/.index-last-build"
if [ -f build_index.py ]; then
  now=$(date +%s); last=$(stat -f %m "$IDX_STAMP" 2>/dev/null || echo 0)
  if [ $((now - last)) -ge 86400 ]; then
    /opt/homebrew/bin/python3 build_index.py >> "$HOME/.hermes/logs/nous-space-refresh.log" 2>&1 \
      && touch "$IDX_STAMP" \
      && echo "$(date -u +%FT%TZ) nous-index rebuilt" >> "$HOME/.hermes/logs/nous-space-refresh.log"
  fi
fi


{
  echo "$(date -u +%FT%TZ) start (local-only)"

  # Fetch + render. refresh_data.py chains fetch_state.py then build.py.
  perl -e 'alarm shift; exec @ARGV' 300 /opt/homebrew/bin/python3 "$ROOT/refresh_data.py"
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "$(date -u +%FT%TZ) fetch/render failed exit=$status"
    exit "$status"
  fi

  # Hourly KV data push (API stays fresh without a site deploy).
  # Own stamp gate: 3600s. Data-only — never uploads the worker script.
  kv_now=$(date +%s)
  kv_last=$(cat "$KVSTAMP" 2>/dev/null || echo 0)
  if [ $((kv_now - kv_last)) -ge 3600 ]; then
    kv_status=0
    perl -e 'alarm shift; exec @ARGV' 180 /opt/homebrew/bin/python3 "$HOME/nous-api/push_kv.py" || kv_status=$?
    if [ "$kv_status" -eq 0 ]; then
      date +%s > "$KVSTAMP"
      echo "$(date -u +%FT%TZ) KV pushed (hourly)"
    else
      echo "$(date -u +%FT%TZ) KV push failed exit=$kv_status"
    fi
  fi

  now=$(date +%s)
  last=$(cat "$STAMP" 2>/dev/null || echo 0)
  if [ $((now - last)) -lt "$MIN_INTERVAL" ]; then
    echo "$(date -u +%FT%TZ) render throttled (min ${MIN_INTERVAL}s between renders)"
    exit 0
  fi

  hash=$(python3 - << 'PY'
import hashlib, pathlib, re
root = pathlib.Path("/Users/jefferson/nous-space")
def norm(path):
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return re.sub(r'"generated":"[^"]*"', '"generated":""', text)
digest = hashlib.sha256()
digest.update(norm(root / "state.json").encode())
digest.update(norm(root / "news.json").encode())
print(digest.hexdigest())
PY
)
  prev=$(cat "$HASHFILE" 2>/dev/null || echo none)
  if [ "$hash" = "$prev" ]; then
    echo "$(date -u +%FT%TZ) data unchanged, no action"
    exit 0
  fi

  printf '%s\n' "$hash" > "$HASHFILE"
  date +%s > "$STAMP"
  echo "$(date -u +%FT%TZ) rendered locally — served at 127.0.0.1:8791 (NOT deployed)"
} >> "$LOG" 2>&1
