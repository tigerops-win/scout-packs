# HANDOFF — Composite Dossier Endpoint (`GET /dossier`)

Builder: Tiger subagent, 2026-10-16. Status: **built and tested locally only.
NOT committed, NOT pushed, NOT deployed.** Production (Railway) untouched.

## Branch / commit state

- Local branch: `feature/dossier-endpoint` (created from `main` @ `71dae59`).
- Nothing committed. All changes are uncommitted working-tree changes on that
  branch. Nothing pushed anywhere.
- Working-tree changes for this feature:
  - `server.py` (+258 lines, 0 deletions): `BAZAAR_DOSSIER`, dossier section
    (`DOSSIER_*` constants, `dossier()`, `verify_dossier_payment()`,
    `dossier_payment_terms()`, `dossier_paywall_body()`), Handler routes
    (`GET /dossier`, `POST /fulfill-dossier`) + Handler methods
    (`dossier_paywall`, `serve_paid_dossier`, `fulfill_dossier`),
    enumeration in `catalog()`, `well_known()`, `sample_record()` pricing,
    and `LLMS_TXT`.
  - `openapi-draft.json` (+65): `/dossier` and `/fulfill-dossier` paths.
  - `mcp/scout_packs_mcp.py` (+16): `dossier` MCP tool via
    `_x402_instructions()`.
  - New: `dossier/` (SPEC.md, ACCEPTANCE.md, TASKS.md, this HANDOFF.md) and
    `tests/test_dossier.py` + `tests/__init__.py`.
- Pre-existing dirt NOT from this build (was already in the tree on arrival,
  left untouched): `M mcp-registry/server.json`, plus untracked files
  (`agentndx-submission-payload-2026-10-13.md`, `bazaar-audit-*.md`,
  `data-pipeline/`, `endpoint-expansion-spec.md`, `shelf-prs/…`, `work/`, …).

## What was built

`GET /dossier?domain=<domain>` — one x402 call fusing `domain_intel()`,
`tech_stack()`, `email_pattern()`, and `ssl_check()` into a single response:
verbatim per-section results + per-section signals, a top-level aggregated
`signals` list (section order, dedup, first occurrence wins), and a `sections`
list. Full shape, wiring, and the price rationale are in SPEC.md.
Price: **$0.05 USDC** (`DOSSIER_AMOUNT = 50_000`) — exact sum of the four
parts ($0.02+$0.01+$0.01+$0.01), above the $0.01–$0.03 penny tier, no premium
and no discount (rationale: SPEC.md, "Price proposal").

## Test evidence

Command (repo root):

```
python3 -m unittest tests.test_dossier -v
```

Final run, 2026-10-16: **13 tests ran, OK (all passing)** in ~111 s.
(The runtime is dominated by live-upstream timeouts for Fixtures 2–3 in this
sandbox — RDAP/DoH/site fetches — not by local logic.)

Coverage, mapped to ACCEPTANCE.md:

- Fixture 1 (invalid domain `not-a-domain`): exact fused dict equality.
  First run FAILED on one detail: `domain_intel()` returns early on an
  invalid domain before assigning `intel["signals"]`, so the verbatim
  section has no `signals` key. The expectation in ACCEPTANCE.md and the
  test were corrected to the source function's actual documented/observed
  behaviour (section stays verbatim; the flag reaches the aggregated list
  via the second return value). No fusion code was changed to fit the test.
- Fixture 2 (`example.com`): email-pattern known answers exact (the 10
  hard-coded patterns from `email_pattern()`, in order); other sections
  asserted for shape/type only, live values [CHECK].
- Fixture 3 (`jane@example.com`): cleaned domain `example.com` reaches every
  section; patterns exact.
- Fixture 4 (canned returns copied from the `BAZAAR_*` documented output
  examples): verbatim section fusion + hand-written aggregated signals,
  plus a cross-section dedup case.
- HTTP: unpaid 402 body + both payment headers (v2 amount `"50000"`, v1
  `maxAmountRequired "50000"`, Bazaar extension present); `/catalog`,
  `/.well-known/x402`, `/sample`, `/openapi.json` enumeration;
  `POST /fulfill-dossier` 400-on-missing-domain and 402-on-unverified-tx;
  the four source endpoints unchanged (402 amounts 20000/10000/10000/10000).
