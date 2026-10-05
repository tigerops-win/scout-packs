# Scout Packs — Tiger Operations

Verified B2B lead packs and per-lead enrichment lookups sold to AI agents over
**x402** (USDC on Base, `eip155:8453`). **Demand-probe pricing (2026-10-04):
$0.01 per lookup or pack.** Margin inversion vs. Scout COGS is acknowledged —
this is a demand probe, not a business model. Kill gate: ≥3 paid lookups from
≥2 distinct wallets in 7 days post-reprice.

| Pack | Leads | Price | Fulfillment |
|------|-------|-------|-------------|
| scout-pack-25 | 25 | $0.01 | instant JSON download after payment |
| scout-pack-50 | 50 | $0.01 | assembled on demand, delivered within 24h |
| scout-pack-100 | 100 | $0.01 | assembled on demand, delivered within 24h |

Per-lead enrichment: `GET /lookup?query=<company or domain>` — 402 paywall,
**$0.01 USDC**, `POST /fulfill-lookup` returns one verified business email +
source URL + provenance.

Each lead: `company_name`, `city_state`, `category`, `contact_email` (verified business email), `source_url`.

## Endpoints

- `GET /` — human landing page
- `GET /catalog` — packs & prices (JSON)
- `GET /.well-known/x402` — machine-readable payment terms
- `GET /llms.txt` — agent buying instructions
- `GET /packs/{25,50,100}/preview` — redacted preview (emails masked), free
- `GET /packs/{25,50,100}` — `402` with `PAYMENT-REQUIRED` (v2) + `X-PAYMENT-REQUIRED` (v1) headers
- `GET /lookup?query=<company or domain>` — `402` with payment terms ($0.01 USDC); no match → `404`
- `POST /fulfill` — `{"tx_hash":"0x...","pack":"25","deliver_to":"..."}`
- `POST /fulfill-lookup` — `{"tx_hash":"0x...","query":"<company>"}`
- `GET /skill.md` — agent skill file for the lead lookup (markdown)
- `/mcp` — MCP streamable-HTTP endpoint (proxied to the sibling MCP server when `MCP_PROXY_PORT` is set)

## Interface reference (for agent/MCP clients)

`GET /packs/{25,50,100}` → `402 Payment Required`
- Headers: `PAYMENT-REQUIRED` = base64(JSON x402 v2 terms), `X-PAYMENT-REQUIRED` = base64(JSON x402 v1 terms)
- Body: `{error:"payment_required", pack, leads, price_usd, currency:"USDC", network:"eip155:8453", fulfillment, sales_enabled, x402:{x402Version:2, accepts:[{scheme:"exact", network, maxAmountRequired (atomic USDC, 6 decimals), resource, description, mimeType, payTo, maxTimeoutSeconds, asset, extra}]}, how_to_pay:[...]}`
- `sales_enabled:false` while the seller address is unconfigured (current state); flips automatically once set.

`POST /fulfill` — body `{tx_hash:"0x…", pack:"25"|"50"|"100", deliver_to:"…" (optional)}`
- Success, pack 25 → `200 {receipt:"ok", pack:"scout-pack-25", tx_hash, verified_at, leads:{…25-lead pack JSON…}}`
- Success, pack 50/100 → `200 {receipt:"ok", pack, tx_hash, verified_at, order_id, status:"queued_for_assembly", eta:"within 24 hours of payment confirmation", deliver_to, note}`
- Failure → `402 {error:"payment_not_verified", detail:"sales_paused: receiving address not configured" | "bad_tx_hash" | "already_redeemed" | "tx_not_found" | "tx_not_successful" | "tx_too_old" | "no_matching_usdc_transfer" | "chain_lookup_failed", pay:[…steps…]}` or `400 {error:"unknown_pack"|"bad_json"}`

Verification rules: tx must be a successful Base USDC transfer of ≥ the pack amount to the configured receiving address, mined <30 days ago, and each tx hash is single-use.

## Buying flow

1. `GET /packs/25` → read the 402 terms (`payTo`, exact USDC amount).
2. Send exactly $0.01 USDC on Base to `payTo`.
3. `POST /fulfill` with the tx hash → pack 25 delivered as JSON; 50/100 return a 24h order receipt.

Payment is verified on-chain (Blockscout free API): the tx must be a successful
USDC transfer of ≥ the pack amount to the receiving address. Tx hashes are
single-use (replay-protected); txs older than 30 days are rejected.

## Config

- `SCOUTPACKS_RECEIVING_ADDRESS` — the Base address that receives USDC. **While
  unset (or the zero address) the endpoint runs in preview-only mode**:
  `sales_enabled=false` in 402 bodies and `/.well-known/x402`, and `/fulfill`
  refuses all requests.
- `SCOUTPACKS_PUBLIC_BASE` — public URL used in 402 `resource` fields.
- `PORT` — default 8000.
- `MCP_PROXY_PORT` — optional (e.g. `8001`); when set, `/mcp` reverse-proxies to
  the sibling MCP streamable-HTTP server (`mcp/http_server.py`) on that port —
  one deploy exposes both the x402 API and a durable-HTTPS MCP endpoint.

## Deploy

```bash
./run.sh &                                   # localhost:8000
```

Production (since 2026-10-02) runs on **Railway** —
`https://scout-packs-production.up.railway.app` is the sole production endpoint.
The old localtunnel path (lt-proxy.js, loca.lt subdomains) is dead legacy, retired
2026-10-02 after chronic 503s. On normal infra for a fresh deploy,
`cloudflared tunnel --url http://127.0.0.1:8000` works as usual.

Then register on the open indexes, e.g. 402 Index:
`POST https://402index.io/api/v1/register` with
`{url, name, protocol:"x402", description, price_usd, payment_asset:"USDC",
payment_network:"eip155:8453", category:"data", tags:[...]}`.

## MCP server (for agent clients)

AI agents can also discover and buy packs from inside MCP clients
(Claude Desktop, Cursor, MCP Inspector, agent frameworks) via the MCP server
in [`mcp/`](mcp/):

- `list_packs` — free. Pack sizes, prices, live sales status, redacted sample.
- `buy_pack` — returns the exact x402 payment terms and the step-by-step flow;
  the buying agent's own wallet pays the endpoint. Never moves funds, never
  holds keys.

Quick start (Python 3.10+, installs the `mcp` SDK only):

```bash
cd mcp && python3 -m venv .venv && .venv/bin/pip install mcp
BASE_URL=https://<endpoint-url> .venv/bin/python scout_packs_mcp.py
```

Or once published to PyPI: `uvx scout-packs-mcp` with `BASE_URL` set.
Full docs: [`mcp/README.md`](mcp/README.md). Registry listings:
[`mcp/REGISTRIES.md`](mcp/REGISTRIES.md).
