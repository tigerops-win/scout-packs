# TASKS — Telemetry Ledger Mirror

Builder checklist. SPEC.md and ACCEPTANCE.md were written first (2026-10-16).

- [x] Audit `server.py`: existing read surfaces (`/health`, discovery only),
      auth patterns (none), ledger state files (`data/<kind>_sales.jsonl`
      via `log_sale()`, `data/x402_settled.json`, `data/redeemed.json`),
      secret conventions (env config; 600-perm token file precedent).
- [x] Write SPEC.md (audit findings, endpoint + mirror design, store format).
- [x] Write ACCEPTANCE.md with hand-written fixture expectations BEFORE building.
- [x] Branch `feature/telemetry-ledger-mirror` created locally from `main`.
- [x] `server.py`: `SCOUTPACKS_OPS_TOKEN` config + `read_ledger_snapshot()`
      helper + `GET /ops/ledger` route + `Handler.ops_ledger()` (Bearer,
      `hmac.compare_digest`, disabled→404 when token unset, `?since=` filter).
- [x] `telemetry/mirror.py`: fetch (Bearer) → validate → dedup-merge into
      `telemetry/store/` (append-only `sales.jsonl` w/ sha256 `_sale_id`,
      union `settled.json`/`redeemed.json`, atomic `state.json`, `runs.jsonl`),
      fail-closed exit codes 0/2/3/4, `summary` subcommand.
- [x] `telemetry/run-nightly.sh`: cron-ready wrapper; `.gitignore` gains
      `telemetry/store/`.
- [x] `tests/test_telemetry_mirror.py`: every ACCEPTANCE.md criterion.
- [x] Run tests: telemetry 10/10 OK; dossier regression suite 13/13 OK;
      CLI smoke (no-token → exit 2, empty-store summary honest).
- [x] HANDOFF.md: test evidence, exact deploy steps for Tiger, rollback.
- [x] Coordinator brief at
      `~/workspace/ai-crew/briefs/telemetry-mirror-build-2026-10-16.md`.
- [x] Commit LOCALLY on `feature/telemetry-ledger-mirror` only.
- [x] STOP: no push, no deploy, no sends, no spend, no publishing, no ProtonMail.
