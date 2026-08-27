#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Redis self-heal wrapper (run by supervisor, see /etc/supervisor/conf.d/redis.conf)
#
# A container rebuild can wipe the apt-installed redis-server binary from
# /usr/bin while leaving the supervisor config in place. When that happens the
# 'redis' program crash-loops ("can't find command '/usr/bin/redis-server'"),
# the backend gets unstable during cold start, and the frontend shows the
# "Engine error" (HTML returned where JSON was expected).
#
# This wrapper makes redis self-healing: on every start it checks for the
# binary and re-installs it if missing, then execs redis-server. Normal starts
# (binary already present) are instant — the install path only runs after a
# rebuild wiped it.
# ---------------------------------------------------------------------------
set -u

log() { echo "[redis-healer] $*" >&2; }

ensure_redis() {
  local bin
  bin="$(command -v redis-server 2>/dev/null || true)"
  if [ -n "$bin" ] && [ -x "$bin" ]; then
    echo "$bin"
    return 0
  fi

  log "redis-server not found — attempting install (container rebuild likely wiped it)..."
  export DEBIAN_FRONTEND=noninteractive
  # A few retries in case apt mirrors are briefly unavailable at cold start.
  for attempt in 1 2 3; do
    apt-get update -y >/dev/null 2>&1 || true
    if apt-get install -y --no-install-recommends redis-server >/dev/null 2>&1; then
      log "install succeeded on attempt ${attempt}."
      break
    fi
    log "install attempt ${attempt} failed — retrying in 5s..."
    sleep 5
  done

  # Never let systemd's redis unit fight our supervisor-managed instance for :6379.
  systemctl disable redis-server >/dev/null 2>&1 || true
  systemctl stop redis-server >/dev/null 2>&1 || true

  bin="$(command -v redis-server 2>/dev/null || echo /usr/bin/redis-server)"
  echo "$bin"
}

REDIS_BIN="$(ensure_redis)"

if [ ! -x "$REDIS_BIN" ]; then
  log "ERROR: redis-server still unavailable at '$REDIS_BIN' after install attempts."
  log "The backend degrades gracefully without Redis, but real-time order-flow will be limited."
  # Exit non-zero so supervisor retries (which re-runs this healer -> another install try).
  exit 1
fi

log "starting redis-server at ${REDIS_BIN}"
# 'exec' so supervisor tracks the redis-server process directly (correct signals/status).
exec "$REDIS_BIN" --port 6379 --bind 127.0.0.1 --save "" --appendonly no --maxmemory 256mb --maxmemory-policy allkeys-lru
