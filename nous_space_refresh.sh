#!/bin/bash
# Refresh the local page, then publish it to https://nous.minddragonlabs.com.
# Fetch + render only; no model calls.
# Invoked every 5 minutes by the LaunchAgent com.hermes.nous-space-refresh.
# crontab cannot read the gh login keychain, so this script is not scheduled there.
set -u
export HOME="${HOME:-/Users/jefferson}"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
ROOT="/Users/jefferson/nous-space"
LOG="$HOME/.hermes/logs/nous-space-refresh.log"
LOCK="$ROOT/.refresh.lock"
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

{
  echo "$(date -u +%FT%TZ) start"
  perl -e 'alarm shift; exec @ARGV' 300 /opt/homebrew/bin/python3 "$ROOT/refresh_data.py"
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "$(date -u +%FT%TZ) failed exit=$status"
    exit "$status"
  fi
  echo "$(date -u +%FT%TZ) rendered"
  cd "$ROOT"
  hash=$(python3 - << 'PY'
import hashlib, pathlib, re
root = pathlib.Path("/Users/jefferson/nous-space")
def norm(path):
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return re.sub(r'"generated":"[^"]*"', '"generated":""', text)
digest = hashlib.sha256()
digest.update(norm(root / "index.html").encode())
digest.update(norm(root / "news.json").encode())
print(digest.hexdigest())
PY
)
  stamp="$ROOT/.deploy-hash"
  if [ -f "$stamp" ] && [ "$(cat "$stamp")" = "$hash" ]; then
    echo "$(date -u +%FT%TZ) unchanged, skip deploy"
    exit 0
  fi
  perl -e 'alarm shift; exec @ARGV' 180 /opt/homebrew/bin/vercel deploy --prod --yes
  status=$?
  if [ "$status" -ne 0 ]; then
    echo "$(date -u +%FT%TZ) deploy failed exit=$status"
    exit "$status"
  fi
  printf '%s\n' "$hash" > "$stamp"
  echo "$(date -u +%FT%TZ) deployed https://nous.minddragonlabs.com"
} >> "$LOG" 2>&1
