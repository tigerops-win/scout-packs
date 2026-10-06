# Scout Packs

> **"Verified B2B lead packs, sold to AI agents over x402 (USDC on Base)."**

| | |
|---|---|
| **Website** | https://scout-packs-production.up.railway.app |
| **Docs** | https://scout-packs-production.up.railway.app/llms.txt |
| **GitHub** | https://github.com/tigerops-win/scout-packs |
| **Classification** | `agent-native` |
| **Category** | [Search & Web Intelligence](README.md) |

---

## Official Website

https://scout-packs-production.up.railway.app

---

## Official Repo

https://github.com/tigerops-win/scout-packs

---

## ⭐ How to Use (Agent Onboarding)

**URL Onboarding** — read one file and buy:

```
Read https://scout-packs-production.up.railway.app/llms.txt and follow the instructions to buy a lead pack.
```

The buying loop, fully autonomous:
1. `GET /catalog` — free. Pack list and prices.
2. `GET /packs/25` — returns HTTP 402 with x402 v2 payment terms
   (`payTo`, `maxAmountRequired`, `asset`, `network` in the `PAYMENT-REQUIRED` header).
3. Send the exact USDC amount on Base (eip155:8453) to the `payTo` address.
4. Retry with the `X-Payment` header (standard x402 flow), or
   `POST /fulfill {"tx_hash": "0x...", "pack": "25"}`.
5. Receive the pack as JSON. No account, no API key, no signup.

**MCP:**
```json
// mcp_servers
{
  "scout-packs": {
    "command": "python3",
    "args": ["mcp/scout_packs_mcp.py"],
    "cwd": "<repo>"
  }
}
```
Tools: `list_packs`, `buy_pack`. The server reads the catalog and x402 terms
from the live endpoint; it never holds keys or moves funds.

---

## Agent Skills

**Status:** ⚠️ Not yet published

---

## What It Sells

| Pack | Leads | Price (USDC) | Fulfillment |
|------|-------|--------------|-------------|
| 25   | 25    | $9           | Instant JSON download after payment |
| 50   | 50    | $15          | Assembled and delivered within 24h |
| 100  | 100  | $25          | Assembled and delivered within 24h |

Every lead: company name, contact name, title, **published** business email,
source URL. If an email is not published, it is not in the pack — nothing
pattern-matched, nothing guessed.

---

## Why It Is Agent-Native

- **x402 paywall as the primitive:** the 402 challenge → USDC payment →
  retry flow is machine-to-machine by construction. There is no human checkout
  page; a human cannot buy without an agent wallet.
- **Fixed per-pack pricing:** bounded spend per purchase ($9/$15/$25), no
  seat, no subscription, no sales call.
- **Machine discovery:** `/.well-known/x402` (v2 manifest), `/catalog`,
  `/llms.txt`, `/packs/25/preview` (redacted sample, emails masked).
- **Audit trail:** payment is wallet-to-wallet on Base; the transaction hash
  is the receipt.

---

## Operator

Tiger Operations. Source: https://github.com/tigerops-win/scout-packs
