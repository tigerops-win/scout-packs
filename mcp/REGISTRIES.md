# MCP registry listing drafts — Scout Packs

**Status: DRAFTS ONLY. Do not submit without Conor's tap** (standing rule).

Assumptions baked into these drafts:
- The Scout Packs repo becomes public at `https://github.com/tigerops-win/scout-packs`
  (currently only local at `~/workspace/scout-packs`). Pushing it public is a
  required prep step and an outward action — needs Conor's tap.
- Python distribution goes through PyPI as `scout-packs-mcp` (free to publish,
  installable via `uvx`). Publishing to PyPI is also an outward action —
  needs Conor's tap.
- Brand on every listing: **Tiger Operations**. No personal names.

## Shared listing copy (use verbatim everywhere)

- **Name:** `scout-packs`
- **Display name:** Scout Packs — Verified B2B Lead Packs
- **Short blurb (140 chars):** Verified B2B lead packs for AI agents: 25/$9, 50/$15, 100/$25. Machine-readable JSON, paid in USDC on Base over x402.
- **Long description:** Scout Packs by Tiger Operations sells verified B2B lead
  packs machine-to-machine. Each lead ships as JSON with company, city/state,
  category, verified business email, and source URL. Payment is x402 (USDC on
  Base): the `buy_pack` tool returns exact payment terms and the redeem flow;
  the agent's own wallet pays the endpoint. Pack 25 delivers instantly after
  on-chain verification; packs 50 and 100 are assembled on demand and delivered
  within 24 hours of payment confirmation.
- **Categories:** data, sales, marketing, developer-tools
- **Tags:** leads, b2b, x402, usdc, base, prospecting, mcp, agent-commerce
- **Homepage:** the endpoint URL (or repo URL until the public URL is final)
- **Repository:** https://github.com/tigerops-win/scout-packs
- **License:** MIT (add a LICENSE file to the repo before submitting)

## Prep steps (all three registries need these)

1. `git init` the scout-packs dir, add MIT LICENSE, push public to
   `tigerops-win/scout-packs` (needs Conor's tap — new public repo).
2. Publish `scout-packs-mcp` to PyPI (needs Conor's tap): package
   `mcp/scout_packs_mcp.py` with a `pyproject.toml` (requires-python >=3.10,
   dependencies `mcp>=2`), entry point `scout-packs-mcp = scout_packs_mcp:main`
   (add a `main()` wrapper) so `uvx scout-packs-mcp` works.
3. Set `BASE_URL` on the public endpoint and confirm `/catalog` serves the live
   pack list.

---

## 1. Official MCP Registry (registry.modelcontextprotocol.io)

Highest leverage: Glama, VS Code, and other aggregators ingest this registry.

**Steps:**
1. Install the publisher CLI:
   `brew install mcp-publisher` (or download the release tarball from
   github.com/modelcontextprotocol/registry).
2. From the repo root, generate and fill in `server.json`
   (`mcp-publisher init`, then apply the draft below). Namespace
   `io.github.tigerops-win/scout-packs` is verified via GitHub OAuth —
   simplest path.
3. `mcp-publisher login github`
4. `mcp-publisher publish`
5. Verify: `https://registry.modelcontextprotocol.io/v0/servers?search=scout-packs`

**`server.json` draft** (validate with `mcp-publisher init` before submitting —
schema evolves):

```json
{
  "name": "io.github.tigerops-win/scout-packs",
  "title": "Scout Packs — Verified B2B Lead Packs",
  "description": "Verified B2B lead packs for AI agents: 25/$9, 50/$15, 100/$25. Machine-readable JSON, paid in USDC on Base over x402.",
  "version": "1.0.0",
  "websiteUrl": "https://github.com/tigerops-win/scout-packs",
  "repository": {
    "url": "https://github.com/tigerops-win/scout-packs",
    "source": "github"
  },
  "packages": [
    {
      "registryType": "pypi",
      "identifier": "scout-packs-mcp",
      "version": "1.0.0",
      "transport": { "type": "stdio" },
      "runtimeHint": "uvx"
    }
  ]
}
```

---

## 2. Smithery (smithery.ai)

Most-trafficked MCP marketplace; one-click install for Claude Desktop / Cursor.

**Steps:**
1. Sign in at https://smithery.ai with the tigerops-win GitHub account.
2. Go to https://smithery.ai/new → **Add Server** → paste the repo URL
   `https://github.com/tigerops-win/scout-packs`.
3. Smithery scans for `smithery.yaml` at the repo root — commit the draft below
   before submitting.
4. Fill metadata from the shared copy block above; transport: **stdio**.
5. Complete the publishing flow, then **Settings → Verification** to request the
   verified badge (links back to the GitHub org).

**`smithery.yaml` draft** (repo root):

```yaml
name: scout-packs
description: "Verified B2B lead packs for AI agents: 25/$9, 50/$15, 100/$25. Machine-readable JSON, paid in USDC on Base over x402."
startCommand:
  type: stdio
  configSchema:
    type: object
    properties:
      baseUrl:
        type: string
        description: "Scout Packs endpoint base URL"
        default: "http://localhost:8000"
    required: []
  commandFunction: |
    (config) => ({
      command: "uvx",
      args: ["scout-packs-mcp"],
      env: { BASE_URL: config.baseUrl || "http://localhost:8000" }
    })
```

Verify: `https://smithery.ai/server/tigerops-win/scout-packs` (namespace may vary).

---

## 3. Glama (glama.ai/mcp)

Auto-discovers MCP servers from GitHub and the official registry — there is
**no submission form**. The work is claiming the listing and passing the build
check.

**Steps:**
1. Push the public repo (prep step 1). Glama's crawler picks it up on its own;
   the listing appears at `https://glama.ai/mcp/servers/tigerops-win/scout-packs`.
2. Click **"Login with GitHub to claim"** on the listing and claim it for the
   tigerops-win org.
3. The automated check needs the server to start and answer introspection. The
   repo-root `Dockerfile` (already added) builds the MCP server standalone:
   if Glama's Docker config only takes a Dockerfile path, the default
   `Dockerfile` at root works (build context = repo root).
4. Once the check passes and a real score renders, pull the badge:
   `https://glama.ai/mcp/servers/tigerops-win/scout-packs/badges/score.svg`
   and add it to the repo README.

---

## What NOT to submit yet

- **PulseMCP**: community reports conflict on whether submissions are open
  (their "Submit a server" form exists but at least one maintainer notes
  submissions are paused). Revisit after the three above are live.
- **mcp.so**: form-based directory, lower traffic; optional backlink play later.
