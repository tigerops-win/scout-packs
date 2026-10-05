FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "mcp>=2"
COPY server.py .
COPY openapi-draft.json .
COPY assets/ ./assets/
COPY packs/ ./packs/
COPY mcp/ ./mcp/
COPY skills/ ./skills/
# One dyno serves both the x402 HTTP API and the MCP streamable-HTTP endpoint:
# the MCP server listens on 127.0.0.1:8001 and server.py reverse-proxies /mcp
# to it (MCP_PROXY_PORT). Railway injects $PORT for the public API.
CMD ["sh", "-c", "BASE_URL=http://127.0.0.1:${PORT:-8000} MCP_HTTP_PORT=8001 python mcp/http_server.py & MCP_PROXY_PORT=8001 python server.py"]
