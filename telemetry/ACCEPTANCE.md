# ACCEPTANCE — Telemetry Ledger Mirror

Written BEFORE the implementation (2026-10-16), per the four-file contract.
Expected answers are hand-written below from the ledger shapes documented in
SPEC.md (which were read out of `server.py`'s `log_sale()` call sites), NOT
computed by running the mirror. Fixture data is invented test data — fake tx
hashes, fake wallets — and must never be mistaken for real sales.

Test implementation: `tests/test_telemetry_mirror.py` (stdlib `unittest`,
run with `python3 -m unittest tests.test_telemetry_mirror -v` from the repo
root). No network beyond 127.0.0.1; no live upstreams are called.

## Fixture ledger (server-side, written to a temp `data/` dir by the test)

`lookup_sales.jsonl` — 2 lines:
1. x402 shape (from `serve_paid_lookup`'s `log_sale` call):
   `{"method": "x402", "query": "acme.com", "tx_hash": "0xaaa1",
   "sender": "0xwallet1", "amount_usd": 0.01, "replay": false,
   "ts": "2026-10-10T01:02:03Z"}`
2. manual shape (from `fulfill_lookup`'s direct append — NO `method`):
   `{"ts": "2026-10-11T04:05:06Z", "query": "beta.com",
   "tx_hash": "0xbbb2", "sender": "0xwallet2", "amount_usd": 0.01}`

`dossier_sales.jsonl` — 1 line:
`{"method": "manual", "domain": "gamma.com", "tx_hash": "0xccc3",
"sender": "0xwallet1", "amount_usd": 0.05, "ts": "2026-10-12T07:08:09Z"}`

`x402_settled.json` — 2 entries:
`{"digestA": {"tx_hash": "0xaaa1", "payer": "0xwallet1", "ts": "2026-10-10T01:02:03Z"},
  "digestB": {"tx_hash": "0xddd4", "payer": "0xwallet3", "ts": "2026-10-12T09:10:11Z"}}`
(`0xddd4` intentionally has NO sales-jsonl line: settled-but-unattributed.)

`redeemed.json` — `["0xbbb2", "0xccc3"]`

## Server endpoint criteria (`GET /ops/ledger`)

1. Token env unset → `404`, body `{"error": "not_found"}` (endpoint
   disabled, fail closed).
2. Token env set, no `Authorization` header → `401 {"error": "unauthorized"}`.
3. Token env set, wrong token → `401 {"error": "unauthorized"}`.
4. Token env set, correct Bearer token → `200` with:
   - `sales.lookup` == the 2 fixture records above, in file order, verbatim.
   - `sales.dossier` == the 1 fixture record, verbatim.
   - `settled` == the fixture dict verbatim; `redeemed` == the fixture list.
   - `counts` == `{"sales_total": 3, "per_kind": {"lookup": 2, "dossier": 1},
     "settled": 2, "redeemed": 2, "unparseable_lines": 0}`.
   - `generated_at` present and a string.
5. `since=2026-10-11T00:00:00Z` → `sales.lookup` contains ONLY fixture line 2
   (line 1's `ts` 2026-10-10 ≤ since); `sales.dossier` still contains its
   line (ts 2026-10-12 > since); `counts.sales_total == 2`;
   settled/redeemed unaffected (full).
6. A malformed line appended to `dossier_sales.jsonl` (`not json{`) →
   it appears as `{"_raw": "not json{", "_parse_error": true}` in
   `sales.dossier`, and `counts.unparseable_lines == 1`.
7. No regressions: `GET /health` still `200 {"ok": true, ...}`;
   `GET /nonexistent` still `404 {"error": "not_found"}`;
   `GET /ops/ledger` is NOT present in `GET /catalog` output.

## Mirror criteria (`telemetry/mirror.py` against a local fixture server)

The fixture server is the real `server.py` Handler on an ephemeral
127.0.0.1 port, pointed at the fixture ledger above, token `test-token`.

8. First run → exit 0; store results:
   - `sales.jsonl` has exactly 3 lines; each line is the fixture record
     verbatim plus `"_kind"` (`"lookup"` ×2, `"dossier"` ×1) and a
     `"_sale_id"` that is a 64-char lowercase hex string; the 3 ids are
     pairwise distinct.
   - `settled.json` == fixture settled dict; `redeemed.json` ==
     `["0xbbb2", "0xccc3"]` (sorted).
   - `state.json`: `total_sales_mirrored == 3`, `last_success_at` set.
   - `runs.jsonl` last entry: `ok == true, fetched == 3, appended == 3,
     duplicates_skipped == 0`.
9. Second run (server unchanged) → exit 0; `sales.jsonl` **byte-identical**
   to after run 1; run log entry `appended == 0, duplicates_skipped == 3`.
10. Third run after appending ONE new line to the server's
    `lookup_sales.jsonl` (`{"method": "x402", "query": "delta.com",
    "tx_hash": "0xeee5", "sender": "0xwallet2", "amount_usd": 0.01,
    "replay": false, "ts": "2026-10-13T01:01:01Z"}`) → exit 0;
    `appended == 1, duplicates_skipped == 3`; `sales.jsonl` has 4 lines and
    its first 3 lines are byte-identical to before (append-only preserved).
11. Wrong token → exit non-zero (3); `sales.jsonl`, `settled.json`,
    `redeemed.json` byte-identical to before; run log gains an `ok == false`
    entry naming the failure.
12. Server returns malformed payload (stub handler returning `{"bogus": 1}`)
    → exit non-zero (4); store files byte-identical; run log `ok == false`.
13. No token in env and no token file → exit 2; no store files created
    other than `runs.jsonl` bookkeeping [CHECK: if the implementation
    writes `runs.jsonl` into a not-yet-created store dir, that is the only
    file permitted].

## Summary criteria (`mirror.py summary`, from the post-run-10 store)

14. Output reports, from local data only:
    - per-kind counts: `lookup: 3`, `dossier: 1`;
    - per-kind USD totals: lookup `0.03`, dossier `0.05`; grand total `0.08`
      (floats compared with tolerance 1e-9);
    - distinct senders == 2 (`0xwallet1`, `0xwallet2`);
    - `settled_total == 2`, `redeemed_total == 2`;
    - settled-but-unattributed printed as `settled 2 - sales 4` is NOT the
      formula — the report must state attributed sales (4) and settled
      settlements (2) as separate lines and flag that they count different
      things (sales lines include manual redemptions and replays) rather
      than inventing a reconciliation number. Pass = both numbers present,
      no fabricated "unattributed" figure presented as fact. [The fixture's
      `0xddd4` settled-without-sale case is exactly why: from local data
      alone its attribution is [UNKNOWN].]

## Explicitly NOT acceptance criteria

- Any contact with the production service (tests are 127.0.0.1 only).
- A real paid settlement — [UNKNOWN] until Tiger deploys and a test
  purchase is made.
- Reconciliation of `x402_settled.json` digests to endpoints — impossible
  from the settled index alone (it has no endpoint field); the mirror
  preserves the data, it does not invent attribution.
