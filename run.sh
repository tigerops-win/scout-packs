#!/usr/bin/env bash
# Run the Scout Packs endpoint on 127.0.0.1:8000 (tunnel provides public ingress).
set -euo pipefail
cd "$(dirname "$0")"
if [ -f .env ]; then set -a; . ./.env; set +a; fi
exec python3 server.py
