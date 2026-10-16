# SPEC — Telemetry Ledger Mirror (nightly mirror of Scout Packs sales ledgers)

Feature directory: `telemetry/` (this folder). Server change: `server.py`
(one new read endpoint). Client: `telemetry/mirror.py`. Tests:
`tests/test_telemetry_mirror.py`. Status: LOCAL ONLY — built and tested
locally on branch `feature/telemetry-ledger-mirror`, NOT deployed, NOT
pushed, 2026-10-16.

## Problem

Scout Packs' settled-sales ledgers live only on the Railway production
volume (`data/` under the server's `BASE_DIR`, gitignored runtime state).
Locally, per-endpoint sales attribution is [UNKNOWN]: we know from memory
that 2 paid calls settled ($0.02 total, 2 wallets), but we cannot say which
endpoints earned them, and any redeploy/volume loss takes the only copy of
the ledger with it. This build is the instrumentation fix: a nightly mirror
that pulls the service's own ledger state into a local append-only store.

## What the server already exposes (audit of `server.py`, 2026-10-16)

Read surfaces that exist today — all public, none authenticated:

- `GET /health` → `{"ok": true, "sales_enabled": bool}`. No sales data.
- `GET /catalog`, `/.well-known/x402`, `/sample`, `/openapi.json`,
  `/llms.txt`, `/skill.md` — discovery/pricing only.
- There is **no** ops/admin/stats/sales endpoint, **no** `Authorization`
  check, **no** API-key pattern anywhere in the codebase. The only
  secret-handling conventions in the repo are: (a) config via `SCOUTPACKS_*`
  environment variables (e.g. `SCOUTPACKS_RECEIVING_ADDRESS`,
  `X402_FACILITATOR_URL`), and (b) the 402index token kept as a raw secret in
  a 600-perm file (`~/.config/scout-packs/402index-token`) with only its
  hash committed/served.

Conclusion: **no existing read path for ledger state. A server-side read
endpoint must be added** (this build, locally only, undeployed — see
"Remaining deploy step" in HANDOFF.md / the coordinator brief).

## Ledger state on the server (what there is to mirror)

All under `BASE_DIR/data/` on the production volume:

1. `data/<kind>_sales.jsonl` — one file per service kind, appended by
   `log_sale(kind, record)` in `server.py`. Kinds seen in the code:
   `lookup`, `deliverability`, `domain-intel`, `tech-stack`,
   `email-pattern`, `ssl-check`, `dossier`, `headers`, `dns`, `subdomains`,
   `contact-page`, `mail-provider`, `repo-health`, `packsize`, `pack`.
   Common record fields: `ts` (added by `log_sale`, UTC
   `%Y-%m-%dT%H:%M:%SZ`), `method` (`"x402"` or `"manual"`), `tx_hash`,
   `sender`, `amount_usd`, plus one subject field per kind (`query`,
   `domain`, `target`, `title`, `repo`, or `pack`). x402 records also carry
   `replay` (bool). One exception: the manual `POST /fulfill-lookup` path
   appends to `lookup_sales.jsonl` directly with shape
   `{ts, query, tx_hash, sender, amount_usd}` — **no `method` field**. The
   mirror must tolerate missing fields, never assume a uniform schema.
2. `data/x402_settled.json` — the facilitator settlement index:
   `{sha256(payment_b64): {"tx_hash", "payer", "ts"}}`. Proves a payment
   settled, but carries **no endpoint attribution** — attribution comes
   from the sales jsonl files; the settled index is mirrored for
   cross-checking (settled count vs. attributed sales count).
3. `data/redeemed.json` — JSON list of manually-redeemed tx hashes
   (the manual `/fulfill*` replay guard).

Out of scope for the mirror: `build_intakes.jsonl` (Tiger Builds intake
forms — not sales, contains submitter emails; deliberately NOT mirrored by
this endpoint).

## Design

### Server: `GET /ops/ledger` (new, in `server.py`, local branch only)

- Auth — reuses the codebase's only secret conventions (env config +
  constant-time handling): the token is read from env
  `SCOUTPACKS_OPS_TOKEN` at process start.
  - Env unset/empty → endpoint is **disabled**: responds
    `404 {"error": "not_found"}`, indistinguishable from an unknown route.
    Fail closed; nothing about the ledger leaks, not even its existence.
  - Env set → request must carry `Authorization: Bearer <token>`, compared
    with `hmac.compare_digest`. Missing/wrong → `401 {"error":
    "unauthorized"}`.