- MCP tool presence verified by source inspection (MCP SDK not installed in
  this environment [CHECK], so the module was not imported).

Not tested locally (cannot be, without a wallet/facilitator/production
address): a real paid settlement on either path — [UNKNOWN] until a live
test purchase after deploy.

Known inherited quirks (pre-existing, NOT introduced or fixed here):

- `server.py` never imports `ssl`/`socket` at module level, so `ssl_check()`
  in this environment degrades to `connection_failed` via its own exception
  handling [CHECK — the same code path serves production `/ssl-check`; the
  2026-10-06 build note says raw TLS also fails in this sandbox due to the
  egress proxy but works on Railway's direct egress]. Verify `/ssl-check`
  live behaviour before/after deploy separately if this matters.
- Dossier latency = sum of the four source calls (sequential, no caching);
  live latency [CHECK] unmeasured.

## Deploy-prep — exact steps for Tiger to run later (DO NOT run as part of this build)

1. Review this diff on branch `feature/dossier-endpoint`:
   `git diff main -- server.py openapi-draft.json mcp/scout_packs_mcp.py`
   and read `dossier/` + `tests/`.
2. Re-run the fixture tests on the machine that will deploy:
   `python3 -m unittest tests.test_dossier -v` — expect 13 tests, OK.
3. Commit ONLY this feature's files (leave the pre-existing dirt out):
   `git add server.py openapi-draft.json mcp/scout_packs_mcp.py dossier tests`
   then commit with a message naming the endpoint, price, and local test
   result. Push the branch / merge to `main` per the normal Scout Packs flow.
4. Deploy to Railway the same way previous Scout Packs deploys were done
   (production service for `scout-packs-production.up.railway.app`; see
   `REDEPLOY-CHECKLIST.md` in the repo root and follow it — it predates this
   feature and remains the deploy checklist of record [CHECK: confirm it is
   still current before relying on it]).
   No new env vars are required: `/dossier` reuses
   `SCOUTPACKS_RECEIVING_ADDRESS`, `X402_FACILITATOR_URL`, and the existing
   settled/redeemed stores.
5. Post-deploy smoke checks (read-only first):
   - `GET https://scout-packs-production.up.railway.app/dossier?domain=example.com`
     → 402, `price_usd 0.05`, both payment headers decode, amount `50000`.
   - `GET /catalog`, `GET /.well-known/x402`, `GET /sample`,
     `GET /openapi.json` → each enumerates `/dossier` at $0.05.
   - `GET /llms.txt` → lists `/dossier`.
6. One real paid test purchase ($0.05) via a buyer wallet, both paths if
   possible: signed x402 retry on `GET /dossier`, and manual
   `POST /fulfill-dossier`. Confirm the fused body, the
   `PAYMENT-RESPONSE`/`X-PAYMENT-RESPONSE` header, and a `dossier` line in
   the sales log (`data/dossier_sales.jsonl` via `log_sale`).
7. Only after step 6 passes: discovery follow-through, each a separate
   decision — Bazaar/CDP ingestion happens automatically on the first
   settled payment carrying the `BAZAAR_DOSSIER` extension; consider
   updating `mcp-registry/server.json` tool list and the README endpoint
   list in a follow-up commit (neither was changed in this build:
   `server.json` already had unrelated uncommitted changes, and README
   updates ride the deploy commit at Tiger's discretion).

## Rollback

- Pre-deploy: abandon the branch — `git checkout main` and
  `git branch -D feature/dossier-endpoint` (changes are uncommitted, so also
  `git checkout -- server.py openapi-draft.json mcp/scout_packs_mcp.py` and
  remove `dossier/` + `tests/` if the branch was never committed). Nothing
  in production can be affected: nothing was deployed.
- Post-deploy: redeploy the previous Railway build / revert the single
  feature commit (`git revert <commit>` then redeploy). `/dossier` is purely
  additive — no existing route, price, or data file changes behaviour — so a
  revert restores the exact prior surface. The only durable side effect a
  live period can leave is `data/dossier_sales.jsonl` entries and any
  redeemed tx hashes for `/fulfill-dossier` payments in
  `data/redeemed.json`; both are append-only records of real sales and
  should be kept, not rolled back.
