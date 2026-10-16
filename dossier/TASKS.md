# TASKS — Composite Dossier Endpoint (`GET /dossier`)

Builder checklist. SPEC.md and ACCEPTANCE.md were written first (2026-10-16).

- [x] Explore repo patterns: per-call endpoint anatomy in `server.py`
      (constants + DESC, `BAZAAR_*` via `bazaar_ext()`, `verify_*_payment`,
      `*_payment_terms`, `*_paywall_body`, Handler `*_paywall` /
      `serve_paid_*` / `fulfill_*`), enumeration surfaces (`catalog()`,
      `well_known()`, `sample_record()`, `LLMS_TXT`, `openapi-draft.json`),
      and the MCP `_x402_instructions()` tool pattern.
- [x] Write SPEC.md (incl. $0.05 price proposal + rationale).
- [x] Write ACCEPTANCE.md with known-answer fixtures BEFORE building.
- [x] `server.py`: add `BAZAAR_DOSSIER` beside the other `BAZAAR_*` blocks.
- [x] `server.py`: add the dossier section (after the ssl-check block):
      `DOSSIER_PRICE_USD` / `DOSSIER_AMOUNT` / `DOSSIER_DESC`,
      `dossier(domain)` fusion function, `verify_dossier_payment`,
      `dossier_payment_terms`, `dossier_paywall_body`.
- [x] `server.py`: Handler routes — `GET /dossier`, `POST /fulfill-dossier`;
      Handler methods `dossier_paywall`, `serve_paid_dossier`,
      `fulfill_dossier`.
- [x] `server.py`: enumeration — `catalog()`, `well_known()`,
      `sample_record()` pricing, `LLMS_TXT`.
- [x] `openapi-draft.json`: add `/dossier` and `/fulfill-dossier` paths
      mirroring `/ssl-check` + `/fulfill-ssl-check`.
- [x] `mcp/scout_packs_mcp.py`: add `dossier` MCP tool via
      `_x402_instructions`.
- [x] `tests/test_dossier.py`: implement every ACCEPTANCE.md criterion.
- [x] Run tests locally; iterate until green; record results in HANDOFF.md.
- [x] HANDOFF.md: test evidence, exact deploy steps for Tiger, rollback note.
- [x] Summary brief at `~/workspace/ai-crew/briefs/dossier-endpoint-build-2026-10-16.md`.
- [x] STOP: no commit (or branch-only), no push, no deploy, no listings.
