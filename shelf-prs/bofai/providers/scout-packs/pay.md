# Scout Packs — call & payment instructions (for agents and humans)

**Service:** Scout Packs by Tiger Operations
**What:** verified B2B lead packs sold per pack. No subscription, no account, no API key.
**Settlement:** USDC on Base mainnet (`eip155:8453`) via x402 `exact`.

## Packs and prices

| Pack | Leads | Price (USDC) | Fulfillment |
|------|-------|--------------|-------------|
| 25   | 25    | $9           | Instant JSON download after payment |
| 50   | 50    | $15          | Assembled and delivered within 24h |
| 100  | 100   | $25          | Assembled and delivered within 24h |

Every lead: company name, contact name, title, published business email,
source URL. Machine-readable JSON. If an email is not published, it is not
in the pack.

## How to buy (agent flow)

1. **Inspect payment terms** — make an unpaid request; you get HTTP 402:
   ```bash
   curl -s -i https://scout-packs-production.up.railway.app/packs/25
   # HTTP/1.1 402 Payment Required
   # body: x402Version 2, accepts[] with scheme "exact", network "eip155:8453",
   #   payTo 0xAF7B70D8487EE6193701597E67f56A5902d23913, asset USDC
   #   0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913, maxAmountRequired "9000000" ($9)
   ```
2. **Pay** — sign a USDC transfer on Base to the `payTo` address for the exact
   `maxAmountRequired`, then retry the same URL with the `X-Payment` header
   carrying the signed payment payload (standard x402 flow; use your
   facilitator of choice, e.g. `x402-fetch`).
3. **Receive** — the 25-pack returns as JSON immediately. For the 50/100-pack,
   POST the transaction hash to `/fulfill`; the pack is delivered within 24h
   of payment confirmation.

## Discovery (machine-readable)

- Catalog: `GET https://scout-packs-production.up.railway.app/catalog` (free)
- x402 manifest: `GET https://scout-packs-production.up.railway.app/.well-known/x402` (free)
- Agent notes: `GET https://scout-packs-production.up.railway.app/llms.txt` (free)
- Redacted preview: `GET https://scout-packs-production.up.railway.app/packs/25/preview` (free)

## Operator

Tiger Operations. Source: https://github.com/tigerops-win/scout-packs
