# Scout Packs — Redeploy Bundle Checklist (staged 2026-10-04)

**Why:** Analyst's #1 sales lever. Zero paid lookups to date; the diagnosis
(`~/workspace/ai-crew/zero-sales-diagnosis.md`) found `/lookup` priced at
$0.10 = 20x the default agent wallet policy cap ($0.005/request) and 10x the
proven clearing price of the best-selling direct competitor
(`x402.agentutility.ai`, $0.01, 397 calls/30d). Kill gate: **5+ paid lookups
from 3+ wallets by Oct 16**, or the agent-priced data play dies.

**What it does:** reprices everything to $0.01 (demand probe — margin
inversion vs. Scout COGS is acknowledged, this is a price-discovery test),
fixes the broken preview, wires CDP Bazaar discovery extensions onto every
paid x402 route, publishes a public `/skill.md`, keyword-tunes tool
names/descriptions for the Agent402 `/api/route` text-match router, and
ships a durable-HTTPS MCP endpoint (`/mcp`) on the same Railway domain.

**Scope:** code in the working tree only. **NOT deployed** — Railway
production (`scout-packs-production.up.railway.app`) untouched and healthy.

---

## One-line deploy checklist (single-tap moment for Conor)

```
cd ~/workspace/scout-packs && git add -A && git commit -m "redeploy bundle 2026-10-04: $0.01 reprice, preview-500 fix, CDP Bazaar extension, /skill.md, MCP-HTTP" && git push && <Railway redeploy via dashboard or `railway redeploy`> && curl -s https://scout-packs-production.up.railway.app/health && curl -s -o /dev/null -w "lookup %{http_code}\n" "https://scout-packs-production.up.railway.app/lookup?query=Julie%20Services"
```

Conor's action: **tap "ship it"** → I run the sequence above, then verify the
live 402 (`maxAmountRequired: 10000`, `extra.name: USD Coin`, bazaar
extension) on the production URL. Deploy needs his tap per standing rules;
the code is staged and locally verified.

> **Railway MCP wiring caveat (from OPS.md):** the committed Dockerfile CMD
> starts the *stdio* MCP server, not the HTTP stack — production's start
> command is believed to be overridden in the Railway dashboard. At deploy
> time, confirm the dashboard start command runs **both** processes on one
> dyno: `BASE_URL=http://127.0.0.1:$PORT MCP_HTTP_PORT=8001 python
> mcp/http_server.py & MCP_PROXY_PORT=8001 python server.py`. Unset
> `MCP_PROXY_PORT` → `/mcp` 404s by design (no crash).

---

## File-by-file diff summary (working tree vs HEAD)

| File | Change | Why |
|---|---|---|
| `server.py` (+188/−71 → now +207/−39 after my fix) | All packs $9/$15/$25 → **$0.01 flat** (`PACKS` dict); `/lookup` **$0.10 → $0.01** (`LOOKUP_PRICE_USD=0.01`, `LOOKUP_AMOUNT=10_000`); `preview_pack()` rewritten with defensive `.get()` (see below); `LOOKUP_DESC` keyword-tuned for router text-match ("B2B lead enrichment — contact lookup…") and wired into both the `/lookup` 402 body and `/.well-known/x402`; CDP Bazaar `extensions.bazaar` (discoverable + input/output schemas) attached to every paid `accepts[]` entry (lookup, packs, `/.well-known/x402`); NEW `GET /skill.md` (serves `skills/scout-packs-lead-lookup/SKILL.md` as `text/markdown`, 404 if missing); NEW `/mcp` reverse-proxy to sibling MCP server when `MCP_PROXY_PORT` set (502 on upstream failure, never a fake response); `EIP-712 extra.name: "USD Coin"`, `version: "2"`; homepage + llms.txt + FAQ copy updated to $0.01/probe framing | (a) reprice, (b) preview-500 fix, (c) bazaar extension, (d) /skill.md, (e) keyword tuning, (f) MCP proxy — the whole bundle |
| `mcp/http_server.py` (NEW, untracked) | Streamable-HTTP MCP server wrapping the same tools, stateless mode, binds 127.0.0.1, DNS-rebinding protection off (reverse-proxied, no browser clients) | (f) MCP-HTTP completion — durable-HTTPS `mcp_url` is an AgentShare listing precondition; stdio-only is rejected |
| `mcp/scout_packs_mcp.py` (+71/−17) | NEW `lookup_lead` tool ($0.01, keyword-tuned description); fallback prices → $0.01; `list_packs`/`buy_pack` descriptions keyword-tuned | MCP side of the reprice + router text-match |
| `SKILL.md` (NEW) + `skills/scout-packs-lead-lookup/SKILL.md` (NEW) | Agent skill file: lead-lookup usage, $0.01/lookup, name/description frontmatter | (d) discovery hygiene — agents cite skills; served live at `/skill.md` |
| `openapi-draft.json` (NEW) | Full OpenAPI doc incl. `/lookup` + `/fulfill-lookup` with $0.01 terms documented; served at `/openapi.json` | Machine-readable shelf asset (x402scan/AgentShare/awesome-lists) |
| `server.json`, `smithery.yaml` | Descriptions rewritten: "B2B lead enrichment … $0.01/lookup, packs $0.01/pack" | (e) registry text-match (Smithery, MCP registries) |
| `mcp/README.md`, `mcp/REGISTRIES.md` | Price blurbs → $0.01; registry drafts updated | Consistency — no stale $9/$15/$25 or $0.10 anywhere (grep-verified: zero remaining) |
| `README.md`, `OPS.md` | README: pricing table, endpoints, buying flow → $0.01 probe; OPS: Railway is sole production (localtunnel retired), MCP wiring documented, MCP start-command caveat recorded | Ops truth for the next deploy |
| `.env.example` | `MCP_PROXY_PORT` documented | One-dyno MCP wiring discoverability |

