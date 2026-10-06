# Issue draft: propose Scout Packs to haoruilee/awesome-agent-native-services

**Status:** DRAFT — needs GitHub auth to open. This repo requires an ISSUE FIRST
(maintainer ✅ Go within ~7 days) before any PR.
**Target repo:** https://github.com/haoruilee/awesome-agent-native-services
**Issue template:** 🆕 New service → `.github/ISSUE_TEMPLATE/01-new-service.yml`
**New issue URL:** https://github.com/haoruilee/awesome-agent-native-services/issues/new?template=01-new-service.yml

---

## Issue title
`[New Service] Scout Packs — verified B2B lead packs sold to AI agents over x402`

## Issue body (paste into the template fields)

**Service name:** Scout Packs
**Website:** https://scout-packs-production.up.railway.app
**Official repo:** https://github.com/tigerops-win/scout-packs
**Official tagline:** "Verified B2B lead packs, sold to AI agents over x402 (USDC on Base)."
**Proposed category:** 9. Search & Web Intelligence
**Classification:** `agent-native`
**MCP status:** ✅ Available — MCP server in the repo (`mcp/scout_packs_mcp.py`, tools: `list_packs`, `buy_pack`); reads catalog + x402 terms from the live endpoint, never holds keys or moves funds.
**Agent Skills:** ⚠️ Not yet published.

### Evidence for the five hard criteria

**1. Agent-First Positioning** — The product page and machine docs identify AI
agents as the primary consumer:
- `llms.txt`: "Scout Packs — Tiger Operations. Verified B2B lead packs, sold
  to AI agents over x402 (USDC on Base, eip155:8453)." —
  https://scout-packs-production.up.railway.app/llms.txt
- `/.well-known/x402` serves a machine-readable v2 payment manifest; there is
  no human checkout flow at all.

**2. Agent-Specific Primitives** — The x402 paywall IS the primitive: an HTTP
402 challenge carrying signed payment terms (`payTo`, `maxAmountRequired`,
`asset`, `network`), paid in USDC on Base and retried with an `X-Payment`
header. No account, no API key, no human checkout page exists. A human
developer would not use this flow to build a human-facing product — there is
no human-facing product.

**3. Autonomy-Compatible Control Plane** — An agent completes the full loop
without a human clicking anything: GET /catalog (free) → GET /packs/25 →
HTTP 402 with payment terms → sign USDC transfer on Base → retry with
X-Payment header (or POST /fulfill with the tx hash) → JSON download.
Spending is bounded per pack ($9/$15/$25 fixed).

**4. M2M Integration Surface** — Primary interfaces: REST API + MCP server.
The human landing page is informational only; nothing in the buying flow
requires it.

**5. Agent Identity / Delegation Semantics** — Payment is wallet-to-wallet on
Base: the agent's own wallet pays the operator's receiving address. No user
identity is minted or required; the audit trail is the on-chain transaction.

### URL Onboarding ⭐ (bonus signal)
`Read https://scout-packs-production.up.railway.app/llms.txt and follow the instructions
to buy a lead pack.` — the full buying protocol (catalog → 402 → pay →
fulfill) is documented in one machine-readable file. No signup, no SDK install.

### Why the generic alternative does not qualify
Apollo.io, ZoomInfo, and similar sell monthly seats to humans through sales
calls and dashboards — agent-adapted at best, excluded by the
"agent-adapted services" rule. Scout Packs has no seat, no dashboard, no sales
call; the x402 flow cannot be completed by a human without an agent wallet.

### Disclosure
Submitted by the operator (Tiger Operations). No other financial interest.

---

## After the ✅ Go — PR checklist (for later)
- PR title: `[New Service] Scout Packs`
- Create `services/search-web-intelligence/scout-packs.md` (draft below)
- Add a row to `services/search-web-intelligence/README.md`
- Add a row to the root `README.md` section 9 table
- Classification: `agent-native`
