# New micro-business specs (2026-10-06)

Two businesses, neither is "another endpoint". Both buildable in <1 day, sellable
within 48h of launch, zero marginal cost, no ad spend.

---

## 1. LaunchCheck — $19 instant site audits

**Concept.** One URL in, a scored 10-point audit out in 60 seconds: security headers
grade, DNS hygiene, SSL validity, tech-stack fingerprint, and deliverability of the
site's contact email — delivered as a branded shareable page plus PDF. Every data
primitive already exists as a live Scout Packs endpoint; this is a thin packaging
layer (input form → fan-out calls → scored report template → Stripe payment link).

**Buyer.** Indie hackers, solo founders, and small agencies in pre-launch week — people
who obsess over "is my site ready" and already pay for checklists and audits.

**Price.** $19 per report; $49/mo for 10 reports (agencies).

**Distribution.** (a) Outbound to the 987 leads already in the Scout Packs DB — every
one is a business with a website; the opener writes itself: "your site scored 42/100
on security headers — full 10-point report is $19." (b) One build-in-public X thread
showing real audits of well-known sites (no pitch, just the grades). (c) Indie
Hackers launch post framed as the build write-up.

**Why money this week.** Zero new data work — the endpoints are deployed and tested.
Build is a landing page + report template + Stripe link (one day). The lead DB is a
ready outbound list, and site owners open "your site has problems" emails at high
rates. First sale plausible within 48h of the first outbound batch.

---

## 2. ListScrub — stale email list cleaning

**Concept.** Upload a CSV of emails → per-address deliverability verdict (MX present,
SPF, disposable domain, role account, catch-all risk) → download a cleaned CSV with
only safe-to-send addresses, plus a bounce-risk score for the list. The
deliverability engine is already built, deployed, and priced at $0.03/call — this
product is CSV in/out wrapped around it with batch pricing.

**Buyer.** Lead-gen agencies, freelance SDRs, and newsletter operators sitting on
old, decaying lists. They already pay NeverBounce/MillionVerifier ~$8 per 1,000
emails, so the willingness to pay is proven and the switching pitch is price.

**Price.** $29 per 5,000 emails; $99/mo unlimited for agencies. Undercuts incumbents
~25% with zero marginal cost to us.

**Distribution.** (a) Email-first outbound to lead-gen agencies (the standing motion:
thousands of targets, plain-text, one recipient per email). (b) Agent-callable batch
endpoint listed on the same x402 marketplaces as Scout Packs — AI SDR agents are a
natural machine buyer for list cleaning. (c) A free "first 100 emails" tier that
converts on the results page.

**Why money this week.** The hard part (deliverability scoring) is done and live.
Build is a CSV upload page + batch runner + download (one day). Agencies buy this
as a commodity with a credit card the same day they discover it — no education
needed, just "cheaper than NeverBounce, results in minutes."
