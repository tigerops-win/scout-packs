# Scout Packs — Pay-Per-Call B2B Data for AI Agents

Buy verified B2B data with USDC on Base. No account. No API key. No subscription.
The plugin installs free; each data call is a pay-per-call x402 transaction.

**Operator:** Tiger Operations — https://github.com/tigerops-win/scout-packs

## What you get

- `lookup_lead` — verified B2B contact email + company enrichment by company or domain — **$0.01**
- `deliverability` — MX/SPF/DMARC, disposable/role detection, bounce-risk score — **$0.03**
- `domain_intel` — RDAP registration data + DNS infra signals — **$0.02**
- `tech_stack` — tech-stack detection from headers + markup — **$0.01**
- `email_pattern` — likely corporate email patterns + MX check — **$0.01**
- `ssl_check` — SSL/TLS details + risk flags — **$0.01**
- `headers` — security headers audit, A–F grade — **$0.01**
- `dns` — full DNS record dump (A, AAAA, MX, TXT, NS, CNAME) — **$0.01**
- `subdomains` — CT-log subdomain footprint, intent-classified — **$0.02**
- `contact_page` — published emails (role vs personal), phone numbers — **$0.02**
- `mail_provider` — mailbox host (Google Workspace, Microsoft 365, …) — **$0.01**
- `repo_health` — GitHub repo health: stars, forks, issues, license, velocity — **$0.01**
- `packsize` — parse product titles into pack count / unit size / unit price — **$0.02**
- `list_packs` / `buy_pack` — pre-built lead packs (25/50/100 verified leads) — **$0.01/pack**

Every lead/email: company name, contact name, title, **published** business email,
source URL where it was found. If it isn't published, it isn't in the data.
Nothing guessed, nothing pattern-matched.

## How to pay (x402 flow)

1. Call the endpoint unpaid — it returns **HTTP 402** with payment terms:
   `x402Version: 2, scheme: exact, network: eip155:8453 (Base)`,
   asset: USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`, amount in 6-decimal USDC.
2. Sign an EIP-3009 authorization for the exact USDC amount on Base to the
   `payTo` address, then retry with the signature in the `X-PAYMENT` (v1) or
   `PAYMENT-SIGNATURE` (v2) header. Settled by facilitator — no separate transfer.
3. Receive the data as JSON immediately.

Fallback: send the exact USDC on Base to `payTo` yourself, then redeem with the
tx hash (`POST /fulfill`, `/fulfill-lookup`, etc.).

## Discovery (free, machine-readable)

- Catalog: `GET https://scout-packs-production.up.railway.app/catalog`
- Payment manifest: `GET https://scout-packs-production.up.railway.app/.well-known/x402`
- Agent docs: `GET https://scout-packs-production.up.railway.app/llms.txt`
- OpenAPI: `GET https://scout-packs-production.up.railway.app/openapi.json`
- MCP endpoint: `https://scout-packs-production.up.railway.app/mcp` (streamable HTTP)

## When to use this

- Your outreach workflow needs a verified lead list or a real contact email
- Your research agent needs company/domain data with provenance
- You want per-call pricing instead of a monthly data seat
