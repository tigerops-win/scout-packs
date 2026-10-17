#!/bin/sh
# Nightly telemetry ledger mirror — Tiger Operations (telemetry/SPEC.md).
#
# Cron-ready (America/New_York), e.g.:
#   15 3 * * *  /home/hatch/workspace/scout-packs/telemetry/run-nightly.sh
#
# The ops token is read by mirror.py from SCOUTPACKS_OPS_TOKEN or, as here,
# from the 600-perm file ~/.config/scout-packs/ops-token (never commit it).
# Exit code is mirror.py's: 0 ok · 2 no token · 3 HTTP/auth · 4 bad payload.
# A non-zero exit must be surfaced (hook/cron mail); a failed night loses
# nothing — the next successful run backfills via full-snapshot + dedup.
set -u
cd "$(dirname "$0")/.." || exit 2
mkdir -p telemetry/store
{
    echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) nightly mirror run ==="
    python3 telemetry/mirror.py
    echo "exit=$?"
    python3 telemetry/mirror.py summary
} >> telemetry/store/nightly.log 2>&1
# Preserve the mirror's exit status for the scheduler: re-run bookkeeping is
# in telemetry/store/runs.jsonl; the log tail carries the human-readable copy.
tail -n 1 telemetry/store/runs.jsonl | grep -q '"ok": true'
