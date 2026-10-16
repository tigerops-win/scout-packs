# ACCEPTANCE — Composite Dossier Endpoint (`GET /dossier`)

Written BEFORE the implementation (2026-10-16), per the four-file contract.
The expected answers below are derived from the **existing** endpoints' code
and documented behaviour in `server.py` — the builder does not grade the
fusion against a formula the builder invented for the fusion. Where a value
comes from a live upstream and cannot be known in advance, it is marked
[CHECK] and the criterion is field presence/type only — never an invented
value.

Test implementation: `tests/test_dossier.py` (stdlib `unittest`, run with
`python3 -m unittest tests.test_dossier -v` from the repo root, or
`python3 tests/test_dossier.py`).

## Fixture 1 — invalid domain: `not-a-domain` (fully deterministic, no network)

All four source functions return early on an invalid domain, before any
network call — verified by reading them:

- `domain_intel()`: regex fails → returns `({"domain": "not-a-domain"},
  ["invalid_domain"])` — the intel dict has **no** `registration`/`dns` keys
  and, because the return happens before `intel["signals"]` is assigned, no
  `signals` key either. (This detail was confirmed against the actual output
  during the first local test run, 2026-10-16; the section stays verbatim —
  the flag surfaces in the dossier's top-level aggregated `signals` via the
  function's second return value.)
- `tech_stack()`: `_normalize_domain` invalid → result
  `{"domain": "not-a-domain", "technologies": [], "server_header": ""}`,
  flags dict with only `invalid_domain` active → signals `["invalid_domain"]`.
- `email_pattern()`: invalid → result `{"domain": "not-a-domain",
  "patterns": [], "mx_found": false, "catch_all_unknown": true}`,
  signals `["invalid_domain"]`.
- `ssl_check()`: invalid → result `{"domain": "not-a-domain", "valid": false,
  "issuer": "", "subject": "", "expires": "", "days_remaining": null,
  "tls_version": ""}`, signals `["invalid_domain"]`.

Expected fused output (exact equality):

```json
{
  "domain": "not-a-domain",
  "domain_intel": {"domain": "not-a-domain"},
  "tech_stack": {"domain": "not-a-domain", "technologies": [],
                 "server_header": "", "signals": ["invalid_domain"]},
  "email_pattern": {"domain": "not-a-domain", "patterns": [],
                    "mx_found": false, "catch_all_unknown": true,
                    "signals": ["invalid_domain"]},
  "ssl_check": {"domain": "not-a-domain", "valid": false, "issuer": "",
                "subject": "", "expires": "", "days_remaining": null,
                "tls_version": "", "signals": ["invalid_domain"]},
  "signals": ["invalid_domain"],
  "sections": ["domain-intel", "tech-stack", "email-pattern", "ssl-check"]
}
```

Pass criteria: exact dict equality (aggregated `signals` deduplicates the
four identical `invalid_domain` flags to one).

## Fixture 2 — valid domain: `example.com` (email-pattern values are exact)

`email_pattern()` in `server.py` returns a **hard-coded pattern list** for any
valid domain — these are known answers from the existing code, not from the
fusion:

Expected `email_pattern.patterns`, in exact order:

```
first@example.com
last@example.com
first.last@example.com
firstlast@example.com
first_last@example.com
first-last@example.com
f.last@example.com
flast@example.com
firstl@example.com
last.first@example.com
```

Also expected: `email_pattern.domain == "example.com"`,
`email_pattern.catch_all_unknown == true`,
`email_pattern.mx_found` is a boolean [CHECK: the value depends on the live
Cloudflare DoH MX answer for example.com at run time].

Expected for the other sections (presence/type only — values are live):

- `domain_intel.domain == "example.com"`; `domain_intel.registration` is an
  object; `domain_intel.dns` is an object with keys `nameservers`,
  `nameserver_count`, `a_records`, `a_record_count`, `mx_found`, `mx_hosts`;
  `domain_intel.signals` is a list. Registrar / `created` / `domain_age_days`
  values: [CHECK] live RDAP (rdap.org).
- `tech_stack.domain == "example.com"`; `technologies` is a list;
  `server_header` is a string. Detected technologies: [CHECK] live site.
  (In this sandbox the fetch may fail → `technologies == []` and
  `signals` contains `request_failed`; either outcome passes, the shape is
  the criterion.)
- `ssl_check.domain == "example.com"`; `valid` is a boolean; `issuer`,
  `subject`, `expires`, `tls_version` are strings; `days_remaining` is an
  integer or null. Values: [CHECK] live TLS handshake. Known sandbox caveat
  from the 2026-10-06 build notes: raw TLS from this sandbox is intercepted
  by the egress proxy, and `server.py` does not import `ssl`/`socket` at
  module level [CHECK — pre-existing, out of scope here], so
  `signals` containing `connection_failed` is an acceptable outcome locally;
  on Railway's direct egress the same code path is the one the existing
  `/ssl-check` endpoint uses.
- Top level: `domain == "example.com"`,
  `sections == ["domain-intel", "tech-stack", "email-pattern", "ssl-check"]`,
  top-level `signals` is a list containing every signal present in any
  section, with no duplicates.

## Fixture 3 — email-form input: `jane@example.com`

Derivation: `BAZAAR_DOMAININTEL` documents for `/domain-intel` that "An email
address also works; the domain part is used", and `domain_intel()` implements
it with `partition("@")[2]`. SPEC extends that cleaning to the whole dossier.

Expected (exact, deterministic):

- Top-level `domain == "example.com"`.
- `email_pattern.patterns` == the same 10 patterns as Fixture 2, in order.
- `email_pattern.domain == "example.com"` and
  `tech_stack.domain == "example.com"` and `ssl_check.domain == "example.com"`
  (the cleaned domain reaches every section, not the raw email string).
- No section's `signals` contains `invalid_domain`.

## Fixture 4 — fusion fidelity with documented canned outputs (no network)

The test stubs the four source functions with canned returns whose values are
copied from the endpoints' **documented examples in `server.py`** (the
`BAZAAR_*` `bazaar_ext(...)` output examples) and the functions' documented
return shapes:

