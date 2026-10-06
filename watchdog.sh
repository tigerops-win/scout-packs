#!/usr/bin/env bash
# Health monitor for the Scout Packs production endpoint (Railway).
# Runs via cron (check `crontab -l` for cadence). Append-only logging to watchdog.log.
# 2026-10-02 CUTOVER: production moved to https://scout-packs-production.up.railway.app.
# The loca.lt tunnel path (lt-proxy.js, pinned subdomains) is DEAD LEGACY — this
# script no longer restarts tunnels or a local server. Railway restarts are not
# possible from this sandbox; a failed check logs an ALERT for a human to act on.
# The receiving address below is PUBLIC (it appears on our listings) - safe to keep here.
set -uo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$DIR/watchdog.log"
PUBLIC_BASE="https://scout-packs-production.up.railway.app"

log() { echo "$(date -u +%FT%TZ) $*" >> "$LOG"; }

HEALTH="$(curl -s -m 20 "$PUBLIC_BASE/health" 2>/dev/null || true)"
if echo "$HEALTH" | grep -q '"ok": true'; then
  if echo "$HEALTH" | grep -q '"sales_enabled": true'; then
    log "ok: railway healthy, sales_enabled=true"
  else
    log "ALERT: railway up but sales NOT enabled - human check needed"
  fi
else
  log "ALERT: railway endpoint down or unreachable ($PUBLIC_BASE) - human check needed"
fi
