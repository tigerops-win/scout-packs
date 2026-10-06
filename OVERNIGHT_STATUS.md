# Scout Packs Sprint — Overnight Status (2026-10-02 01:30 EDT)

## Sales: 0

No payments detected. No USDC transfers to the receiving address.

## Infrastructure Status: DEGRADED

### What's Working
- Main API server (127.0.0.1:8000): UP, sales_enabled=true
- MCP server (127.0.0.1:8001): UP, responding to initialize
- Smithery listing: LIVE
- dev.to tutorial: LIVE

### What's Broken
- Main tunnel (scoutpacks-tunnel-1.loca.lt): DOWN — Localtunnel won't allocate the pinned subdomain
- Main tunnel (scoutpacks-1.loca.lt): DOWN — allocates but legs don't establish
- MCP tunnel (scoutpacks-mcp-bc34c6.loca.lt): DOWN — Bad Gateway, legs not establishing

### Root Cause (Updated 02:24 EDT)
Localtunnel's infrastructure is having a systemic issue. Initially only
`scoutpacks-tunnel-1` was affected, but now ALL pinned subdomain requests
return random URLs. The allocation API is ignoring the requested subdomain
entirely. This is a Localtunnel server-side outage, not a problem with our code.

The local servers (API on 8000, MCP on 8001) are healthy and running.
The watchdog cron (every 5 min) continues attempting to restore tunnel
connectivity and will succeed when Localtunnel's infrastructure recovers.

## Distribution Completed
- Smithery: LIVE (https://smithery.ai/servers/tigerops-win/scout-packs)
- dev.to: LIVE tutorial
- n8n forum: Post submitted, pending moderator approval
- Directories: 2 submitted (aiagentslive, aitoolshunt)
- GitHub PRs: coinbase/x402 #371 (awaiting review), xpaysh/awesome-x402 #1684, BofAI/x402-catalog #25
- 402index: 3 listings (point to dead URL — need update when stable URL available)
- Agent402: Registered (points to dead URL — needs update)

## Blocked
- Discord: hCaptcha unreadable, needs Conor's manual solve
- Indie Hackers: Needs Conor's Google OAuth tap
- X: Login retry at 1:05 AM (cron scheduled)
- Moltbook: Needs X access for claim
- 2 awesome-x402 PRs: Browser editor can't handle large README
- ClawHub: OAuth button disabled

## Recommendation
Move off Localtunnel to stable hosting ASAP. Options:
1. Railway/Render/Fly.io (stable URL, free tier, ~30 min setup)
2. Custom domain + Cloudflare Tunnel (best long-term)

All marketplace listings need URL updates once we have a stable endpoint.