- domain-intel canned: `registration {"registrar": "Example Registrar",
  "created": "2001-05-03"}`, `dns {"a": ["93.184.216.34"]}`,
  `domain_age_days 9280`, signals `["aged-domain"]`
  (from `BAZAAR_DOMAININTEL`'s output example).
- tech-stack canned: `technologies ["nginx", "wordpress"]`,
  `server_header "nginx"`, no active flags (from `BAZAAR_TECHSTACK`).
- email-pattern canned: `patterns ["{first}.{last}"]`, `mx_found true`,
  `catch_all_unknown false`, no active flags (from `BAZAAR_EMAILPATTERN`).
- ssl-check canned: `valid true`, `issuer "Let's Encrypt"`,
  `expires "2027-01-01"`, `days_remaining 85`, `tls_version "TLSv1.3"`,
  plus one active flag `expiring_soon_lt_30d = false`→ inactive, and the test
  additionally sets a second canned run where ssl flags include an active
  duplicate of a domain-intel flag to prove dedup [fixture-internal].

Expected: each dossier section equals the canned source result verbatim
(plus `signals` for the three sections whose handlers add it), and the
top-level `signals` equals the hand-written expected list in the test —
written out literally in `tests/test_dossier.py`, not computed by re-running
any aggregation code.

## Protocol / enumeration criteria (HTTP, local server)

1. Unpaid `GET /dossier?domain=example.com` → HTTP 402, body
   `error == "payment_required"`, `service == "dossier"`,
   `domain == "example.com"`, `price_usd == 0.05`, `currency == "USDC"`,
   `network == "eip155:8453"`, and a `how_to_pay` list whose second step
   names `POST /fulfill-dossier`.
2. The 402 carries a `PAYMENT-REQUIRED` header that base64-decodes to x402
   v2 terms (`x402Version == 2`) whose `accepts[0].amount == "50000"` and
   whose `extensions.bazaar` is present; and an `X-PAYMENT-REQUIRED` header
   that decodes to v1 terms with `accepts[0].maxAmountRequired == "50000"`.
3. Constants: `DOSSIER_PRICE_USD == 0.05` and `DOSSIER_AMOUNT == 50000`.
4. `GET /catalog` → `per_call_services` contains exactly one entry with
   `path == "/dossier"` and `price_usd == 0.05`.
5. `GET /.well-known/x402` → `resources` contains an entry whose `resource`
   URL ends with `/dossier` and whose amount is `"50000"`.
6. `GET /sample` → `pricing.per_call["/dossier"] == 0.05`.
7. `GET /openapi.json` → `paths` contains `/dossier` (GET, with a `domain`
   query parameter) and `/fulfill-dossier` (POST).
8. `POST /fulfill-dossier` with `{}` → HTTP 400 `missing_domain`; with a
   domain and a malformed tx hash → HTTP 402 `payment_not_verified`
   (detail `sales_paused…` when no receiving address is configured locally,
   or `bad_tx_hash` when one is — either proves the manual path is wired to
   `verify_dossier_payment`; the test accepts both, environment-dependent).
9. MCP: `mcp/scout_packs_mcp.py` defines a `dossier` tool routed through
   `_x402_instructions` with path `/dossier` and fulfill path
   `/fulfill-dossier` (verified by source inspection in the test — the MCP
   SDK is not installed in this environment [CHECK], so the module is not
   imported by the test).
10. No regressions: the four source endpoints still return 402 unpaid with
    their original amounts (`/domain-intel` 20000, the other three 10000).

## Explicitly NOT acceptance criteria (out of scope, local-only build)

- A real paid settlement (needs a buyer wallet + facilitator + the production
  receiving address) — [UNKNOWN] until Tiger deploys and a test purchase is
  made.
- Live values from RDAP / the target site / TLS for Fixtures 2–3 — [CHECK]
  as marked above.
- Registry/Bazaar ingestion of the new route — happens only after deploy.
