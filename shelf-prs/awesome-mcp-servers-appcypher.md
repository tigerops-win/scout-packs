# PR draft: appcypher/awesome-mcp-servers listing for Scout Packs

**Status:** DRAFT — needs GitHub auth to open. All content below is ready to paste.
**Target repo:** https://github.com/appcypher/awesome-mcp-servers
**File to edit:** `README.md`
**Section:** `## 🎯 Marketing`
**Placement:** append at the END of the Marketing bullet list (after the
`[Google Ads](https://github.com/gomarble-ai/google-ads-mcp-server)` line,
before the `<br />`).

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
 - <img src="https://img.icons8.com/?size=48&id=ui4CTPMMDCFh&format=png" height="14"/> [Google Ads](https://github.com/gomarble-ai/google-ads-mcp-server) - MCP server acting as an interface to the Google Ads, enabling programmatic access to Google Ads data and management features.
+- <img src="https://cdn.simpleicons.org/github/000000" height="14"/> [Scout Packs](https://github.com/tigerops-win/scout-packs) - Verified B2B lead packs for AI agents: 25/$9, 50/$15, 100/$25 behind an x402 paywall (USDC on Base). Every lead carries company, contact, title, published email, and source URL as machine-readable JSON. No account, no API key.
 <br />
```

## Notes
- Icon: generic GitHub mark (no brand icon exists for Scout Packs).
- If the maintainer asks for a stable (non-tunnel) endpoint URL, re-submit after the endpoint moves to permanent hosting.
- How to submit: fork appcypher/awesome-mcp-servers → edit README.md → open PR with the title/body above.
