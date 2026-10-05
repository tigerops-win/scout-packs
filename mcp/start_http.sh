#!/bin/bash
# Start/restart the Scout Packs MCP server (Streamable HTTP) + its tunnel.
# Usage: ./start_http.sh [subdomain]
# Default subdomain keeps the current public URL stable:
#   https://scout-packs-production.up.railway.app/mcp
set -e
SUBDOMAIN="${1:-scoutpacks-mcp-bc34c6}"
cd ~/workspace/scout-packs
# stop any existing MCP http server (bracket trick avoids matching this script)
pkill -f "[h]ttp_server" 2>/dev/null || true
sleep 1
BASE_URL=https://scout-packs-production.up.railway.app MCP_HTTP_PORT=8001 \
  nohup ./mcp/.venv/bin/python mcp/http_server.py >> /tmp/mcp-http.log 2>&1 &
echo "mcp http server restarted (port 8001), log: /tmp/mcp-http.log"
echo "NOTE: the loca.lt tunnel path is DEAD LEGACY (retired 2026-10-02). Production is"
echo "https://scout-packs-production.up.railway.app. To expose the MCP server publicly,"
echo "route it through the production endpoint instead of a tunnel."
# tunnel block retired 2026-10-02 (localtunnel decommissioned; Railway is sole production)
# if ! pgrep -f "lt-proxy.js ${SUBDOMAIN} 8001" >/dev/null 2>&1; then
#   nohup node lt-proxy.js "$SUBDOMAIN" 8001 >> /tmp/mcp-tunnel.log 2>&1 &
#   echo "tunnel started: https://${SUBDOMAIN}.loca.lt -> 8001"
# else
#   echo "tunnel already running: https://${SUBDOMAIN}.loca.lt"
# fi
