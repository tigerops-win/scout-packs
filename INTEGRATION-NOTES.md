# Wave-2 endpoints — integration notes (2026-10-06)

Three new $0.01 x402 endpoints: `/headers`, `/dns`, `/repo-health`.
Pattern mirrors `ssl-check` exactly. NOT committed, NOT deployed — awaiting review.

## Files touched

1. **`server.py`** (+742 / -1; the -1 is the intentional `timedelta` import addition)
   - Price constants: `HEADERS_*`, `DNS_*`, `REPOHEALTH_*` (`*_PRICE_USD = 0.01`, `*_AMOUNT = 10000`)
   - Bazaar extensions: `BAZAAR_HEADERS`, `BAZAAR_DNS`, `BAZAAR_REPOHEALTH`
   - Detection fns (before `# ---- server`): `security_headers()`, `dns_dump()` (+`_doh_query()`),
     `repo_health()` (+`_gh_get()`), `SECURITY_HEADERS` / `_DOH_TYPES` / `_REPO_RE` tables
   - Paywall wiring per endpoint: `verify_*_payment()`, `*_payment_terms()`, `*_paywall_body()`
   - `Handler` methods per endpoint: `*_paywall()`, `serve_paid_*()`, `fulfill_*()`
   - `do_GET` routes: `/headers`, `/dns`, `/repo-health` (400 on missing param)
   - `do_POST` routes: `/fulfill-headers`, `/fulfill-dns`, `/fulfill-repo-health`
   - `catalog()` → 3 new `per_call_services` entries
   - `well_known()` → 3 new manifest resource tuples
2. **`mcp/scout_packs_mcp.py`** (+38): new `@mcp.tool()`s `headers()`, `dns()`, `repo_health()`
3. **`openapi-draft.json`** (+126, surgical, formatting preserved): 6 new paths
   (`/headers`, `/fulfill-headers`, `/dns`, `/fulfill-dns`, `/repo-health`, `/fulfill-repo-health`)

Pre-existing uncommitted change I did NOT make: `mcp-registry/server.json` (was already
modified in the working tree before this task started — 1+/17-).

## Verified

- `python3 -m py_compile server.py mcp/scout_packs_mcp.py` → OK
- Live server smoke test (PORT=8899): `/headers`, `/dns`, `/repo-health` → **HTTP 402**;
  missing-param variants → 400; manifest, `/catalog`, `/openapi.json` all list the new routes;
  402 body carries `service`, `price_usd: 0.01`, `x402Version: 2`, PAYMENT-REQUIRED headers
- Detection fns unit-checked: invalid input → `invalid_domain`/`invalid_repo` flags, no crash;
  live calls through sandbox egress all returned real data:
  `dns_dump("example.com")` → 2 A records + `has_spf`;
  `repo_health("octocat/hello-world")` → 3850 stars;
  `security_headers("example.com")` → score 0 / grade F (bare IANA page, plausible)
- Old endpoints (`/ssl-check`, `/tech-stack`) still return 402 — no regressions.
  (`/lookup?query=` returns 404 on the ORIGINAL code too — pre-existing, out of scope.)

## Not yet exercised

- Paid fulfillment paths (`serve_paid_*` via signed x402, `fulfill_*` via manual tx) need a
  real $0.01 USDC tx on Base — same as every other endpoint pre-launch.
- The 3 new $0.01 routes will each need a real tx hash before their separate PayAPI listings
  (adds $0.03 to the PayAPI self-pay tap).

## Test commands (reviewer)

```bash
cd ~/workspace/scout-packs && PORT=8899 python3 server.py &
curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8899/headers?domain=example.com"          # 402
curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8899/dns?domain=example.com"              # 402
curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8899/repo-health?repo=octocat/hello-world" # 402
curl -s "http://127.0.0.1:8899/.well-known/x402" | python3 -m json.tool | grep -c "repo-health\|/dns\|/headers"
curl -s "http://127.0.0.1:8899/catalog" | python3 -c "import json,sys; print([s['path'] for s in json.load(sys.stdin)['per_call_services']])"
curl -s "http://127.0.0.1:8899/openapi.json" | python3 -c "import json,sys; print(len(json.load(sys.stdin)['paths']))"  # 27
```

## Suggested ship checklist (parent)

1. Review `git diff server.py` (742+/1-)
2. Deploy to Railway, verify the 3 routes return 402 in production
3. Republish MCP Registry metadata (now 10 MCP tools) + update version
4. Patch 402index listing copy; update awesome-list entries
5. Make the 3 × $0.01 self-pay txs → submit 3 new PayAPI listings
