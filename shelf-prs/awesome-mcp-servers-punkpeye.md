# PR draft: punkpeye/awesome-mcp-servers listing for Scout Packs

**Status:** DRAFT — needs GitHub auth to open. All content below is ready to paste.
**Target repo:** https://github.com/punkpeye/awesome-mcp-servers (the canonical awesome MCP list)
**File to edit:** `README.md`
**Section:** `## Server Implementations` → `### 🎯 Marketing`
**Placement:** append at the END of the Marketing bullet list (after the
`prepublish/prepublish-mcp` line, before the blank line + `### 📊 Monitoring`).

## PR metadata
- **Title:** `Add Scout Packs MCP server (Marketing)`
- **Body:**
  ```
  Adds the Scout Packs MCP server to the Marketing category.

  Scout Packs sells verified B2B lead packs (25/$9, 50/$15, 100/$25) to AI
  agents and operators behind an x402 paywall (USDC on Base, no account or
  API key). Every lead carries company, contact name, title, published email,
  and source URL as machine-readable JSON. The MCP server exposes list_packs
  and buy_pack tools; it reads the catalog and x402 payment terms from the
  live endpoint and never holds keys or moves funds.

  Repo: https://github.com/tigerops-win/scout-packs
  Live endpoint: https://scout-packs-production.up.railway.app
  ```

## Exact diff (append to the end of the Marketing list)

```diff
 - [prepublish/prepublish-mcp](https://github.com/prepublish/prepublish-mcp) [![prepublish/prepublish-mcp MCP server](https://glama.ai/mcp/servers/prepublish/prepublish-mcp/badges/score.svg)](https://glama.ai/mcp/servers/prepublish/prepublish-mcp) 🎖️ 📇 ☁️ - Audit YouTube scripts before recording: hook, structure and pacing scores, drop-off passages, policy and inauthentic-content checks, and runtime estimates.
+
+- [tigerops-win/scout-packs](https://github.com/tigerops-win/scout-packs) 🐍 ☁️ - Verified B2B lead packs for AI agents: 25/$9, 50/$15, 100/$25 behind an x402 paywall (USDC on Base). Every lead carries company, contact, title, published email, and source URL as machine-readable JSON. No account, no API key.
```

## Notes
- Emoji: 🐍 (Python codebase) + ☁️ (Cloud Service — talks to the remote x402 endpoint).
- No Glama badge yet (Glama hasn't indexed the repo; see glama.json note below).
- If the maintainer asks for a stable (non-tunnel) endpoint URL, re-submit after the endpoint moves to permanent hosting.
- How to submit: fork punkpeye/awesome-mcp-servers → edit README.md → open PR with the title/body above.
