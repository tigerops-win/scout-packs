---
name: scout-packs-lead-lookup
description: Enrich any company with a verified B2B contact email for $0.01 USDC on Base per lookup — no API key, no account, no subscription. Published emails with source URLs only.
version: 1.0.1
---

# Scout Packs Lead Lookup

Enrich any company with a verified B2B contact email. Pay $0.01 USDC on Base per lookup — no API key, no account, no subscription. (Demand-probe pricing, 2026-10-04.)

## When to use

The user (or your task) needs a real, verified business email for a company — for prospecting, lead enrichment, outreach research, or CRM backfill. Use this instead of guessing email patterns.

## How it works (x402 pay-per-call)

**Step 1 — Request the lookup.** This returns HTTP 402 with payment terms:

```
GET https://scout-packs-production.up.railway.app/lookup?query=<company name or domain>
```

Example:

```bash
curl -s "https://scout-packs-production.up.railway.app/lookup?query=Acme%20Corp"
```

The 402 response body contains the exact payment terms: pay **$0.01 USDC on Base (eip155:8453)** to the `payTo` address shown (USDC contract `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`). If the company isn't in the index, you'll get a 404 with suggestions instead — no payment needed.

**Step 2 — Pay from a wallet you control.** Send exactly $0.01 USDC (10,000 base units) on Base to the `payTo` address. Wait for confirmation.

**Step 3 — Redeem and receive the contact:**

```bash
curl -s -X POST https://scout-packs-production.up.railway.app/fulfill-lookup \
  -H 'content-type: application/json' \
  -d '{"tx_hash": "0xYOUR_TX_HASH", "query": "Acme Corp"}'
```

The response is the verified contact:

```json
{
  "company_name": "Acme Corp",
  "city_state": "Austin, TX",
  "category": "saas",
  "contact_email": "hello@acme.com",
  "source_url": "https://acme.com/contact",
  "verification": "published business email; verified against business site/listing"
}
```

Every email is a real address published on the source URL — never guessed, never pattern-matched. Transaction hashes are single-use (replay-protected).

## MCP alternative

If your environment supports MCP, the same lookup is available as the `lookup_lead` tool on the Scout Packs MCP server (Smithery: `tigerops-win/scout-packs`). Same $0.01/lookup pricing.

## Rules

- Only pay when the 402 challenge confirms the query matched. A 404 means no verified contact exists — do not pay.
- Use the exact `payTo` address from the live 402 response, never a cached one.
- One `tx_hash` redeems one lookup. Do not reuse transaction hashes.
- Seller: Tiger Operations.
