# Scout Packs — Purchase-Loop Walkthrough (402 → pay → fulfill)

Reproduce the full purchase loop against the live production API.
Base URL: `https://scout-packs-production.up.railway.app`
Today's date: 2026-10-02. Sales so far: 0. Kill gate: 5+ paid lookups from 3+ wallets by Oct 16, 2026.

## Payment config (public — returned by the live server itself)

| Field | Value |
|---|---|
| payTo (receiving address) | `0xaf7b70d8487ee6193701597e67f56a5902d23913` |
| Network | `eip155:8453` (Base mainnet) |
| Base native USDC contract | `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913` |
| Amount | `10000` atomic units = $0.01 (USDC, 6 decimals) |
| x402 scheme | `exact`, version 2 |

## Step 1 — trigger the 402 (no payment needed)

```bash
curl -s -D - "https://scout-packs-production.up.railway.app/lookup?query=edison" | head -60
```

Expected: `HTTP/1.1 402 Payment Required` with a JSON body containing
`error: "payment_required"`, `price_usd: 0.1`, and an `x402.accepts[0]` block
with `payTo`, `asset`, `network: "eip155:8453"`, `maxAmountRequired: "10000"`,
plus a `how_to_pay` array. Verify `payTo` matches the address in the table above.

Note: the query must match a company in the 252-contact database, otherwise
you get `404 {"error":"no_match"}`. `edison` (Edison Electric, Inc.) works.
Missing query → `400 {"error":"missing_query"}`.

## Step 2 — pay $0.01 USDC on Base (OPERATOR ACTION — do not run unattended)

From any Base wallet holding ≥ $0.01 USDC, send exactly $0.01 to:

```
0xaf7b70d8487ee6193701597e67f56a5902d23913
```

Using `cast` (Foundry) as an example — adapt to your wallet tooling:

```bash
# Send 0.01 USDC (10000 base units) to the receiving address on Base
cast send 0xaf7b70d8487ee6193701597e67f56a5902d23913 \
  "transfer(address,uint256)" 0xaf7b70d8487ee6193701597e67f56a5902d23913 10000 \
  --rpc-url https://mainnet.base.org \
  --contract 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 \
  --private-key "$YOUR_PRIVATE_KEY"   # keep this secret; never commit it
```

Record the resulting tx hash. The server verifies it on-chain via Blockscout:
successful Base USDC transfer of ≥ $0.01 to payTo, mined < 30 days ago,
single-use per tx hash.

DO NOT make payments on Conor's behalf — spending needs his tap.

## Step 3 — redeem the payment for the lookup result

```bash
curl -s -X POST "https://scout-packs-production.up.railway.app/fulfill-lookup" \
  -H 'Content-Type: application/json' \
  -d '{"tx_hash":"0xYOUR_TX_HASH_HERE","query":"edison"}' | python3 -m json.tool
```

Expected on success (`200`):

```json
{
  "receipt": "ok",
  "service": "lead-lookup",
  "query": "edison",
  "tx_hash": "0x...",
  "price_usd": 0.1,
  "lead": {
    "company_name": "Edison Electric, Inc.",
    "city_state": "Minneapolis, MN",
    "category": "electrician",
    "contact_email": "<verified email>",
    "source_url": "<provenance URL>"
  },
  "verified_at": "2026-10-02T...Z",
  "note": "Verified business contact delivered. Source URL included for provenance."
}
```

On failure you'll get `402 {"error":"payment_not_verified", "detail": ...}` with
detail one of: `bad_tx_hash`, `tx_not_found`, `tx_not_successful`, `tx_too_old`,
`no_matching_usdc_transfer`, `chain_lookup_failed`, or `already_redeemed`.

## Related endpoints (same pattern)

```bash
# pack 25 ($0.01 USDC): GET /packs/25  → 402, POST /fulfill {"tx_hash":"0x...","pack":"25"}
curl -s -o /dev/null -w "%{http_code}\n" "https://scout-packs-production.up.railway.app/packs/25"
curl -s "https://scout-packs-production.up.railway.app/catalog"
curl -s "https://scout-packs-production.up.railway.app/.well-known/x402" | python3 -m json.tool
```
