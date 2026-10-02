FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "mcp>=2"
COPY mcp/scout_packs_mcp.py ./mcp/
ENV BASE_URL=http://localhost:8000
CMD ["python", "mcp/scout_packs_mcp.py"]