- Response (200, JSON):
  ```json
  {
    "generated_at": "<UTC ts>",
    "sales": {"<kind>": [ <raw record>, ... ], ...},
    "settled": { "<payment_digest>": {"tx_hash": "...", "payer": "...", "ts": "..."} },
    "redeemed": ["0x<tx_hash>", ...],
    "counts": {"sales_total": N, "per_kind": {"<kind>": n, ...},
               "settled": M, "redeemed": K, "unparseable_lines": U}
  }
  ```
  - `sales` is built by scanning `data/` for `*_sales.jsonl` files (kind =
    filename minus `_sales.jsonl`), parsing each line as JSON; a line that
    fails to parse is included verbatim as
    `{"_raw": "<line>", "_parse_error": true}` and counted in
    `unparseable_lines` — ledger fidelity over prettiness.
  - Optional query param `since=<ISO ts>`: sales records with a parseable
    `ts` strictly greater than `since` only; records with missing/
    unparseable `ts` are always included (cannot be proven old).
    `settled`/`redeemed` are always returned in full (small, and the
    mirror unions them). The mirror itself fetches without `since`
    (simplest correct mode at current volume); `since` exists for later.
- Read-only: the handler never writes. It is not added to `/catalog`,
  `/.well-known/x402`, `openapi-draft.json`, `LLMS_TXT`, or CORS paths —
  it is an ops surface, not a discovery surface.

### Client: `telemetry/mirror.py` (stdlib only, like the rest of the repo)

- Config: base URL from env `SCOUTPACKS_BASE_URL` (default
  `https://scout-packs-production.up.railway.app`); token from env
  `SCOUTPACKS_OPS_TOKEN`, else from the 600-perm file
  `~/.config/scout-packs/ops-token` (the 402index-token precedent).
  No token anywhere → exit 2, nothing written except a run-log entry.
- One run: `GET {base}/ops/ledger` with the Bearer token → validate the
  payload shape → merge into the local store → append a run-log entry.
- Local store — `telemetry/store/` (gitignored, like `data/`):
  - `sales.jsonl` — **append-only** unified sales ledger. Each line is the
    server record verbatim plus `"_kind"` (source kind) and `"_sale_id"`.
  - `settled.json` — merged settlement index (union of keys; on a key
    conflict the server's record wins and the conflict is counted in the
    run log).
  - `redeemed.json` — merged, sorted list of tx hashes (union).
  - `state.json` — `{last_run_at, last_success_at, source_counts,
    total_sales_mirrored}` bookkeeping, rewritten atomically (tmp+replace,
    the `save_settled` pattern in `server.py`).
  - `runs.jsonl` — append-only run log: `{ts, ok, fetched, appended,
    duplicates_skipped, settled_total, redeemed_total, error?}`.
- Deduplication / idempotency: `_sale_id = sha256(kind + "|" +
  canonical_json(record))` where canonical_json is `json.dumps(record,
  sort_keys=True)`. On each run the mirror loads all existing `_sale_id`s
  from `sales.jsonl` and appends only records whose id is not already
  present. Re-running against an unchanged server appends **zero** lines
  and leaves `sales.jsonl` byte-identical. Known limitation, accepted and
  documented: two server lines that are byte-for-byte identical records
  (same second-resolution `ts`, same tx, same everything) are
  indistinguishable in the source ledger itself and collapse to one
  mirrored line; x402 replays are logged by the server with their own
  `ts`/`replay` fields, so genuine repeats remain distinguishable.
- Failure behaviour: fail closed. Any HTTP error, auth failure, or
  malformed payload → non-zero exit (3 = HTTP/auth, 4 = bad payload),
  `sales.jsonl`/`settled.json`/`redeemed.json` untouched, failure recorded
  in `runs.jsonl` (and `state.json`'s `last_run_at` only). A scheduler
  surfaces the non-zero exit; a failed night loses nothing and the next
  successful run backfills everything (full-snapshot fetch + dedup).
- `python3 telemetry/mirror.py summary` — read-only report from the LOCAL
  store only: per-kind sale counts, per-kind `amount_usd` totals, grand
  total, distinct `sender` count, settled/redeemed counts, last successful
  run time. This is the human verification surface and the attribution
  payoff: settled-but-unattributed = `settled_total - sales_total` is
  printed explicitly, never smoothed over.

### Nightly procedure (summary; full version in HANDOFF.md)

Nightly ~03:15 America/New_York, run
`telemetry/run-nightly.sh` (sets env from the token file, runs the mirror,
appends output to `telemetry/store/nightly.log`). Recommended mechanism:
a hook/cron entry per Tiger's standing rules (hooks over frequent crons;
a once-nightly cron is acceptable). Verify: exit 0 + `runs.jsonl` tail +
`mirror.py summary` totals move when sales occur.

## Non-goals / rails

- No deploy, no push, no production touch, no sends, no spend, no
  publishing, no ProtonMail. Server change lives only on local branch
  `feature/telemetry-ledger-mirror`.
- No real paid settlement is exercised by this build; end-to-end paid
  settlement remains [UNKNOWN] until a post-deploy test purchase.
- No changes to any existing route, price, or ledger write path.
