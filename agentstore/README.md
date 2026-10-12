# AgentStore listing prep — Scout Packs

**Status:** manifest drafted + schema-validated. Publisher registration is the only
prerequisite; the actual agent publish stays with the Closer run.

## Files

- `agent-manifest.json` — full manifest, validated against AgentStore's authoritative
  zod schema (`packages/api/src/schema/agent-manifest.ts` in techgangboss/agentstore):
  agent_id 3-part pattern, name ≤100, description 356 chars (10–500), version semver,
  publisher object, pricing model=free/amount=0 (open-agent business rule),
  wrapper checksum `sha256:aa3e2c5b…b183a` matches `agent-wrapper.md`,
  gateway route → `https://scout-packs-production.up.railway.app/mcp` with all 15 MCP
  tools, auth=none (open-agent business rule), permissions, 10 tags, updated_at.
- `agent-wrapper.md` — the markdown agent wrapper (install entrypoint content).
- `publish-payload.json` — ready-to-POST body for the tap-free
  `POST https://api.agentstore.tools/api/publishers/agents/simple` free-publish path
  (no auth for free model; rate-limited; goes live immediately).
  Validated against `SimpleAgentSchema` in `packages/api/src/app/api/publishers/agents/simple/route.ts`.
  Note: the free listing itself is free; per-call data costs $0.01–$0.03 USDC on Base
  and are enforced by the API's own 402 flow, not by AgentStore.

## Tonight's Closer run — exact commands

```bash
# 1. Register publisher (one-time, no auth, rate-limited).
#    Safe to re-run: returns 409 "Publisher name already taken" if it exists —
#    treat 409 as success and continue.
curl -s -X POST https://api.agentstore.tools/api/publishers \
  -H "Content-Type: application/json" \
  -d '{"name":"tiger-operations","display_name":"Tiger Operations"}'

# 2. Publish the free agent (no auth needed for model=free; rate-limited).
#    Agent goes live immediately on agentstore.tools.
curl -s -X POST https://api.agentstore.tools/api/publishers/agents/simple \
  -H "Content-Type: application/json" \
  -d @publish-payload.json
```

Verify live: `agentstore install tiger-operations.scout-packs` (agent_id auto-generated
as `<publisher_id>.<slugified-name>`) or search agentstore.tools for "Scout Packs".

## Why not the CLI submit flow

`agentstore publisher submit agent-manifest.json` requires a local wallet signature
(`agentstore wallet setup`) and is the path for paid listings. The curl flow above
is the documented tap-free path for free listings.
