# Scout Packs — Buy Verified B2B Lead Packs with USDC

Buy verified B2B lead packs for your outreach or research workflows.
No account. No API key. No subscription. Pay per pack in USDC on Base.

## Packs (demand-probe pricing, 2026-10-04)

- **25 leads — $0.01 USDC** — instant JSON download after payment
- **50 leads — $0.01 USDC** — assembled and delivered within 24 hours
- **100 leads — $0.01 USDC** — assembled and delivered within 24 hours

Plus per-lead enrichment: `GET /lookup?query=<company or domain>` —
**$0.01 USDC** per verified business email lookup (`POST /fulfill-lookup`
to redeem).

Every lead: company name, contact name, title, **published business email**,
source URL where it was found. Machine-readable JSON. If an email isn't
published, it isn't in the pack. Nothing guessed, nothing pattern-matched.

## How to buy (x402 flow)

1. **Check the price** — unpaid request returns HTTP 402 with payment terms:
   ```
   curl -s -i https://scout-packs-production.up.railway.app/packs/25
   # HTTP/1.1 402 Payment Required
   # x402Version: 2, scheme: exact, network: eip155:8453 (Base)
   # payTo: 0xAF7B70D8487EE6193701597E67f56A5902d23913
   # asset: USDC 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913
   # amount: 10000 ($0.01)
   ```

2. **Pay (standard x402)** — sign an EIP-3009 authorization for the exact
   USDC amount on Base to the `payTo` address, then retry the same URL with
   the signature in the `X-PAYMENT` (v1) or `PAYMENT-SIGNATURE` (v2) header.
   The payment is verified and settled via facilitator; no separate transfer
   needed.

   Fallback: send the exact USDC amount on Base to `payTo` yourself, then
   redeem with the tx hash (`POST /fulfill` for packs, `POST /fulfill-lookup`
   for lookups).

3. **Receive** — the 25-pack (or lookup contact) returns as JSON immediately.
   For 50/100-packs, delivered within 24h of payment confirmation.

## Discovery (free, machine-readable)

- Catalog: `GET https://scout-packs-production.up.railway.app/catalog`
- Payment manifest: `GET https://scout-packs-production.up.railway.app/.well-known/x402`
- Agent docs: `GET https://scout-packs-production.up.railway.app/llms.txt`
- OpenAPI: `GET https://scout-packs-production.up.railway.app/openapi.json`
- Redacted preview: `GET https://scout-packs-production.up.railway.app/packs/25/preview`
- Lead-lookup skill: `GET https://scout-packs-production.up.railway.app/skill.md`
- MCP endpoint: `https://scout-packs-production.up.railway.app/mcp` (streamable HTTP)

## When to use this

- Your outreach workflow needs a verified lead list for a campaign
- Your research agent needs company/contact data with provenance
- You want per-pack pricing instead of a monthly data seat

## Operator

Tiger Operations — https://github.com/tigerops-win/scout-packs
