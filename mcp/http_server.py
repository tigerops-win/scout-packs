#!/usr/bin/env python3
"""Scout Packs MCP server over Streamable HTTP (for Smithery registration).

Same server, same tools (list_packs, buy_pack), same behavior as
scout_packs_mcp.py — only the transport changes from stdio to Streamable
HTTP. Stateless mode: each request gets a fresh session, which is what
Smithery and most registries expect.

Run:
    BASE_URL=https://scout-packs-production.up.railway.app MCP_HTTP_PORT=8001 \
        ~/workspace/scout-packs/mcp/.venv/bin/python \
        ~/workspace/scout-packs/mcp/http_server.py

Endpoint: POST http://127.0.0.1:8001/mcp
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import scout_packs_mcp  # noqa: E402
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402

PORT = int(os.environ.get("MCP_HTTP_PORT", "8001"))

# The server binds 127.0.0.1 and is only reachable through the public
# tunnel; DNS-rebinding protection would reject the tunnel's Host header,
# so it is disabled (no browser clients use this endpoint).
_NO_REBIND = TransportSecuritySettings(enable_dns_rebinding_protection=False)

if __name__ == "__main__":
    print(f"scout-packs-mcp streamable-http on 127.0.0.1:{PORT}/mcp  "
          f"BASE_URL={scout_packs_mcp.BASE_URL}", flush=True)
    scout_packs_mcp.mcp.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=PORT,
        streamable_http_path="/mcp",
        stateless_http=True,
        transport_security=_NO_REBIND,
    )
