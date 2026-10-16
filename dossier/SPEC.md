# SPEC — Composite Dossier Endpoint (`GET /dossier`)

Feature directory: `dossier/` (this folder). Implementation: `server.py` (+
`openapi-draft.json`, `mcp/scout_packs_mcp.py`). Status: LOCAL ONLY — built and
tested locally, NOT deployed, NOT published, 2026-10-16.

## What

One paid x402 call that fuses the four existing domain signals into a single
response for one domain:

| Section key | Source function (existing) | Source endpoint | Price if bought alone |
|---|---|---|---|
| `domain_intel` | `domain_intel(domain)` | `GET /domain-intel` | $0.02 |
| `tech_stack` | `tech_stack(domain)` | `GET /tech-stack` | $0.01 |
| `email_pattern` | `email_pattern(domain)` | `GET /email-pattern` | $0.01 |
| `ssl_check` | `ssl_check(domain)` | `GET /ssl-check` | $0.01 |

Each section is the **verbatim** result of its source function, plus that
section's `signals` exactly as the corresponding paid handler emits them
(source function result spread + `signals`). `domain_intel`'s result carries
its own `signals` list (except on its invalid-domain early return, where the
dict has no `signals` key — the section is kept verbatim either way, and the
flag still reaches the dossier's aggregated list via the function's second
return value); the other three sections get
`signals = _active_flags(flags)` — the same helper the existing handlers use.

Top level of the paid response mirrors every other per-call endpoint:
`receipt:"ok"`, `service:"dossier"`, `tx_hash`, `price_usd`, the fused body,
`checked_at` (UTC, `%Y-%m-%dT%H:%M:%SZ`), and a `note`.

Fused body shape:

```json
{
  "domain": "example.com",
  "domain_intel":  { "...verbatim domain_intel() result, incl. signals..." },
  "tech_stack":    { "...verbatim tech_stack() result...", "signals": ["..."] },
  "email_pattern": { "...verbatim email_pattern() result...", "signals": ["..."] },
  "ssl_check":     { "...verbatim ssl_check() result...", "signals": ["..."] },
  "signals": ["...aggregated..."],
  "sections": ["domain-intel", "tech-stack", "email-pattern", "ssl-check"]
}
```

Aggregated `signals` rule (the only new logic in the fusion): concatenate, in
this fixed order — domain-intel flags (in the order `domain_intel()` returns
them), then tech-stack, email-pattern, and ssl-check active flags (each sorted,
as `_active_flags()` returns) — and drop duplicates, keeping first occurrence.
No other derived/cross-signal logic in v1. That restraint is deliberate: the
aggregated list is mechanically checkable against the four sections in the
same response.

