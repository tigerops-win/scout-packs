# PR draft: awesome-x402 listing for Scout Packs

**Status:** DRAFT — needs GitHub auth to open. All content below is ready to paste.
**Target repo:** https://github.com/xpaysh/awesome-x402
**File to edit:** `README.md`
**Section:** `## 🌟 Ecosystem Projects` → `### Data & Social APIs`
**Placement:** append at the end of the Data & Social APIs bullet list.

## PR metadata
- **Title:** `Add Scout Packs — verified B2B lead packs for AI agents (x402)`
- **Body:**
  ```
  Adds Scout Packs to Ecosystem Projects / Data & Social APIs.

  Scout Packs sells verified B2B lead packs (25/$9, 50/$15, 100/$25) to AI
  agents and operators behind an x402 paywall (USDC on Base, no account or
  API key). Every lead carries company, contact name, title, published email,
  and source URL as machine-readable JSON. Live endpoint with 402 discovery
  at /.well-known/x402. Open-source MCP server included.
  ```

## Exact diff (append to the end of the `### Data & Social APIs` list)

```diff
 - [agentdata-nl](https://agentdata-api.sander-van-aard.workers.dev) - European company screening for AI agents, straight from official public registers: company registers (UK, FR, NO, CH, CZ, FI, PL), insolvency checks (NL, FR), EU + UN sanctions screening, EU VAT (VIES), LEI, MiCA crypto-firm and token-registry checks, EURC peg monitoring and an x402 counterparty pre-payment trust check. 18 endpoints, $0.002–$0.18 per call, all-or-nothing billing — you are only charged when the task fully completed. x402 v2 with Bazaar discovery extension, USDC on Base via CDP facilitator. No API keys, no signup. ([x402 manifest](https://agentdata-api.sander-van-aard.workers.dev/.well-known/x402) | [OpenAPI](https://agentdata-api.sander-van-aard.workers.dev/openapi.json))
+
+- [Scout Packs](https://scout-packs-production.up.railway.app) - Verified B2B lead packs for AI agents and operators: 25 leads $9, 50 leads $15, 100 leads $25. Every lead carries company, contact name, title, published email, and source URL as machine-readable JSON. x402 paywall, USDC on Base, no account or API key. 25-pack delivers instantly; 50/100-pack assembled and delivered within 24h. ([GitHub](https://github.com/tigerops-win/scout-packs) | [Discovery](https://scout-packs-production.up.railway.app/.well-known/x402))
```

## Notes
- Precedent: tunnel URLs already appear in this list (e.g. a trycloudflare.com entry). NOTE 2026-10-02: production moved to https://scout-packs-production.up.railway.app (Railway); the loca.lt tunnel is dead.
- If the maintainer asks for a stable domain, re-submit after the endpoint moves off the tunnel to permanent hosting.
- How to submit: fork xpaysh/awesome-x402 → edit README.md → open PR with the title/body above.
