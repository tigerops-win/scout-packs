# HANDOFF — Telemetry Ledger Mirror

Builder: Tiger subagent (workstream G1), 2026-10-16. Status: **built and
tested locally only. Committed on local branch
`feature/telemetry-ledger-mirror`. NOT pushed, NOT deployed.** Production
(Railway) untouched. Nothing sent, nothing spent, nothing published.

## Branch / commit state

- Local branch: `feature/telemetry-ledger-mirror` (from `main` @ `4e240e1`).
- One local commit containing ONLY this feature's files (pre-existing dirt —
  `M mcp-registry/server.json` and the untracked files that were already in
  the tree — left untouched and uncommitted).
- Files:
  - `server.py` (+~110 lines): `SCOUTPACKS_OPS_TOKEN` config, `import hmac`,
    `read_ledger_snapshot()` helper, `GET /ops/ledger` route +
    `Handler.ops_ledger()`.
  - `telemetry/` (new): `SPEC.md`, `ACCEPTANCE.md`, `TASKS.md`, this
    `HANDOFF.md`, `mirror.py`, `run-nightly.sh`.
  - `tests/test_telemetry_mirror.py` (new).
  - `.gitignore`: `telemetry/store/` added (runtime state, like `data/`).

## What was built

**Server — `GET /ops/ledger`** (the server previously exposed NO read path
for ledger state and had NO auth pattern anywhere; audit in SPEC.md):

- Disabled (404 `{"error":"not_found"}`) unless env `SCOUTPACKS_OPS_TOKEN`
  is set; then requires `Authorization: Bearer <token>` compared with
  `hmac.compare_digest`, else 401 `{"error":"unauthorized"}`. Auth reuses
  the codebase's only secret conventions: env config +
  raw-token-in-600-perm-file client-side.
- 200 body: `{generated_at, sales: {kind: [records verbatim]},
  settled: {...}, redeemed: [...], counts: {...}}`, built by scanning
  `data/*_sales.jsonl`; unparseable lines carried as
  `{"_raw":..., "_parse_error":true}` and counted. Optional `?since=<ISO ts>`
  filters sales records (records without a parseable ts are always kept).
  Read-only; not enumerated in `/catalog`, `/.well-known/x402`, openapi, or
  LLMS_TXT; not a CORS path.

**Client — `telemetry/mirror.py`** (stdlib only): one run fetches the full
snapshot and dedup-merges it into `telemetry/store/`:

- `sales.jsonl` — append-only; each line = server record verbatim +
  `_kind` + `_sale_id` (`sha256(kind|canonical_json(record))`). Re-runs
  against an unchanged server append ZERO lines (byte-identical file —
  test-proven).
- `settled.json` (union, server wins conflicts, conflicts counted),
  `redeemed.json` (sorted union), `state.json` (atomic), `runs.jsonl`
  (every attempt logged, success or failure).
- Fail closed: exit 2 = no token configured, 3 = HTTP/auth failure,
  4 = malformed payload; on failure the data files are untouched.
- `mirror.py summary` — per-kind counts + `amount_usd` totals, distinct
  senders, settled/redeemed totals, last success time — all from the local
  store only; settled and sales figures are reported as separate lines
  (they count different things; no reconciliation is invented).

## Test evidence

Commands (repo root), 2026-10-16:

```
python3 -m unittest tests.test_telemetry_mirror -v   → Ran 10 tests, OK (2.8 s)
python3 -m unittest tests.test_dossier               → Ran 13 tests, OK (111 s)  [regression]
SCOUTPACKS_MIRROR_DIR=/tmp/sp-smoke-store python3 telemetry/mirror.py
                                                     → {"error": "no_ops_token_configured"}, exit 2
```

Telemetry coverage, mapped to ACCEPTANCE.md: endpoint full-snapshot exact
equality (incl. counts), 401 no/wrong token, 404 when disabled, `since`
filter, unparseable-line fidelity, no regressions (`/health`, 404 shape,
`/ops/ledger` absent from `/catalog`); mirror run 1 appends 3, run 2
appends 0 with byte-identical `sales.jsonl`, run 3 appends exactly 1 with
the prior prefix intact, wrong token → exit 3 + store untouched, malformed
payload → exit 4 + store untouched, no token → exit 2 + bookkeeping only;
summary figures (4 sales, $0.08 attributed, 2 senders, settled 2, redeemed 2).

One implementation fix during the run: a 200-with-garbage payload was first
classified exit 3 (fetch failure); `run_mirror()` now catches `ValueError`
from payload validation separately → exit 4, as ACCEPTANCE.md specifies.
No fixture or expectation was changed to fit the code.

Not tested locally (cannot be): a real mirror run against production
(endpoint not deployed — by design) and any real paid settlement —
[UNKNOWN] until Tiger deploys + a test purchase is made.

## Deploy — exact steps for Tiger (DO NOT run as part of this build)

1. Review: `git diff main...feature/telemetry-ledger-mirror` and read
   `telemetry/` + `tests/`.
2. Re-run on the deploying machine: `python3 -m unittest
   tests.test_telemetry_mirror` — expect 10 tests, OK.
3. Generate the ops token and store it client-side ONLY:
   `openssl rand -hex 32 > ~/.config/scout-packs/ops-token && chmod 600
   ~/.config/scout-packs/ops-token`
4. Set the SAME value as env `SCOUTPACKS_OPS_TOKEN` on the Railway
   production service (dashboard or `railway variables set`).
5. Merge `feature/telemetry-ledger-mirror` to `main`, push, and deploy to
   Railway the usual Scout Packs way (see `REDEPLOY-CHECKLIST.md` —
   [CHECK] confirm it is still current). The ONLY new env var is
   `SCOUTPACKS_OPS_TOKEN` (step 4); no other config changes.
6. Post-deploy smoke (read-only):
   - `curl -s https://scout-packs-production.up.railway.app/ops/ledger`
     → 401 (proves route live + auth on).
   - `curl -s -H "Authorization: Bearer $(cat ~/.config/scout-packs/ops-token)" https://scout-packs-production.up.railway.app/ops/ledger`
     → 200 with the real ledger; check `counts` against expectations
     (2 known settled sales = the baseline to reconcile).
   - `curl -s https://scout-packs-production.up.railway.app/health` → 200.
7. First real mirror run: `python3 telemetry/mirror.py` (expect exit 0),
   then `python3 telemetry/mirror.py summary` and eyeball per-kind
   attribution against the settled baseline.
8. Install the nightly job (03:15 America/New_York):
   `15 3 * * * /home/hatch/workspace/scout-packs/telemetry/run-nightly.sh`
   — or a hook per the standing hooks-over-crons rule; the script exits
   non-zero iff the latest run failed, and appends to
   `telemetry/store/nightly.log`.

## Rollback

- Pre-deploy: abandon the branch (`git branch -D
  feature/telemetry-ledger-mirror`); nothing in production can be affected.
- Post-deploy: unset `SCOUTPACKS_OPS_TOKEN` on Railway → the endpoint
  instantly disables itself (404) with no redeploy; then revert the merge
  at leisure. The endpoint is purely additive and read-only — no existing
  route, price, or ledger write path changes behaviour. Local store files
  under `telemetry/store/` are copies; deleting them loses nothing the
  server doesn't still hold (until the server volume is lost — which is
  the point of the mirror).