Input normalisation: the raw `domain` argument is cleaned once, the same way
`domain_intel()` cleans it (strip, lowercase, if it contains `@` take the part
after the last `@`-partition used by `domain_intel` — i.e. `partition("@")[2]`),
and the cleaned domain is passed to all four source functions. This matches the
documented behaviour of `/domain-intel` ("An email address also works; the
domain part is used" — `BAZAAR_DOMAININTEL` in `server.py`) and extends it
uniformly to the other three sections.

## Why

A buyer vetting one company/domain today needs all four signals and must:

1. Make 4 separate unpaid requests (4 × HTTP 402 challenges),
2. Sign 4 separate EIP-3009 authorizations,
3. Wait on 4 separate facilitator verify+settle round-trips,
4. Make 4 paid retries, and stitch 4 response envelopes together client-side.

`/dossier` collapses that to 1 challenge, 1 authorization, 1 settlement, 1
retry. The buyer saves 3 payment round-trips and all client-side stitching,
and gets one `checked_at` timestamp for the whole picture instead of four
snapshots taken at different moments. For agent buyers — the actual market —
round-trips and settlement latency are the real cost of a penny endpoint; the
data price is not.

Seller side: one $0.05 call instead of four $0.01–$0.02 calls is a larger
basket per settlement, one facilitator settlement instead of four
[CHECK: facilitator per-settlement fee/latency in production is not measured
in this repo], and a cleaner telemetry record (one dossier sale = one fully
vetted domain, comparable across buyers).

## Price proposal: $0.05 USDC per call (`DOSSIER_AMOUNT = 50_000`)

Rationale:

- Sum of parts: $0.02 + $0.01 + $0.01 + $0.01 = **$0.05**. The composite is
  priced at exactly the sum of its parts — no fusion premium, no bundle
  discount.
- Above the penny tier: every existing per-call service is $0.01–$0.03
  (`/deliverability` is the current ceiling at $0.03). $0.05 makes `/dossier`
  the highest-priced per-call service, which is correct for the only product
  that returns four services' output in one response.
- Why no premium above $0.05: the saved round-trips (3 settlements, 3
  challenges, stitching) are already the buyer's reason to choose the
  composite over the parts at price parity. Charging $0.06 (sum + $0.01
  convenience premium, considered and rejected for v1) would give a rational
  buyer a reason to just buy the parts. Price parity makes the composite the
  strictly dominant choice for anyone who wants ≥3 of the 4 signals, which is
  what grows dossier volume and telemetry.
- Why no discount below $0.05: marginal cost is still zero (same free
  upstreams), but discounting would cannibalise the proven penny endpoints
  and undercut their listed prices on every registry/catalog surface where
  both appear. Parity keeps the whole price ladder coherent:
  $0.01 single signal → $0.02 domain-intel/subdomains/contact-page →
  $0.03 deliverability → $0.05 full dossier.
- Kill/adjust note (for Tiger, post-launch, NOT part of this build): if
  dossier volume cannibalises the four source endpoints without growing total
  per-domain revenue within the first review window, revisit the $0.06 premium.

## Wiring (mirrors the existing endpoints exactly)

- Constants: `DOSSIER_PRICE_USD`, `DOSSIER_AMOUNT`, `DOSSIER_DESC`
  (description ends with a "Use when…" line, per the 2026-10-14 Bazaar fix
  applied to all 16 existing descriptions).
- `BAZAAR_DOSSIER = bazaar_ext(...)` built with the same helper as the other
  `BAZAAR_*` declarations.
- `verify_dossier_payment(tx_hash)` — same manual-tx verification shape as
  `verify_sslcheck_payment()` / `verify_domainintel_payment()`, amount
  `DOSSIER_AMOUNT`.
- `dossier_payment_terms(handler, domain)` / `dossier_paywall_body(handler, domain)`
  — same shapes as `sslcheck_*` equivalents, `service:"dossier"`.
- Handler: `dossier_paywall` (402 before validation, `PAYMENT-REQUIRED` v2 +
  `X-PAYMENT-REQUIRED` v1 headers), `serve_paid_dossier` (facilitator settle
  via `x402_requirements()` / `settle_x402_payment()`, `log_sale("dossier", …)`,
  settlement response header), `fulfill_dossier` for
  `POST /fulfill-dossier {"tx_hash":"0x…","domain":"…"}`.
- Enumeration, the way other endpoints are added: `catalog()` per-call list,
  `well_known()` resources tuple, `sample_record()` per-call pricing,
  `LLMS_TXT` services list, a `/dossier` (+ `/fulfill-dossier`) path in
  `openapi-draft.json`, and an MCP tool `dossier` in
  `mcp/scout_packs_mcp.py` via the shared `_x402_instructions()` helper.
- Errors mirror the neighbours: unpaid → 402 `payment_required`; bad/missing
  domain on the manual path → 400 `missing_domain`; unverified manual tx →
  402 `payment_not_verified` with `how_to_pay`; invalid domain on the paid
  path is NOT a 400 — the four source functions report it via `signals`
  (`invalid_domain`), exactly as they do on their own endpoints.

## Non-goals / out of scope for this build

- No deploy, no push, no registry/listing submission, no production touch.
- No new upstreams, no caching, no parallel fan-out (v1 calls the four source
  functions sequentially, like the codebase's existing style; total latency is
  the sum of the four — [CHECK] live latency unmeasured).
- No changes to the four source endpoints or their prices.
- No free/demo variant of `/dossier`.
