FROM python:3.12-slim
WORKDIR /app
COPY server.py .
COPY openapi-draft.json .
COPY assets/ ./assets/
COPY packs/ ./packs/
CMD ["python3", "server.py"]
