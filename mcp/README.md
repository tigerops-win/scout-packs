# Scout Packs MCP server — Tiger Operations

An MCP (Model Context Protocol) server that lets AI agents discover and buy
**Scout Packs** — verified B2B lead packs (25/$9, 50/$15, 100/$25, USDC on Base)
— from inside any MCP client (Claude Desktop, Cursor, MCP Inspector, agent
frameworks).

Brand: **Tiger Operations** only. No personal names, no invented claims.

## Install

Python 3.10+. Uses a local venv so the system Python stays clean:

```bash
cd ~/workspace/scout-packs/mcp
python3 -m venv .venv
.venv/bin/pip install mcp
```

Only dependency: the `mcp` Python SDK (free, open source). The server itself is
stdlib otherwise. $0 spend.

## Config

One environment variable:

| Var        | Default                 | Meaning                                    |
|------------|-------------------------|--------------------------------------------|
| `BASE_URL` | `http://localhost:8000` | Scout Packs HTTP endpoint (sibling server) |

The MCP server talks only to `BASE_URL`. It never touches wallets, keys, or
any other host. When the endpoint moves to its public URL, just set `BASE_URL`
to that URL — no code changes.

## Run

```bash
cd ~/workspace/scout-packs/mcp
BASE_URL=http://localhost:8000 .venv/bin/python scout_packs_mcp.py
```

stdio transport (standard for MCP clients).

### Claude Desktop config example

```json
{
  "mcpServers": {
    "scout-packs": {
      "command": "/home/hatch/workspace/scout-packs/mcp/.venv/bin/python",
      "args": ["/home/hatch/workspace/scout-packs/mcp/scout_packs_mcp.py"],
      "env": { "BASE_URL": "https://<public-endpoint-url>" }
    }
  }
}
```

## Tools

### `list_packs` — free, no arguments

Returns the pack catalog (sizes, prices in USDC on Base `eip155:8453`,
fulfillment ETAs), live sales status, and a redacted sample (emails masked,
source domains shown). Every response ends with the honest fulfillment note.

### `buy_pack` — arguments: `pack` ("25" | "50" | "100")

Returns the exact x402 payment requirements for the pack (`payTo` address,
exact USDC amount, asset contract, network) plus the step-by-step flow the
buying agent must follow:

1. Send the exact USDC amount on Base to `payTo` from a wallet the agent controls.
2. `POST {BASE_URL}/fulfill` with `{"tx_hash": "0x...", "pack": "<size>"}`.
3. Pack 25 comes back as JSON; 50/100 return an order receipt (delivered within 24h).

Safety: if the endpoint reports `sales_enabled=false`, the tool says SALES
PAUSED and instructs the agent NOT to send funds. The tool never moves funds
and never holds private keys.

## Worked example (MCP Inspector)

```bash
npx @modelcontextprotocol/inspector
# connect: stdio, command .venv/bin/python, args scout_packs_mcp.py
# env: BASE_URL=http://localhost:8000
```

1. Call `list_packs` → see the three packs and the masked sample.
2. Call `buy_pack` with `{"pack": "25"}` → copy the `payTo` address and exact
   amount, pay from your own wallet, then `POST /fulfill` with the tx hash.

## Interface contract (matches `../README.md` exactly)

- `GET {BASE_URL}/catalog` → `{seller, packs: {scout-pack-N: {leads, price_usd, currency, network, fulfillment_eta}}, sales_enabled}`
- `GET {BASE_URL}/packs/{25,50,100}/preview` → redacted sample (masked emails)
- `GET {BASE_URL}/packs/{25,50,100}` → HTTP 402 + JSON body `{price_usd, currency, network, fulfillment, sales_enabled, x402: {accepts: [{payTo, maxAmountRequired, asset, network, resource}]}, how_to_pay}`

If the endpoint is unreachable, `list_packs` falls back to the documented
catalog and labels it as fallback; `buy_pack` refuses rather than guessing
payment details.
