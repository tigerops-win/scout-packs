# Scout Packs — CDP Bazaar Discovery Extension: Status & Implementation Spec

Builder audit, 2026-10-12 (evening). Live service:
https://scout-packs-production.up.railway.app

## Verdict

**The Bazaar discovery extension is already implemented and live — spec-only
for the remaining gap.** What is missing is not response metadata; it is
settlement through the CDP facilitator, which is blocked on a Conor decision
(CDP account + API keys + facilitator switch). Do NOT change the 402 response
shape during the PayAPI verification window (~next 24h): the current shape is
the one CDP's validate endpoint already passed on 2026-10-08.

## What is already live (verified 2026-10-12 against production)

- Wire format is the current `@x402/extensions` v2 shape from
  `declareDiscoveryExtension()`: `extensions.bazaar = {info, schema}` — NOT
  the old `{discoverable, inputSchema, outputSchema}` shape (commits
  `ac5bf1e`, `541d856`, 2026-10-08).
- Present in three places on every paid route, all 13 per-call services
  (/lookup, /deliverability, /packsize, /domain-intel, /tech-stack,
  /email-pattern, /ssl-check, /headers, /dns, /repo-health, /subdomains,
  /contact-page, /mail-provider) plus /packs/{25,50,100}:
  1. top level of the v2 PaymentRequired object (body `x402.extensions.bazaar`
     and the decoded `PAYMENT-REQUIRED` header),
  2. inside `accepts[0].extensions.bazaar` (kept for older consumers),
  3. `/.well-known/x402` — all 16 resources carry `info` + `schema`.
- `info.input = {type: "http", method: "GET", queryParams: {<example values>}}`,
  `info.output = {type: "json", example: {<realistic paid response>}}`;
  `schema` is a JSON Schema (draft 2020-12) whose `properties.input` validates
  the info input. Code: `bazaar_ext()` + 14 `BAZAAR_*` constants in server.py.
- All 16 route descriptions are ≤500 chars (max 287) — inside CDP's limit.
- Unpaid probes of all 13 routes + 3 packs on 2026-10-12: HTTP 402, amounts
  match /catalog exactly, bazaar `info`+`schema` present at both levels.

## Why we are still not indexed in Coinbase Bazaar / agentic.market

Bazaar cataloging is a facilitator-side action, not a crawl:

1. **Settlement, not verification, triggers cataloging.** The facilitator
   extracts the discovery declaration from a *settled* payment and indexes
   the resource. A 402 response alone (or a verify call) does not list us.
2. **Our facilitator is not CDP.** `server.py` settles through
   `FACILITATOR_URL`, default `https://facilitator.payai.network`
   (env override `X402_FACILITATOR_URL`). PayAI settlements do not feed
   Coinbase's catalog. Indexing requires mainnet settlement through the
   **CDP facilitator**, which requires a CDP account and API keys from
   portal.cdp.coinbase.com.
3. **The declaration must survive to the facilitator.** CDP extracts
   `extensions.bazaar` from the payment payload / requirements it receives.
   Our settle path (`settle_x402_payment()`) posts
   `{x402Version, paymentPayload, paymentHeader, paymentRequirements}` where
   `paymentRequirements` is built by `x402_requirements()` — which carries
   **no extensions**. Indexing therefore depends on the buyer's client
   echoing the top-level `extensions` into its payment payload (SDK clients
   do; hand-rolled clients may not).

## Remaining work (in dependency order)

### 1. CDP facilitator switch — BLOCKED ON CONOR (decision + account)
- Create CDP account / API keys (portal.cdp.coinbase.com) — account signup is
  a human/identity step; keys go to Secure Vault, never in repo.
- Set Railway env `X402_FACILITATOR_URL` to the CDP facilitator endpoint and
  confirm CDP verify/settle request/response compatibility with
  `settle_x402_payment()` (CDP expects the same /verify + /settle shape, plus
  auth headers from the API keys — `post_json()` needs an optional headers
  param; ~20 lines).
- Risk: switching facilitators changes the settlement path for ALL routes,
  including PayAPI's pending verification calls. **Do not switch until the
  PayAPI listings are live or the Oct 16 kill gate has resolved.**
- Effort once keys exist: ~1–2h including a staged test.

### 2. Forward the bazaar declaration in settle/verify calls — small, additive
- In `settle_x402_payment()`, attach the route's bazaar extension to the
  posted body so CDP receives it even when the client drops it: add
  `extensions: {bazaar: <route's BAZAAR_*>}` alongside `paymentRequirements`
  (the caller knows the route; thread the constant through the
  `serve_paid_*` functions — 14 call sites, mechanical).
- Effort: ~1h + local facilitator-mock test. Zero change to any 402 response,
  so it cannot break PayAPI verification. Safe to do before step 1, useless
  until step 1 lands.

### 3. Optional resource metadata — small, additive, defer
- Add `serviceName: "Scout Packs"`, `tags: [...]`, `iconUrl` (live /logo.png)
  to the v2 `resource` object in the 14 `*_payment_terms()` functions and
  `well_known()`. Improves listing presentation in the Bazaar UI; not
  required for indexing.
- Effort: ~30 min. Defer until after the PayAPI window — it touches every
  402 body for cosmetic gain.

### 4. First CDP-settled payment — BLOCKED (same decision as step 1)
- After steps 1–2, indexing happens on the first real payment settled via
  CDP. Self-pay verification is out of scope / not authorized; this needs a
  genuine buyer call or an explicit Conor decision.

## What NOT to do
- Do not move the extension out of `accepts[0]` — dual placement is harmless
  and older consumers read it there.
- Do not revert to the old `{discoverable, inputSchema, outputSchema}` shape.
- Do not implement any payment, facilitator account, or CDP signup in the
  Builder lane.