**My change this run (the only unfinished bundle item):** `preview_pack()` in
`server.py` — was the last `[]`-keyed lead indexer in the file. Rewrote every
field read as `.get()` with fallbacks (`category` → "uncategorized", missing
email → `"***"`, missing URL → `""`). A record missing a key previously raised
`KeyError` → 500 `{"error":"internal"}` on `/packs/{25,50,100}/preview` (the
diagnosis's friction finding #2). All other `[]`-style lead accesses are gone
(grep-confirmed).

---

## Local test evidence (all run against a local stack on 127.0.0.1:18080/18081 — production untouched)

| Check | Result |
|---|---|
| `GET /lookup?query=Julie Services - Auto Repair` | **HTTP 402**; `maxAmountRequired: "10000"` (= **exactly $0.01** USDC); `extra.name: "USD Coin"` (not "USDC"), `extra.version: "2"` |
| Served x402 config, `/lookup` resource | `extensions.bazaar.discoverable: true`, with `inputSchema.queryParams.query` + `outputSchema`; description starts "B2B lead enrichment — contact lookup: enrich any company with a verified business email + source URL…" |
| `GET /.well-known/x402` | First resource = `/lookup`, price 10000, `extra.name: "USD Coin"`, bazaar extension present; `/packs/25` also 10000 + bazaar extension |
| `GET /skill.md` | **HTTP 200**, `text/markdown`, 65 lines, frontmatter `name: scout-packs-lead-lookup`, description names the $0.01 price |
| `GET /packs/25/preview` (+ `/50`, `/100`) | **HTTP 200** (was 500), `price_usd: 0.01`, masked emails |
| `GET /packs/50` | **HTTP 402**, `maxAmountRequired: "10000"`, `extra.name: "USD Coin"` |
| MCP streamable-HTTP via `/mcp` proxy | `initialize` → `scout-packs` server; `tools/list` → `list_packs`, `buy_pack`, `lookup_lead` — end-to-end through the reverse proxy |
| `python3 -m py_compile server.py mcp/http_server.py` | OK |
| Stale-price grep across all bundle files | Zero remaining references to $0.10 / $9 / $15 / $25 |

Test servers were started locally and killed after verification. Nothing was
sent to Railway, nothing spent, nothing purchased.

---

## Known follow-ups (out of this bundle's scope)

- **Preview lead-count mismatch:** `/packs/25/preview` returns 252 leads while
  `lead_count` says 25. Pre-existing data quirk (the 25-pack JSON holds the
  full inventory). Not fixed — changing fulfillment payloads is a product
  decision, and `POST /fulfill` delivers the same JSON file. Flagging for the
  next sprint.
- **dev.to dead-link fix** (diagnosis item #2): the article points at a dead
  loca.lt tunnel — needs whoever holds the dev.to login; flagged to parent.
- **x402scan manual submission** (diagnosis item #3): needs Conor's browser or
  manual URL submission — flagged to parent.
- The 50/100-pack preview returns the 25-pack sample (their data files don't
  exist; they're assembled on demand). Honest labeling; acceptable for the
  demand probe.
