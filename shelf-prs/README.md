# Shelf PRs — Scout Packs marketplace/indexer submissions

Drafted 2026-10-01 ~9:40 PM EDT by the Track 2 subagent (sale blitz, Conor's 6 AM deadline).
All copy is under the Tiger Operations brand; no personal names.

## Ready to submit (need GitHub auth — a human or the main agent with a session)

### SAO BLITZ additions (drafted 2026-10-01 ~10:00 PM EDT)

### 3. punkpeye/awesome-mcp-servers (`awesome-mcp-servers-punkpeye.md`)
- **Repo:** https://github.com/punkpeye/awesome-mcp-servers (the canonical awesome MCP list)
- **Action:** fork → edit `README.md` → append entry at end of `### 🎯 Marketing` section
- **Emoji:** 🐍 (Python) + ☁️ (Cloud Service). No Glama badge yet.

### 4. appcypher/awesome-mcp-servers (`awesome-mcp-servers-appcypher.md`)
- **Repo:** https://github.com/appcypher/awesome-mcp-servers (~5.6k stars)
- **Action:** fork → edit `README.md` → append entry at end of `## 🎯 Marketing` section
- **Format:** icon + linked name + one-line description.

### 5. wong2/awesome-mcp-servers (`awesome-mcp-servers-wong2.md`)
- **Repo:** https://github.com/wong2/awesome-mcp-servers
- **Action:** fork → edit `README.md` → insert alphabetically in `## Community Servers`
  (between Search1API and Scrapeless).

### 6. haoruilee/awesome-agent-native-services (`agent-native-services-issue.md`)
- **Repo:** https://github.com/haoruilee/awesome-agent-native-services
- **The agent-native directory** (239 services, 16 categories, machine-readable catalog.json + llms.txt).
- **Action:** open an ISSUE FIRST (template 🆕 New service) — maintainer ✅ Go required
  before any PR (review within ~7 days). Full issue body drafted, plus the
  service file (`agent-native-services-scout-packs.md`) ready for the PR step.
- **Why we qualify:** URL Onboarding ⭐ via llms.txt, x402 as the agent-native
  payment primitive, MCP server, no human checkout exists.

### glama.json (`glama.json`)
- **Action:** add this file to the ROOT of tigerops-win/scout-packs via the
  GitHub browser session: `{"$schema":"https://glama.ai/mcp/schemas/server.json","maintainers":["tigerops-win"]}`
- Glama auto-discovers from GitHub; the listing 404s today. Adding glama.json
  triggers indexing (~24h), then the listing can be claimed via "Login with GitHub".

## Moltbook — agent registered, claim pending (human step)
- Agent `tigeroperations` registered via API 2026-10-02 ~01:53 UTC.
- Public profile: https://www.moltbook.com/u/tigeroperations (live, HTTP 200).
- Credentials in `~/workspace/scout-packs/.secrets/moltbook.json` (600 perms).
- **Unlock:** Conor visits https://www.moltbook.com/claim/moltbook_claim_IYUcqYrQVheG04VD3fHHI3rbB9e4fbK3,
  verifies email, posts the verification tweet (`I'm claiming my AI agent "tigeroperations" on @moltbook 🦞 / Verification: claw-VVDH`).
  Until claimed, the agent cannot post/comment. Reading the feed works.

## Browser-needed surfaces (no-auth web forms)
- **mcpservers.org/submit** — Server Name, Category=Marketing, description, repo URL,
  contact email (required — needs an operator address, NOT Conor's personal Gmail).
  Free review ~2 weeks. (This also feeds wong2/awesome-mcp-servers, which takes no PRs.)
- **mcp.so/submit** — 2 fields (repo URL + name). Blocks automated requests; browser only.
- **x402bazaar.org** — JS app, submission path unclear from text fetch; needs live-browser investigation.
- **PulseMCP** — NOT accepting new servers as of Sept 2026; ingests from the official MCP
  registry only. Blocked until we're on the official registry (blocked on PyPI).

### 1. awesome-x402 (`awesome-x402.md`)
- **Repo:** https://github.com/xpaysh/awesome-x402 (community directory, 854 services)
- **Action:** fork → edit `README.md` → append the one-line bullet under
  `## 🌟 Ecosystem Projects` → `### Data & Social APIs` (exact diff in the file)
- **Precedent:** tunnel URLs already in the list (trycloudflare.com entry). NOTE 2026-10-02: production moved to https://scout-packs-production.up.railway.app (Railway); the loca.lt tunnel is dead.
- **Note:** if the maintainer wants a stable domain, re-submit after the endpoint moves off the tunnel.

### 2. bofai api-catalog (`bofai/providers/scout-packs/`)
- **Files:** `catalog.json` (validated JSON; fqn `scout-packs`, version 1, chains `eip155:8453`,
  full zh-CN i18n, 3 endpoints GET /packs/{25,50,100} at $9/$15/$25) + `pay.md` (call & payment guide).
- **Action:** open a PR against the bofai api-catalog repo with these two files at
  `providers/scout-packs/catalog.json` and `providers/scout-packs/pay.md`.
- **Caveat:** bofai's model expects their Gateway in front of the service
  (official or self-hosted). After the PR, listing also needs either gateway
  onboarding (1–2 business days, email/Telegram contact) or a self-hosted
  gateway deploy. PR draft is the correct first step; gateway is follow-up work.
- **Validate before PR:** confirm `category: "data"` is in their allowed list
  (their CI enforces it; check `reference.md` in the catalog repo).

## Verified BLOCKED (documented, do not retry without the stated unlock)

| Surface | Blocker | Unlock |
|---|---|---|
| x402-list.com (854 services, biggest) | llms.txt: dev-tunnel URLs rejected at any price | Real (non-tunnel) hosting |
| x402scan.com | `POST /api/x402/registry/register` → 402 "SIWX authentication required" (tested 2026-10-01) | Wallet signature = Conor's tap |
| agentic.market / CDP Bazaar / Onyx Bazaar | No submit form; indexed only from CDP-facilitator settlements | Route payments via CDP facilitator + first real settlement |
| PayAI Bazaar | No form/account/manual submission; indexes only from PayAI-facilitator payments | Route payments via PayAI facilitator |
| x402-skill-registry | $0.01 x402 payment to register (can't pay) + requires Base AND Solana rails | Funded wallet + Solana rail |
| agentinternetruntime.com/directory | One-time wallet payment ($0.01–$10 tiers) | Funded wallet |
| x402bazaar.org | Community marketplace (95 APIs); site is a JS app, submission path unclear, likely requires their middleware | Investigate with live browser |
| Pay.sh | Solana-only skills repo | N/A (we're Base-only) |
| x402.dev | Domain-for-sale page | Dead |

## Discovery hygiene (for the Builder lane)
- `/.well-known/x402` ✅ live and correct (v2, sales_enabled true)
- `/catalog`, `/llms.txt`, `/packs/{25,50,100}` ✅ live
- `/openapi.json` ❌ 404 — multiple indexers (x402scan, agentic.market docs) treat an
  origin-root openapi.json as the discovery document. Adding one would widen
  auto-crawl compatibility. Recommended follow-up, not a listing blocker.
