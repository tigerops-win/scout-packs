#!/usr/bin/env python3
"""Scout Packs — Tiger Operations (Agent Data Supply Company).

A minimal x402-paywalled lead-pack endpoint. Python stdlib only.

Packs: 25/50/100 leads at $0.01 flat each (demand probe, 2026-10-04),
plus a $0.01/lookup per-lead enrichment endpoint. Paid in USDC on Base (eip155:8453).
- GET /packs/25   -> the ready-to-deliver 25-lead pack (402 paywall, x402 v1+v2 headers)
- GET /packs/50, /packs/100 -> 402 paywall; fulfilled as made-to-order within 24h
- POST /fulfill {tx_hash, pack, deliver_to?} -> on-chain payment verification
  (Base USDC transfer to the configured receiving address, via Blockscout's
  free API), then delivery for pack 25 or a 24h order receipt for 50/100.

Receiving address is a config placeholder: SCOUTPACKS_RECEIVING_ADDRESS.
While unset (or the zero address), /packs/* report sales_enabled=false and
/fulfill refuses. No agent in this stack holds private keys.

Run:  SCOUTPACKS_RECEIVING_ADDRESS=0x... ./run.sh
"""

import base64
import hashlib
import html as html_lib
import json
import os
import re
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, unquote_plus

# ---------------------------------------------------------------- config
PORT = int(os.environ.get("PORT", "8000"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RECEIVING = os.environ.get("SCOUTPACKS_RECEIVING_ADDRESS", "").strip().lower()
ZERO = "0x0000000000000000000000000000000000000000"
SALES_ENABLED = bool(RECEIVING) and RECEIVING != ZERO and bool(re.fullmatch(r"0x[0-9a-f]{40}", RECEIVING or ""))
PUBLIC_BASE = os.environ.get("SCOUTPACKS_PUBLIC_BASE", "")  # e.g. https://abc.trycloudflare.com

USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # Base native USDC, 6 decimals
NETWORK = "eip155:8453"
BLOCKSCOUT = "https://base.blockscout.com/api/v2"
REDEEMED_PATH = os.path.join(BASE_DIR, "data", "redeemed.json")
VERIFY_PATH = os.path.join(BASE_DIR, "data", "verify.txt")  # 402index domain-verification hash

# Demand probe (Analyst 10-03 reprice verdict, staged 2026-10-04): all packs
# $0.01 flat. Margin inversion vs Scout COGS is acknowledged — probe, not a
# business model. Kill gate: >=3 paid lookups from >=2 wallets in 7 days.
PACKS = {
    "25":  {"count": 25,  "price_usd": 0.01, "amount": 10_000, "eta": "instant"},
    "50":  {"count": 50,  "price_usd": 0.01, "amount": 10_000, "eta": "within 24 hours (assembled on demand)"},
    "100": {"count": 100, "price_usd": 0.01, "amount": 10_000, "eta": "within 24 hours (assembled on demand)"},
}

# Per-lead enrichment lookup (Analyst hunt #3 pivot, 2026-10-02; repriced
# 2026-10-04 per Analyst demand verdict to $0.01 — the proven bestseller's
# price (x402.agentutility.ai, 397 calls/30d). Margin inversion acknowledged.)
LOOKUP_PRICE_USD = 0.01
LOOKUP_AMOUNT = 10_000  # $0.01 in 6-decimal USDC
# Keyword-tuned for Agent402 router text-match: lead / enrichment / b2b /
# contact lookup / email.
LOOKUP_DESC = ("B2B lead enrichment — contact lookup: enrich any company with a verified "
               "business email + source URL. One lead lookup per call. Tiger Operations.")

# Email deliverability score (2026-10-05: model-consensus build #1 — every
# sender agent needs it; no deliverability listing on PayAPI). $0.03/lookup.
DELIVERABILITY_PRICE_USD = 0.03
DELIVERABILITY_AMOUNT = 30_000  # $0.03 in 6-decimal USDC
DELIVERABILITY_DESC = ("Email deliverability score — MX/SPF/DMARC checks, disposable-domain "
                       "and role-account detection, bounce-risk score 0-100 with send/caution/"
                       "do_not_send verdict. One email or domain per call. Tiger Operations.")

# Pack-size identity resolver (2026-10-05: idea #23 from the 100-idea blueprint,
# priority 3/100 — the parser/rules core as a pure x402 data endpoint, no
# customer data needed). $0.02/call.
PACKSIZE_PRICE_USD = 0.02
PACKSIZE_AMOUNT = 20_000  # $0.02 in 6-decimal USDC
PACKSIZE_DESC = ("Pack-size identity resolver — parse a product title into pack count, "
                 "unit size, and normalized totals for comparable unit pricing. "
                 "Deterministic, no customer data needed. Tiger Operations.")

# CDP Bazaar discovery extension (docs.cdp.coinbase.com/x402/bazaar; declared
# on the wire inside each accepts[] entry per the x402 v2 bazaar schema).
# Caveats: actual catalog indexing happens only when a payment settles through
# the CDP facilitator (our fulfill flow is manual/on-chain today), and CDP
# indexing is subject to the known bug for non-CDP-registered payee EOAs
# (x402-foundation/x402#2112). Declared now so the first CDP-settled payment
# fans out to Bazaar/Onyx/Agentic.market automatically.
def bazaar_ext(input_schema, output_schema):
    return {
        "discoverable": True,
        "inputSchema": input_schema,
        "outputSchema": output_schema,
    }

BAZAAR_LOOKUP = bazaar_ext(
    {"queryParams": {
        "query": {"type": "string",
                  "description": "Company name or domain to enrich (e.g. 'Acme Corp' or 'acme.com')",
                  "required": True}}},
    {"type": "object", "properties": {
        "lead": {"type": "object"},
        "receipt": {"type": "string"},
        "verified_at": {"type": "string"}}},
)

BAZAAR_DELIVERABILITY = bazaar_ext(
    {"queryParams": {
        "email": {"type": "string",
                  "description": "Email address to score (e.g. 'jane@acme.com'). Use email OR domain, not both.",
                  "required": False},
        "domain": {"type": "string",
                   "description": "Domain to score (e.g. 'acme.com'). Use email OR domain, not both.",
                   "required": False}}},
    {"type": "object", "properties": {
        "score": {"type": "number"},
        "verdict": {"type": "string"},
        "flags": {"type": "array"},
        "checks": {"type": "object"},
        "receipt": {"type": "string"}}},
)

BAZAAR_PACKSIZE = bazaar_ext(
    {"queryParams": {
        "title": {"type": "string",
                  "description": "Product title to parse (e.g. 'Coca-Cola 12-pack 12oz cans').",
                  "required": True},
        "price": {"type": "string",
                  "description": "Optional package price (e.g. '8.99') to compute price per normalized unit.",
                  "required": False}}},
    {"type": "object", "properties": {
        "pack_count": {"type": "number"},
        "unit_size": {"type": "string"},
        "total_normalized": {"type": "string"},
        "unit_price": {"type": "string"},
        "confidence": {"type": "string"},
        "receipt": {"type": "string"}}},
)

BAZAAR_PACK = bazaar_ext(
    {},
    {"type": "object", "properties": {
        "pack": {"type": "string"},
        "leads": {"type": "array"},
        "receipt": {"type": "string"}}},
)

BAZAAR_DOMAININTEL = bazaar_ext(
    {"queryParams": {
        "domain": {"type": "string",
                   "description": "Domain to investigate (e.g. 'acme.com'). An email address also works; the domain part is used.",
                   "required": True}}},
    {"type": "object", "properties": {
        "registration": {"type": "object"},
        "dns": {"type": "object"},
        "domain_age_days": {"type": "number"},
        "signals": {"type": "array"},
        "receipt": {"type": "string"}}},
)

with open(os.path.join(BASE_DIR, "packs", "scout-pack-25.json")) as f:
    PACK_25 = json.load(f)

with open(os.path.join(BASE_DIR, "openapi-draft.json")) as f:
    OPENAPI_DOC = json.load(f)  # served verbatim at GET /openapi.json

SKILL_MD_PATH = os.path.join(BASE_DIR, "skills", "scout-packs-lead-lookup", "SKILL.md")
try:
    with open(SKILL_MD_PATH) as f:
        SKILL_MD = f.read()  # served verbatim at GET /skill.md
except OSError:
    SKILL_MD = ""

# Durable HTTPS MCP endpoint: when MCP_PROXY_PORT is set (e.g. "8001"), the
# sibling MCP streamable-HTTP server (mcp/http_server.py, stateless) runs on
# 127.0.0.1:<port>/mcp and this server reverse-proxies /mcp to it — so one
# Railway service exposes both the x402 HTTP API and the MCP endpoint on the
# same durable HTTPS domain (AgentShare precondition: mcp_url must be durable
# HTTPS; stdio-only is rejected). Unset = /mcp 404s (default local dev).
MCP_PROXY_PORT = os.environ.get("MCP_PROXY_PORT", "").strip()

TX_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")

# --------------------------------------------------------------- helpers
def load_redeemed():
    try:
        with open(REDEEMED_PATH) as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_redeemed(hashes):
    tmp = REDEEMED_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(sorted(hashes), f)
    os.replace(tmp, REDEEMED_PATH)

def fetch_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "scout-packs/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)

def post_json(url, obj, timeout=25):
    """POST JSON; returns the decoded body. HTTP error bodies that decode as
    JSON are returned as-is (facilitators report verdicts like isValid:false
    with 4xx), so callers see the verdict instead of an exception."""
    data = json.dumps(obj).encode()
    req = urllib.request.Request(url, data=data, headers={
        "User-Agent": "scout-packs/1.0",
        "Content-Type": "application/json",
        "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return json.load(e)
        except Exception:
            raise

# ---------------------------------------------------------------- standard x402 settlement
# Signed-payment flow (what real x402 clients speak): the buyer signs an
# EIP-3009 transfer authorization and retries with X-PAYMENT (v1) or
# PAYMENT-SIGNATURE (v2). We verify + settle through a public facilitator —
# no private keys on this server; USDC settles straight to RECEIVING.
# Default: the PayAI facilitator (free tier, no key, Base mainnet capable).
# Override with X402_FACILITATOR_URL to point at CDP or a self-hosted one.
FACILITATOR_URL = os.environ.get("X402_FACILITATOR_URL", "https://facilitator.payai.network").strip().rstrip("/")
# Network label per protocol version (v1 uses short names, v2 uses CAIP-2).
NETWORK_V1 = "base"
NETWORK_V2 = NETWORK  # "eip155:8453"
X402_SETTLED_PATH = os.path.join(BASE_DIR, "data", "x402_settled.json")

def load_settled():
    try:
        with open(X402_SETTLED_PATH) as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}

def save_settled(d):
    tmp = X402_SETTLED_PATH + ".tmp"
    os.makedirs(os.path.dirname(X402_SETTLED_PATH), exist_ok=True)
    with open(tmp, "w") as f:
        json.dump(d, f)
    os.replace(tmp, X402_SETTLED_PATH)

def x402_incoming_payment(headers):
    """Return (version, payment_b64) from X-PAYMENT (v1) or PAYMENT-SIGNATURE (v2)."""
    v1 = headers.get("X-PAYMENT")
    if v1 and v1.strip():
        return 1, v1.strip()
    v2 = headers.get("PAYMENT-SIGNATURE")
    if v2 and v2.strip():
        return 2, v2.strip()
    return None, None

def x402_requirements(version, resource_url, amount, description):
    """paymentRequirements for the facilitator, shaped per protocol version.

    v1: maxAmountRequired + short network name + string resource.
    v2: amount + CAIP-2 network (resource lives top-level in the 402; the
    facilitator reference omits it here)."""
    req = {
        "scheme": "exact",
        "asset": USDC_BASE,
        "payTo": RECEIVING,
        "maxTimeoutSeconds": 300,
        "extra": {"name": "USD Coin", "version": "2"},
    }
    if version == 2:
        req["network"] = NETWORK_V2
        req["amount"] = str(amount)
    else:
        req["network"] = NETWORK_V1
        req["maxAmountRequired"] = str(amount)
        req["resource"] = resource_url
    return req

def payer_from_x402_payload(payload):
    try:
        return str(payload["payload"]["authorization"]["from"]).lower()
    except Exception:
        return ""

def settle_x402_payment(version, payment_b64, requirements):
    """Verify + settle a signed x402 payment via the facilitator.

    Returns (ok, info). On success info = {"tx_hash", "payer", "replay"}.
    Replays of an already-settled payment re-serve without re-settling.
    """
    try:
        payload = json.loads(base64.b64decode(payment_b64).decode())
    except Exception:
        return False, "bad_payment_encoding"
    digest = hashlib.sha256(payment_b64.encode()).hexdigest()
    settled = load_settled()
    if digest in settled:
        rec = settled[digest]
        return True, {"tx_hash": rec.get("tx_hash", ""), "payer": rec.get("payer", ""),
                      "replay": True}
    body = {"x402Version": version, "paymentPayload": payload,
            "paymentHeader": payment_b64,
            "paymentRequirements": requirements}
    try:
        v = post_json(FACILITATOR_URL + "/verify", body)
    except Exception:
        return False, "facilitator_unreachable"
    if not isinstance(v, dict) or not v.get("isValid"):
        reason = (v or {}).get("invalidReason", "unknown")
        return False, "payment_invalid:%s" % reason
    try:
        s = post_json(FACILITATOR_URL + "/settle", body)
    except Exception:
        return False, "facilitator_unreachable"
    if not isinstance(s, dict) or not s.get("success"):
        reason = (s or {}).get("errorReason", "unknown")
        return False, "settlement_failed:%s" % reason
    tx_hash = str(s.get("transaction") or s.get("txID") or s.get("txHash") or "")
    payer = payer_from_x402_payload(payload)
    settled[digest] = {"tx_hash": tx_hash, "payer": payer,
                       "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    save_settled(settled)
    return True, {"tx_hash": tx_hash, "payer": payer, "replay": False}

def x402_settlement_response_header(version, tx_hash, payer):
    """Value for PAYMENT-RESPONSE (v2) / X-PAYMENT-RESPONSE (v1)."""
    resp = {"success": True, "transaction": tx_hash, "network": NETWORK,
            "payer": payer}
    return base64.b64encode(json.dumps(resp).encode()).decode()

def log_sale(kind, record):
    try:
        path = os.path.join(BASE_DIR, "data", kind + "_sales.jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        record = dict(record)
        record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with open(path, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass

def blockscout_tx(tx_hash):
    return fetch_json(f"{BLOCKSCOUT}/transactions/{tx_hash}")

def verify_payment(tx_hash, pack_size):
    """Returns (ok, detail). All failure reasons are plain strings."""
    if not SALES_ENABLED:
        return False, "sales_paused: receiving address not configured"
    if not TX_RE.match(tx_hash or ""):
        return False, "bad_tx_hash"
    tx_hash = tx_hash.lower()
    redeemed = load_redeemed()
    if tx_hash in redeemed:
        return False, "already_redeemed"
    try:
        tx = blockscout_tx(tx_hash)
    except urllib.error.HTTPError as e:
        return (False, "tx_not_found") if e.code == 404 else (False, f"chain_lookup_failed:{e.code}")
    except Exception:
        return False, "chain_lookup_failed"
    if str(tx.get("status", "")).lower() != "ok":
        return False, "tx_not_successful"
    # replay window: tx must be recent (30 days). Blockscout v2 puts the
    # ISO timestamp at top level ("timestamp"); transfers carry block_number.
    try:
        ts_raw = (tx.get("timestamp") or "").replace("Z", "+00:00")
        from datetime import datetime, timezone
        ts = datetime.fromisoformat(ts_raw).timestamp()
        if time.time() - ts > 30 * 86400:
            return False, "tx_too_old"
    except Exception:
        pass
    want = PACKS[pack_size]["amount"]
    for t in tx.get("token_transfers", []) or []:
        try:
            tok_obj = t.get("token") or {}
            tok = (tok_obj.get("address_hash") or tok_obj.get("address") or "").lower()
            to = (t.get("to") or {}).get("hash", "").lower()
            val = int((t.get("total") or {}).get("value", 0))
        except (ValueError, TypeError):
            continue
        if tok == USDC_BASE.lower() and to == RECEIVING and val >= want:
            redeemed.add(tx_hash)
            save_redeemed(redeemed)
            return True, "verified"
    return False, "no_matching_usdc_transfer"

def verify_lookup_payment(tx_hash):
    """Returns (ok, detail) for $0.01 lookup payments."""
    if not SALES_ENABLED:
        return False, "sales_paused: receiving address not configured"
    if not TX_RE.match(tx_hash or ""):
        return False, "bad_tx_hash"
    tx_hash = tx_hash.lower()
    redeemed = load_redeemed()
    if tx_hash in redeemed:
        return False, "already_redeemed"
    try:
        tx = blockscout_tx(tx_hash)
    except urllib.error.HTTPError as e:
        return (False, "tx_not_found") if e.code == 404 else (False, f"chain_lookup_failed:{e.code}")
    except Exception:
        return False, "chain_lookup_failed"
    if str(tx.get("status", "")).lower() != "ok":
        return False, "tx_not_successful"
    try:
        ts_raw = (tx.get("timestamp") or "").replace("Z", "+00:00")
        from datetime import datetime, timezone
        ts = datetime.fromisoformat(ts_raw).timestamp()
        if time.time() - ts > 30 * 86400:
            return False, "tx_too_old"
    except Exception:
        pass
    for t in tx.get("token_transfers", []) or []:
        try:
            tok_obj = t.get("token") or {}
            tok = (tok_obj.get("address_hash") or tok_obj.get("address") or "").lower()
            to = (t.get("to") or {}).get("hash", "").lower()
            val = int((t.get("total") or {}).get("value", 0))
            sender = (t.get("from") or {}).get("hash", "").lower()
        except (ValueError, TypeError):
            continue
        if tok == USDC_BASE.lower() and to == RECEIVING and val >= LOOKUP_AMOUNT:
            redeemed.add(tx_hash)
            save_redeemed(redeemed)
            return True, {"sender": sender, "value": val}
    return False, "no_matching_usdc_transfer"


def mask_email(e):
    local, _, dom = (e or "").partition("@")
    return (local[:3] + "***@" + dom) if dom else "***"


def preview_pack():
    # preview-500 fix (2026-10-04): every field is read with .get() and a
    # sane default. A single lead record missing a key previously raised
    # KeyError -> 500 {"error":"internal"} on /packs/{25,50,100}/preview;
    # that now degrades to a redacted placeholder instead of a broken page.
    leads = []
    cats = {}
    for l in PACK_25["leads"]:
        cat = (l.get("category") or "uncategorized").strip() or "uncategorized"
        cats[cat] = cats.get(cat, 0) + 1
        email = l.get("contact_email") or ""
        src = l.get("source_url") or ""
        leads.append({
            "company_name": l.get("company_name") or "n/a",
            "city_state": l.get("city_state") or "n/a",
            "category": cat,
            "contact_email": mask_email(email) if email else "***",
            "source_domain": urlparse(src).netloc if src else "",
        })
    return {"pack": "scout-pack-25", "lead_count": 25, "price_usd": PACKS["25"]["price_usd"],
            "category_breakdown": cats, "leads": leads,
            "note": "Emails redacted in preview. Full JSON (verified emails + source URLs) delivered after payment."}

def base_url(handler):
    if PUBLIC_BASE:
        return PUBLIC_BASE.rstrip("/")
    host = handler.headers.get("Host", f"127.0.0.1:{PORT}")
    return f"http://{host}"

def payment_terms(handler, pack_size):
    p = PACKS[pack_size]
    base = base_url(handler)
    resource = f"{base}/packs/{pack_size}"
    desc = (f"Scout Pack {p['count']} — {p['count']} verified B2B leads as JSON "
            f"(lead enrichment batch: company, location, category, verified business "
            f"email, source URL per contact). Tiger Operations.")
    accept = {
        "scheme": "exact",
        "network": NETWORK,
        "amount": str(p["amount"]),
        "description": desc,
        "mimeType": "application/json",
        "payTo": RECEIVING if SALES_ENABLED else ZERO,
        "maxTimeoutSeconds": 300,
        "asset": USDC_BASE,
        "extra": {"name": "USD Coin", "version": "2"},
        "extensions": {"bazaar": BAZAAR_PACK},
    }
    return {
        "x402Version": 2,
        "accepts": [accept],
        "resource": {"url": resource, "description": desc, "mimeType": "application/json"},
        "sales_enabled": SALES_ENABLED,
        **({} if SALES_ENABLED else {"error": "Sales paused: seller receiving address not configured yet."}),
    }

def paywall_body(handler, pack_size):
    p = PACKS[pack_size]
    terms = payment_terms(handler, pack_size)
    return {
        "error": "payment_required",
        "pack": f"scout-pack-{pack_size}",
        "leads": p["count"],
        "price_usd": p["price_usd"],
        "currency": "USDC",
        "network": NETWORK,
        "fulfillment": ("Delivered as JSON download within minutes of payment confirmation."
                        if pack_size == "25" else
                        "Assembled on demand from the live verified list and delivered within 24 hours of payment confirmation."),
        "sales_enabled": SALES_ENABLED,
        "x402": terms,
        "how_to_pay": [
            ("1. Standard x402: sign an EIP-3009 authorization for exactly "
             f"${p['price_usd']:.2f} USDC on Base to "
             f"{RECEIVING if SALES_ENABLED else '(address pending)'} and retry this request "
             "with the signature in the X-PAYMENT (v1) or PAYMENT-SIGNATURE (v2) header. "
             "We verify + settle via facilitator and return your pack immediately (25) "
             "or queue it (50/100)."),
            ("2. Manual: send exactly "
             f"${p['price_usd']:.2f} USDC on Base to "
             f"{RECEIVING if SALES_ENABLED else '(address pending)'}, then "
             "POST /fulfill with {\"tx_hash\": \"0x...\", \"pack\": \"" + pack_size + "\"}"),
            "3. Receive your pack (25) or order receipt (50/100).",
        ],
    }

def find_lead(query):
    """Search the 25-lead database by company name or domain. Returns lead dict or None."""
    leads = PACK_25.get("leads", []) if isinstance(PACK_25, dict) else PACK_25
    q = (query or "").strip().lower()
    if not q:
        return None
    # Try domain match first (extract domain from source_url)
    for lead in leads:
        src = (lead.get("source_url") or "").lower()
        try:
            domain = urlparse(src).netloc.lower().replace("www.", "")
        except Exception:
            domain = ""
        if q in domain or domain in q:
            return lead
    # Then company name match
    for lead in leads:
        name = (lead.get("company_name") or "").lower()
        if q in name or name in q:
            return lead
    return None

def lookup_payment_terms(handler, query):
    base = base_url(handler)
    resource = f"{base}/lookup?query={query}"
    accept = {
        "scheme": "exact",
        "network": NETWORK,
        "amount": str(LOOKUP_AMOUNT),
        "description": LOOKUP_DESC,
        "mimeType": "application/json",
        "payTo": RECEIVING if SALES_ENABLED else ZERO,
        "maxTimeoutSeconds": 300,
        "asset": USDC_BASE,
        "extra": {"name": "USD Coin", "version": "2"},
        "extensions": {"bazaar": BAZAAR_LOOKUP},
    }
    return {
        "x402Version": 2,
        "accepts": [accept],
        "resource": {"url": resource, "description": LOOKUP_DESC, "mimeType": "application/json"},
        "sales_enabled": SALES_ENABLED,
        **({} if SALES_ENABLED else {"error": "Sales paused: seller receiving address not configured yet."}),
    }

def lookup_paywall_body(handler, query):
    terms = lookup_payment_terms(handler, query)
    return {
        "error": "payment_required",
        "service": "lead-lookup",
        "query": query,
        "price_usd": LOOKUP_PRICE_USD,
        "currency": "USDC",
        "network": NETWORK,
        "sales_enabled": SALES_ENABLED,
        "x402": terms,
        "how_to_pay": [
            ("1. Standard x402: sign an EIP-3009 authorization for exactly "
             f"${LOOKUP_PRICE_USD:.2f} USDC on Base to "
             f"{RECEIVING if SALES_ENABLED else '(address pending)'} and retry this request "
             "with the signature in the X-PAYMENT (v1) or PAYMENT-SIGNATURE (v2) header. "
             "We verify + settle via facilitator and return the contact immediately."),
            ("2. Manual: send exactly "
             f"${LOOKUP_PRICE_USD:.2f} USDC on Base to "
             f"{RECEIVING if SALES_ENABLED else '(address pending)'}, then POST /fulfill-lookup "
             "with {\"tx_hash\": \"0x...\", \"query\": \"" + query + "\"}"),
            "3. Receive the verified contact (email + source URL + provenance).",
        ],
    }

# ---------------------------------------------------------------- deliverability
# Email deliverability scoring: DNS-over-HTTPS (Cloudflare) for MX/TXT,
# plus static disposable/role/free-provider lists. Stdlib only.

DOH = "https://cloudflare-dns.com/dns-query"

DISPOSABLE_DOMAINS = frozenset("""
mailinator.com guerrillamail.com 10minutemail.com tempmail.com
temp-mail.org throwaway.email yopmail.com fakeinbox.com
getnada.com mohmal.com sharklasers.com trashmail.com
dispostable.com emailondeck.com mytemp.email tempmailo.com
""".split())

ROLE_LOCALPARTS = frozenset("""
info support sales admin contact hello mail webmaster
postmaster abuse noreply no-reply careers jobs press
marketing billing accounts helpdesk it security privacy
legal compliance unsubscribe newsletter office team
""".split())

FREE_PROVIDERS = frozenset("""
gmail.com yahoo.com hotmail.com outlook.com aol.com
icloud.com protonmail.com proton.me gmx.com zoho.com
yandex.com live.com msn.com comcast.net
""".split())

def doh_query(name, qtype):
    """DNS-over-HTTPS JSON lookup. Returns list of answer strings (may be empty)."""
    try:
        url = f"{DOH}?name={name}&type={qtype}"
        req = urllib.request.Request(url, headers={"Accept": "application/dns-json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        return [a.get("data", "") for a in data.get("Answer", []) if a.get("data")]
    except Exception:
        return []

def deliverability_score(target):
    """Score an email address or bare domain 0-100. Returns (score, verdict, flags, checks)."""
    target = (target or "").strip().lower()
    flags, checks = [], {}
    if "@" in target:
        local, _, domain = target.partition("@")
        kind = "email"
    else:
        local, domain = "", target.lstrip("@")
        kind = "domain"

    # Syntax
    syntax_ok = bool(re.fullmatch(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", target)) if kind == "email" \
        else bool(re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", domain))
    checks["syntax_valid"] = syntax_ok
    if not syntax_ok:
        flags.append("invalid_syntax")
        return 0, "do_not_send", flags, checks

    score = 100

    # MX records
    mx = doh_query(domain, "MX")
    checks["mx_records"] = [m for m in mx][:5]
    checks["mx_found"] = bool(mx)
    if not mx:
        score -= 60
        flags.append("no_mx_records")
    else:
        # Null MX (RFC 7505) means "accepts no mail"
        if any(m.strip().startswith("0 ") for m in mx):
            score -= 60
            flags.append("null_mx_rejects_mail")

    # SPF
    txt = doh_query(domain, "TXT")
    spf = any("v=spf1" in t for t in txt)
    checks["spf_found"] = spf
    if not spf:
        score -= 10
        flags.append("no_spf_record")

    # DMARC
    dmarc_txt = doh_query(f"_dmarc.{domain}", "TXT")
    dmarc = any("v=dmarc1" in t.lower() for t in dmarc_txt)
    checks["dmarc_found"] = dmarc
    if not dmarc:
        score -= 5
        flags.append("no_dmarc_record")

    # Disposable
    checks["disposable"] = domain in DISPOSABLE_DOMAINS
    if domain in DISPOSABLE_DOMAINS:
        score = min(score, 15)
        flags.append("disposable_domain")

    # Role account
    if kind == "email":
        checks["role_account"] = local in ROLE_LOCALPARTS
        if local in ROLE_LOCALPARTS:
            score -= 15
            flags.append("role_account")
        checks["free_provider"] = domain in FREE_PROVIDERS
        if domain in FREE_PROVIDERS:
            score -= 10
            flags.append("free_mailbox_provider")

    score = max(0, min(100, score))
    if score >= 80:
        verdict = "send"
    elif score >= 50:
        verdict = "caution"
    else:
        verdict = "do_not_send"
    if "no_mx_records" in flags or "null_mx_rejects_mail" in flags or "disposable_domain" in flags:
        verdict = "do_not_send"
    return score, verdict, flags, checks

def verify_deliverability_payment(tx_hash):
    """Returns (ok, detail) for $0.03 deliverability payments."""
    if not SALES_ENABLED:
        return False, "sales_paused: receiving address not configured"
    if not TX_RE.match(tx_hash or ""):
        return False, "bad_tx_hash"
    tx_hash = tx_hash.lower()
    redeemed = load_redeemed()
    if tx_hash in redeemed:
        return False, "already_redeemed"
    try:
        tx = blockscout_tx(tx_hash)
    except urllib.error.HTTPError as e:
        return (False, "tx_not_found") if e.code == 404 else (False, f"chain_lookup_failed:{e.code}")
    except Exception:
        return False, "chain_lookup_failed"
    if str(tx.get("status", "")).lower() != "ok":
        return False, "tx_not_successful"
    for t in tx.get("token_transfers", []) or []:
        try:
            tok_obj = t.get("token") or {}
            tok = (tok_obj.get("address_hash") or tok_obj.get("address") or "").lower()
            to = (t.get("to") or {}).get("hash", "").lower()
            val = int((t.get("total") or {}).get("value", 0))
            sender = (t.get("from") or {}).get("hash", "").lower()
        except (ValueError, TypeError):
            continue
        if tok == USDC_BASE.lower() and to == RECEIVING and val >= DELIVERABILITY_AMOUNT:
            redeemed.add(tx_hash)
            save_redeemed(redeemed)
            return True, {"sender": sender, "value": val}
    return False, "no_matching_usdc_transfer"

def deliverability_payment_terms(handler, target):
    base = base_url(handler)
    resource = f"{base}/deliverability?target={target}"
    accept = {
        "scheme": "exact",
        "network": NETWORK,
        "amount": str(DELIVERABILITY_AMOUNT),
        "description": DELIVERABILITY_DESC,
        "mimeType": "application/json",
        "payTo": RECEIVING if SALES_ENABLED else ZERO,
        "maxTimeoutSeconds": 300,
        "asset": USDC_BASE,
        "extra": {"name": "USD Coin", "version": "2"},
        "extensions": {"bazaar": BAZAAR_DELIVERABILITY},
    }
    return {
        "x402Version": 2,
        "accepts": [accept],
        "resource": {"url": resource, "description": DELIVERABILITY_DESC, "mimeType": "application/json"},
        "sales_enabled": SALES_ENABLED,
        **({} if SALES_ENABLED else {"error": "Sales paused: seller receiving address not configured yet."}),
    }

def deliverability_paywall_body(handler, target):
    terms = deliverability_payment_terms(handler, target)
    return {
        "error": "payment_required",
        "service": "deliverability-score",
        "target": target,
        "price_usd": DELIVERABILITY_PRICE_USD,
        "currency": "USDC",
        "network": NETWORK,
        "sales_enabled": SALES_ENABLED,
        "x402": terms,
        "how_to_pay": [
            ("1. Standard x402: sign an EIP-3009 authorization for exactly "
             f"${DELIVERABILITY_PRICE_USD:.2f} USDC on Base to "
             f"{RECEIVING if SALES_ENABLED else '(address pending)'} and retry this request "
             "with the signature in the X-PAYMENT (v1) or PAYMENT-SIGNATURE (v2) header. "
             "We verify + settle via facilitator and return the deliverability score immediately."),
            ("2. Manual: send exactly "
             f"${DELIVERABILITY_PRICE_USD:.2f} USDC on Base to "
             f"{RECEIVING if SALES_ENABLED else '(address pending)'}, then POST /fulfill-deliverability "
             "with {\"tx_hash\": \"0x...\", \"target\": \"" + target + "\"}"),
            "3. Receive the deliverability score (0-100), verdict, and risk flags.",
        ],
    }

# ---------------------------------------------------------------- packsize
# Pack-size identity resolver: deterministic parse of a product title into
# pack count + unit size + normalized totals. Stdlib only, no external data.

# unit -> (canonical name, multiplier to base unit)
UNIT_TABLE = {
    # weight (base: oz)
    "oz": ("oz", 1), "ounce": ("oz", 1), "ounces": ("oz", 1),
    "lb": ("oz", 16), "lbs": ("oz", 16), "pound": ("oz", 16), "pounds": ("oz", 16),
    "g": ("g", 1), "gram": ("g", 1), "grams": ("g", 1),
    "kg": ("g", 1000), "kilo": ("g", 1000), "kilogram": ("g", 1000),
    # volume (base: fl oz)
    "fl oz": ("fl_oz", 1), "floz": ("fl_oz", 1), "fluid ounce": ("fl_oz", 1),
    "ml": ("ml", 1), "milliliter": ("ml", 1),
    "l": ("ml", 1000), "liter": ("ml", 1000), "litre": ("ml", 1000),
    "gal": ("fl_oz", 128), "gallon": ("fl_oz", 128),
    "qt": ("fl_oz", 32), "quart": ("fl_oz", 32),
    "pt": ("fl_oz", 16), "pint": ("fl_oz", 16),
    # count (base: ct)
    "ct": ("ct", 1), "count": ("ct", 1),
    "pack": ("ct", 1), "packs": ("ct", 1),
    "roll": ("ct", 1), "rolls": ("ct", 1),
    "sheet": ("ct", 1), "sheets": ("ct", 1),
    "pair": ("ct", 2), "pairs": ("ct", 2),
    "dozen": ("ct", 12),
}

_PACK_RE = re.compile(r"""
    (?P<n>\d+(?:\.\d+)?)\s*[- ]?\s*pack\b |          # 12-pack, 12 pack
    \bpack\s+of\s+(?P<n2>\d+)\b |                    # pack of 12
    \bcase\s+of\s+(?P<n3>\d+)\b |                    # case of 24
    (?P<n4>\d+)\s*ct\b |                             # 48ct
    (?P<n5>\d+)\s*count\b |                           # 24 count
    (?P<n6>\d+)\s+(?:double\s+|mega\s+)?rolls?\b |    # 24 double rolls
    (?P<n7>\d+)\s+sheets?\b                          # 1000 sheets
""", re.IGNORECASE | re.VERBOSE)

_X_RE = re.compile(r"(?P<n>\d+)\s*[x×]\s*(?P<q>\d+(?:\.\d+)?)\s*(?P<u>[a-z]+)?", re.IGNORECASE)

_QTY_RE = re.compile(r"(?P<q>\d+(?:\.\d+)?)\s*[- ]?(?P<u>fl oz|floz|fluid ounces?|ounces?|oz|pounds?|lbs?|grams?|g|kilos?|kilograms?|milliliters?|ml|liters?|litres?|l|gallons?|gal|quarts?|qt|pints?|pt|sheets?|rolls?|counts?|ct|pairs?|dozens?)\b",
                     re.IGNORECASE)

_PACK_UNITS = frozenset(["pack", "packs"])

def packsize_parse(title):
    """Parse a product title. Returns dict with pack_count, units, totals, confidence."""
    t = (title or "").strip()
    low = t.lower()
    pack_count, pack_evidence = 1, []
    unit_qty, unit_name, unit_evidence = None, None, []

    m = _PACK_RE.search(low)
    if m:
        n = next((g for g in (m.group("n"), m.group("n2"), m.group("n3"),
                              m.group("n4"), m.group("n5"), m.group("n6"),
                              m.group("n7")) if g), None)
        if n:
            pack_count = int(float(n))
            pack_evidence.append(m.group(0).strip())

    mx = _X_RE.search(low)
    if mx and pack_count == 1:
        # "3 x 44oz" -> pack of 3
        pack_count = int(mx.group("n"))
        pack_evidence.append(mx.group(0).strip())
        uq, uu = mx.group("q"), (mx.group("u") or "").strip().lower()
        if uq and uu:
            unit_qty, unit_name = float(uq), uu
            unit_evidence.append(f"{uq} {uu}")

    if unit_qty is None:
        # find the largest plausible unit-size mention; skip tokens that are
        # the pack-count itself (e.g. the "12" in "12-pack")
        cands = []
        for qm in _QTY_RE.finditer(low):
            q, u = float(qm.group("q")), qm.group("u").lower().strip()
            if u in _PACK_UNITS:
                continue
            ev0 = qm.group(0).strip()
            # skip the pack-count token itself (e.g. "48ct" when pack came from "48ct")
            if any(ev0 == pe or ev0 in pe for pe in pack_evidence):
                continue
            cands.append((q, u, ev0))
        if cands:
            # prefer a size that differs from the pack count (avoids "12oz"
            # being swallowed when the pack is "12-pack"... keep it, it's
            # the unit). Prefer larger quantities as the unit size.
            cands.sort(key=lambda c: (c[0] == pack_count and c[1] in ("ct", "count"), -c[0]))
            unit_qty, unit_name, ev = cands[0][0], cands[0][1], cands[0][2]
            unit_evidence.append(ev)

    # normalize
    total_str, base_unit, total_val = None, None, None
    if unit_qty and unit_name:
        key = unit_name.rstrip("s") if unit_name.rstrip("s") in UNIT_TABLE else unit_name
        key = key if key in UNIT_TABLE else unit_name.rstrip("s")
        if key in UNIT_TABLE:
            base_unit, mult = UNIT_TABLE[key]
            total_val = round(unit_qty * mult * pack_count, 2)
            total_str = f"{total_val:g} {base_unit} total ({pack_count} x {unit_qty:g} {unit_name})"
        else:
            total_str = f"{pack_count} x {unit_qty:g} {unit_name} (unit not normalizable)"
    elif pack_count > 1:
        total_str = f"{pack_count} ct total"

    if pack_count > 1 and unit_qty:
        confidence = "high"
    elif pack_count > 1 or unit_qty:
        confidence = "medium"
    else:
        confidence = "low"

    flags = []
    if confidence == "low":
        flags.append("no_pack_pattern_found")
    if "assorted" in low or "variety" in low:
        flags.append("assorted_contents_not_comparable")

    return {
        "title": t,
        "pack_count": pack_count,
        "pack_evidence": pack_evidence,
        "unit_size": f"{unit_qty:g} {unit_name}" if unit_qty else None,
        "unit_evidence": unit_evidence,
        "total_normalized": total_str,
        "base_unit": base_unit,
        "total_value": total_val,
        "confidence": confidence,
        "flags": flags,
    }

def packsize_unit_price(parsed, price):
    """Comparable unit price given a package price. Returns string or None."""
    try:
        p = float(str(price).replace("$", "").replace(",", "").strip())
    except (ValueError, TypeError):
        return None
    tv = parsed.get("total_value")
    bu = parsed.get("base_unit")
    if tv and bu and tv > 0:
        return f"${p / tv:.4f} per {bu}"
    pc = parsed.get("pack_count") or 1
    return f"${p / pc:.4f} per unit ({pc} ct)"

def verify_packsize_payment(tx_hash):
    """Returns (ok, detail) for $0.02 packsize payments."""
    if not SALES_ENABLED:
        return False, "sales_paused: receiving address not configured"
    if not TX_RE.match(tx_hash or ""):
        return False, "bad_tx_hash"
    tx_hash = tx_hash.lower()
    redeemed = load_redeemed()
    if tx_hash in redeemed:
        return False, "already_redeemed"
    try:
        tx = blockscout_tx(tx_hash)
    except urllib.error.HTTPError as e:
        return (False, "tx_not_found") if e.code == 404 else (False, f"chain_lookup_failed:{e.code}")
    except Exception:
        return False, "chain_lookup_failed"
    if str(tx.get("status", "")).lower() != "ok":
        return False, "tx_not_successful"
    for t in tx.get("token_transfers", []) or []:
        try:
            tok_obj = t.get("token") or {}
            tok = (tok_obj.get("address_hash") or tok_obj.get("address") or "").lower()
            to = (t.get("to") or {}).get("hash", "").lower()
            val = int((t.get("total") or {}).get("value", 0))
            sender = (t.get("from") or {}).get("hash", "").lower()
        except (ValueError, TypeError):
            continue
        if tok == USDC_BASE.lower() and to == RECEIVING and val >= PACKSIZE_AMOUNT:
            redeemed.add(tx_hash)
            save_redeemed(redeemed)
            return True, {"sender": sender, "value": val}
    return False, "no_matching_usdc_transfer"

def packsize_payment_terms(handler, title, price):
    base = base_url(handler)
    q = f"title={title}" + (f"&price={price}" if price else "")
    resource = f"{base}/packsize?{q}"
    accept = {
        "scheme": "exact",
        "network": NETWORK,
        "amount": str(PACKSIZE_AMOUNT),
        "description": PACKSIZE_DESC,
        "mimeType": "application/json",
        "payTo": RECEIVING if SALES_ENABLED else ZERO,
        "maxTimeoutSeconds": 300,
        "asset": USDC_BASE,
        "extra": {"name": "USD Coin", "version": "2"},
        "extensions": {"bazaar": BAZAAR_PACKSIZE},
    }
    return {
        "x402Version": 2,
        "accepts": [accept],
        "resource": {"url": resource, "description": PACKSIZE_DESC, "mimeType": "application/json"},
        "sales_enabled": SALES_ENABLED,
        **({} if SALES_ENABLED else {"error": "Sales paused: seller receiving address not configured yet."}),
    }

def packsize_paywall_body(handler, title, price):
    terms = packsize_payment_terms(handler, title, price)
    return {
        "error": "payment_required",
        "service": "packsize-resolver",
        "title": title,
        "price_usd": PACKSIZE_PRICE_USD,
        "currency": "USDC",
        "network": NETWORK,
        "sales_enabled": SALES_ENABLED,
        "x402": terms,
        "how_to_pay": [
            ("1. Standard x402: sign an EIP-3009 authorization for exactly "
             f"${PACKSIZE_PRICE_USD:.2f} USDC on Base to "
             f"{RECEIVING if SALES_ENABLED else '(address pending)'} and retry this request "
             "with the signature in the X-PAYMENT (v1) or PAYMENT-SIGNATURE (v2) header. "
             "We verify + settle via facilitator and return the pack-size parse immediately."),
            ("2. Manual: send exactly "
             f"${PACKSIZE_PRICE_USD:.2f} USDC on Base to "
             f"{RECEIVING if SALES_ENABLED else '(address pending)'}, then POST /fulfill-packsize "
             "with {\"tx_hash\": \"0x...\", \"title\": \"" + title + "\"}"),
            "3. Receive the pack-size parse (pack count, unit size, normalized totals, unit price).",
        ],
    }

# ---------------------------------------------------------------- domain-intel
# Domain intelligence: RDAP registration data + DNS infrastructure signals.
# 100% free upstreams (RDAP via rdap.org, DNS-over-HTTPS) — no API key, no
# upstream ToS resale problem, zero marginal cost. $0.02/call. Attaches to the
# lead-enrichment buyer workflow: an agent vetting a company/domain gets
# registration age, registrar, and infra signals in one call. Stdlib only.

DOMAININTEL_PRICE_USD = 0.02
DOMAININTEL_AMOUNT = 20_000  # $0.02 in 6-decimal USDC
DOMAININTEL_DESC = ("Domain intelligence — RDAP registration data (registrar, "
                    "creation/expiry dates, status) plus DNS infrastructure signals "
                    "(nameservers, A records, mail exchanger presence). One domain "
                    "per call. Tiger Operations.")

PRIVACY_REGISTRAR_HINTS = ("privacy", "whoisguard", "whois guard", "domains by proxy",
                           "redacted", "withheld", "private", "guard")

def rdap_lookup(domain):
    """RDAP query via the rdap.org proxy. Returns parsed dict or {} on failure."""
    try:
        req = urllib.request.Request(f"https://rdap.org/domain/{domain}",
                                     headers={"Accept": "application/rdap+json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception:
        return {}

def _vcard_fn(vcard_array):
    """Extract fn/org values from an RDAP vcardArray."""
    out = {}
    try:
        for item in (vcard_array or [])[1]:
            if not isinstance(item, list) or len(item) < 4:
                continue
            name, value = item[0], item[3]
            if name in ("fn", "org") and value and name not in out:
                out[name] = value
    except Exception:
        pass
    return out

def domain_intel(domain):
    """Build domain intelligence. Returns (intel dict, flags list)."""
    raw = (domain or "").strip().lower()
    if "@" in raw:
        raw = raw.partition("@")[2]
    raw = raw.strip()
    intel = {"domain": raw}
    flags = []
    if not re.fullmatch(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}", raw):
        return intel, ["invalid_domain"]

    # RDAP registration data
    rdap = rdap_lookup(raw)
    reg = {}
    if rdap:
        for ent in rdap.get("entities", []) or []:
            roles = ent.get("roles", []) or []
            vc = _vcard_fn(ent.get("vcardArray"))
            if "registrar" in roles:
                reg["registrar"] = vc.get("fn") or vc.get("org") or ent.get("handle", "")
            elif "registrant" in roles and vc.get("org"):
                reg["registrant_org"] = vc["org"]
        for ev in rdap.get("events", []) or []:
            action = ev.get("eventAction", "")
            date = (ev.get("eventDate", "") or "")[:10]
            if action == "registration" and date:
                reg["created"] = date
            elif action == "expiration" and date:
                reg["expires"] = date
            elif action == "last changed" and date:
                reg["updated"] = date
        statuses = [str(s).strip() for s in (rdap.get("status", []) or [])]
        if statuses:
            reg["status"] = statuses[:8]
    intel["registration"] = reg
    if not reg:
        flags.append("rdap_unavailable")

    # Domain-age signal
    if reg.get("created"):
        try:
            created_ts = time.mktime(time.strptime(reg["created"], "%Y-%m-%d"))
            age_days = int((time.time() - created_ts) // 86400)
            intel["domain_age_days"] = age_days
            if age_days < 365:
                flags.append("young_domain_lt_1y")
            if age_days < 90:
                flags.append("very_young_domain_lt_90d")
        except Exception:
            pass
    registrar_l = (reg.get("registrar") or "").lower()
    if any(h in registrar_l for h in PRIVACY_REGISTRAR_HINTS):
        flags.append("privacy_protected_registrant")

    # DNS infrastructure signals (reuse Cloudflare DoH)
    ns = [n.rstrip(".") for n in doh_query(raw, "NS")]
    a = doh_query(raw, "A")
    mx = doh_query(raw, "MX")
    intel["dns"] = {
        "nameservers": ns[:6],
        "nameserver_count": len(ns),
        "a_records": a[:6],
        "a_record_count": len(a),
        "mx_found": bool(mx),
        "mx_hosts": [m.split(None, 1)[-1].rstrip(".") for m in mx][:3] if mx else [],
    }
    if not ns and not a:
        flags.append("no_dns_records")
    if not mx:
        flags.append("no_mail_exchangers")

    intel["signals"] = flags
    return intel, flags

def verify_domainintel_payment(tx_hash):
    """Returns (ok, detail) for $0.02 domain-intel payments."""
    if not SALES_ENABLED:
        return False, "sales_paused: receiving address not configured"
    if not TX_RE.match(tx_hash or ""):
        return False, "bad_tx_hash"
    tx_hash = tx_hash.lower()
    redeemed = load_redeemed()
    if tx_hash in redeemed:
        return False, "already_redeemed"
    try:
        tx = blockscout_tx(tx_hash)
    except urllib.error.HTTPError as e:
        return (False, "tx_not_found") if e.code == 404 else (False, f"chain_lookup_failed:{e.code}")
    except Exception:
        return False, "chain_lookup_failed"
    if str(tx.get("status", "")).lower() != "ok":
        return False, "tx_not_successful"
    for t in tx.get("token_transfers", []) or []:
        try:
            tok_obj = t.get("token") or {}
            tok = (tok_obj.get("address_hash") or tok_obj.get("address") or "").lower()
            to = (t.get("to") or {}).get("hash", "").lower()
            val = int((t.get("total") or {}).get("value", 0))
            sender = (t.get("from") or {}).get("hash", "").lower()
        except (ValueError, TypeError):
            continue
        if tok == USDC_BASE.lower() and to == RECEIVING and val >= DOMAININTEL_AMOUNT:
            redeemed.add(tx_hash)
            save_redeemed(redeemed)
            return True, {"sender": sender, "value": val}
    return False, "no_matching_usdc_transfer"

def domainintel_payment_terms(handler, domain):
    base = base_url(handler)
    resource = f"{base}/domain-intel?domain={domain}"
    accept = {
        "scheme": "exact",
        "network": NETWORK,
        "amount": str(DOMAININTEL_AMOUNT),
        "description": DOMAININTEL_DESC,
        "mimeType": "application/json",
        "payTo": RECEIVING if SALES_ENABLED else ZERO,
        "maxTimeoutSeconds": 300,
        "asset": USDC_BASE,
        "extra": {"name": "USD Coin", "version": "2"},
        "extensions": {"bazaar": BAZAAR_DOMAININTEL},
    }
    return {
        "x402Version": 2,
        "accepts": [accept],
        "resource": {"url": resource, "description": DOMAININTEL_DESC, "mimeType": "application/json"},
        "sales_enabled": SALES_ENABLED,
        **({} if SALES_ENABLED else {"error": "Sales paused: seller receiving address not configured yet."}),
    }

def domainintel_paywall_body(handler, domain):
    terms = domainintel_payment_terms(handler, domain)
    return {
        "error": "payment_required",
        "service": "domain-intel",
        "domain": domain,
        "price_usd": DOMAININTEL_PRICE_USD,
        "currency": "USDC",
        "network": NETWORK,
        "sales_enabled": SALES_ENABLED,
        "x402": terms,
        "how_to_pay": [
            ("1. Standard x402: sign an EIP-3009 authorization for exactly "
             f"${DOMAININTEL_PRICE_USD:.2f} USDC on Base to "
             f"{RECEIVING if SALES_ENABLED else '(address pending)'} and retry this request "
             "with the signature in the X-PAYMENT (v1) or PAYMENT-SIGNATURE (v2) header. "
             "We verify + settle via facilitator and return the domain intelligence immediately."),
            ("2. Manual: send exactly "
             f"${DOMAININTEL_PRICE_USD:.2f} USDC on Base to "
             f"{RECEIVING if SALES_ENABLED else '(address pending)'}, then POST /fulfill-domain-intel "
             "with {\"tx_hash\": \"0x...\", \"domain\": \"" + domain + "\"}"),
            "3. Receive RDAP registration data, DNS infrastructure signals, and risk flags.",
        ],
    }

# ---------------------------------------------------------------- server
class Handler(BaseHTTPRequestHandler):
    server_version = "scout-packs/1.0"

    # -- rate limiting (in-memory, per IP)
    _hits = {}
    def limited(self, cap=120, window=60):
        ip = self.client_address[0]
        now = time.time()
        h = [t for t in self._hits.get(ip, []) if now - t < window]
        h.append(now)
        self._hits[ip] = h
        return len(h) > cap

    def send_json(self, code, obj, extra_headers=None):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, code, text, ctype="text/plain; charset=utf-8"):
        body = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.limited():
            return self.send_json(429, {"error": "rate_limited", "retry_after_seconds": 60})
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            if path == "/":
                return self.landing()
            if path == "/health":
                return self.send_json(200, {"ok": True, "sales_enabled": SALES_ENABLED})
            if path == "/catalog":
                return self.send_json(200, self.catalog())
            if path == "/.well-known/x402":
                return self.send_json(200, self.well_known())
            if path == "/.well-known/402index-verify.txt":
                return self.verify_file()
            if path == "/llms.txt":
                return self.send_text(200, LLMS_TXT, "text/plain; charset=utf-8")
            if path == "/openapi.json":
                return self.send_json(200, OPENAPI_DOC)
            if path == "/skill.md":
                if SKILL_MD:
                    return self.send_text(200, SKILL_MD, "text/markdown; charset=utf-8")
                return self.send_json(404, {"error": "not_found"})
            if path == "/mcp":
                return self.proxy_mcp()
            if path == "/logo.png":
                return self.serve_logo()
            m = re.fullmatch(r"/packs/(\d+)(/preview)?", path)
            if m:
                size, preview = m.group(1), bool(m.group(2))
                if size not in PACKS:
                    return self.send_json(404, {"error": "unknown_pack", "packs": sorted(PACKS)})
                if preview:
                    return self.send_json(200, preview_pack())
                return self.paywall(size)
            if path == "/lookup":
                qs = urlparse(self.path).query
                params = dict(p.split("=", 1) for p in qs.split("&") if "=" in p)
                query = unquote_plus(params.get("query", params.get("domain", params.get("company", "")))).strip()
                if not query:
                    return self.send_json(400, {"error": "missing_query",
                        "usage": "GET /lookup?query=<company name or domain>",
                        "price_usd": LOOKUP_PRICE_USD, "currency": "USDC", "network": NETWORK})
                lead = find_lead(query)
                if not lead:
                    return self.send_json(404, {"error": "no_match", "query": query,
                        "hint": "No verified contact found for this query in the current database."})
                return self.lookup_paywall(query)
            if path == "/deliverability":
                qs = urlparse(self.path).query
                params = dict(p.split("=", 1) for p in qs.split("&") if "=" in p)
                target = unquote_plus(params.get("email", params.get("domain", params.get("target", "")))).strip()
                if not target:
                    return self.send_json(400, {"error": "missing_target",
                        "usage": "GET /deliverability?email=<address> or ?domain=<domain>",
                        "price_usd": DELIVERABILITY_PRICE_USD, "currency": "USDC", "network": NETWORK})
                return self.deliverability_paywall(target)
            if path == "/packsize":
                qs = urlparse(self.path).query
                params = dict(p.split("=", 1) for p in qs.split("&") if "=" in p)
                title = unquote_plus(params.get("title", "")).strip()
                price = unquote_plus(params.get("price", "")).strip() or None
                if not title:
                    return self.send_json(400, {"error": "missing_title",
                        "usage": "GET /packsize?title=<product title>&price=<optional package price>",
                        "price_usd": PACKSIZE_PRICE_USD, "currency": "USDC", "network": NETWORK})
                return self.packsize_paywall(title, price)
            if path == "/domain-intel":
                qs = urlparse(self.path).query
                params = dict(p.split("=", 1) for p in qs.split("&") if "=" in p)
                domain = unquote_plus(params.get("domain", params.get("email", ""))).strip()
                if not domain:
                    return self.send_json(400, {"error": "missing_domain",
                        "usage": "GET /domain-intel?domain=<domain>",
                        "price_usd": DOMAININTEL_PRICE_USD, "currency": "USDC", "network": NETWORK})
                return self.domainintel_paywall(domain)
            return self.send_json(404, {"error": "not_found"})
        except Exception:
            return self.send_json(500, {"error": "internal"})

    def do_POST(self):
        if self.limited(cap=30):
            return self.send_json(429, {"error": "rate_limited", "retry_after_seconds": 60})
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            if path == "/fulfill":
                return self.fulfill()
            if path == "/fulfill-lookup":
                return self.fulfill_lookup()
            if path == "/fulfill-deliverability":
                return self.fulfill_deliverability()
            if path == "/fulfill-packsize":
                return self.fulfill_packsize()
            if path == "/fulfill-domain-intel":
                return self.fulfill_domainintel()
            if path == "/mcp":
                return self.proxy_mcp()
            return self.send_json(404, {"error": "not_found"})
        except Exception:
            return self.send_json(500, {"error": "internal"})

    # -- routes
    def landing(self):
        leads = PACK_25.get("leads", [])
        feat = leads[7] if len(leads) > 7 else leads[0]
        fe = {k: html_lib.escape(str(feat.get(k, ""))) for k in
              ("company_name", "city_state", "category", "contact_email",
               "source_url", "verified", "verification")}
        fe_domain = html_lib.escape(urlparse(feat.get("source_url", "")).netloc)
        feat_json = html_lib.escape(json.dumps(feat, indent=2))
        badges = {"25": "Instant", "50": "Within 24 hours", "100": "Within 24 hours"}
        buy_lines = {
            s: (f"Authorize exactly <strong>${p['price_usd']:.2f} USDC on Base</strong> "
                f"for {p['count']} verified leads, delivered "
                f"{'immediately' if s == '25' else 'within 24 hours'}.")
            for s, p in PACKS.items()
        }
        cards = "".join(
            f'''<div class="pack">
  <div class="pack-head"><span class="pack-size">{p['count']} leads</span><span class="badge">{badges[s]}</span></div>
  <div class="pack-price"><span class="amount">${p['price_usd']}</span><span class="per">USDC · Base</span></div>
  <p class="buy-line">{buy_lines[s]}</p>
  <a class="btn-buy" href="/packs/{s}">Buy this pack</a>
  <div class="pack-foot"><a href="/packs/{s}/preview">redacted preview</a><code>GET /packs/{s}</code></div>
</div>'''
            for s, p in PACKS.items())
        pill = ('<span class="pill"><span class="dot"></span>Live — accepting USDC on Base</span>'
                if SALES_ENABLED else '<span class="pill off"><span class="dot"></span>Paused — seller address pending</span>')
        html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Scout Packs — Published business contacts. Source-linked JSON. One payment. · Tiger Operations</title>
<meta name="description" content="Verified B2B lead packs and per-lead enrichment lookups for agents. $0.01 per lookup or pack (demand probe). USDC on Base via x402. No account, API key, or subscription.">
<style>
:root{{--bg:#faf8f4;--panel:#ffffff;--line:#e4ded2;--line2:#d3cbb9;--ink:#1d2126;--muted:#5d6672;--faint:#9098a3;--amber:#b45309;--amber-dim:rgba(180,83,9,.07);--amber-line:#d9a441;--radius:12px;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;line-height:1.6;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:1020px;margin:0 auto;padding:0 28px 88px}}
.top{{display:flex;justify-content:space-between;align-items:center;padding:22px 0;border-bottom:1px solid var(--line)}}
.brand{{font-size:12px;font-weight:800;letter-spacing:.2em;color:var(--muted)}}
.pill{{display:inline-flex;align-items:center;gap:8px;font-size:12.5px;font-weight:650;color:var(--amber);background:var(--amber-dim);border:1px solid var(--amber-line);padding:7px 14px;border-radius:999px;white-space:nowrap}}
.pill.off{{color:var(--muted);background:transparent;border-color:var(--line2)}}
.dot{{width:8px;height:8px;border-radius:50%;background:var(--amber)}}
.pill.off .dot{{background:var(--faint)}}
.hero{{display:grid;grid-template-columns:1.02fr .98fr;gap:52px;padding:68px 0 60px;align-items:start}}
.eyebrow{{font-size:12px;font-weight:700;letter-spacing:.18em;text-transform:uppercase;color:var(--amber);margin:0 0 18px}}
h1{{font-size:clamp(36px,5.2vw,56px);line-height:1.1;letter-spacing:-.025em;margin:0 0 18px;font-weight:750}}
.lede{{font-size:18px;color:var(--muted);margin:0;max-width:460px}}
.record{{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:22px;box-shadow:0 2px 10px rgba(30,25,15,.05)}}
.rec-label{{font-size:11px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:var(--faint);margin-bottom:14px}}
.contact-card{{border:1px solid var(--line);border-radius:8px;padding:18px 18px 14px;margin-bottom:14px}}
.cc-name{{font-size:19px;font-weight:700;letter-spacing:-.01em}}
.cc-meta{{font-size:13px;color:var(--muted);margin:2px 0 12px}}
.cc-row{{display:flex;gap:12px;font-size:13.5px;padding:9px 0;border-top:1px solid var(--line);align-items:baseline}}
.cc-row>span{{width:62px;flex-shrink:0;font-size:10.5px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--faint)}}
.cc-row code{{font-family:var(--mono);font-size:12.5px;color:var(--ink);background:var(--bg);border:1px solid var(--line);padding:2px 8px;border-radius:5px;word-break:break-all}}
.cc-row a{{color:var(--amber);font-weight:600;word-break:break-all;text-decoration:none}}
.cc-row a:hover{{text-decoration:underline}}
.cc-note{{font-size:12.5px;color:var(--muted);margin:12px 0 0;padding-top:12px;border-top:1px dashed var(--line2)}}
.rec-json{{margin:0;background:#f4f1ea;border:1px solid var(--line);border-radius:8px;padding:16px 18px;font-family:var(--mono);font-size:12.5px;line-height:1.65;color:#3d4450;overflow-x:auto;white-space:pre}}
.caption{{font-size:13px;color:var(--faint);margin:12px 2px 0;font-style:italic}}
.section{{margin:0 0 72px}}
h2.sec{{font-size:23px;font-weight:750;letter-spacing:-.02em;margin:0 0 8px}}
.sec-sub{{color:var(--muted);margin:0 0 28px;max-width:660px;font-size:16px}}
.packs{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}}
.pack{{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:26px 24px 20px;display:flex;flex-direction:column}}
.pack-head{{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;gap:8px}}
.pack-size{{font-size:12px;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}}
.badge{{font-size:11.5px;font-weight:700;color:var(--amber);background:var(--amber-dim);border:1px solid var(--amber-line);padding:4px 11px;border-radius:999px;white-space:nowrap}}
.pack-price{{display:flex;align-items:baseline;gap:8px;margin-bottom:14px}}
.amount{{font-size:46px;font-weight:750;letter-spacing:-.02em;line-height:1}}
.per{{font-size:13px;color:var(--faint)}}
.buy-line{{font-size:14px;color:var(--muted);margin:0 0 18px;flex:1}}
.buy-line strong{{color:var(--ink)}}
.btn-buy{{display:block;text-align:center;background:var(--ink);color:#fff;text-decoration:none;font-weight:700;font-size:15px;padding:13px;border-radius:9px;margin-bottom:14px}}
.btn-buy:hover{{background:#000}}
.pack-foot{{display:flex;justify-content:space-between;align-items:center;border-top:1px solid var(--line);padding-top:14px;gap:8px}}
.pack-foot a{{color:var(--amber);font-size:13.5px;font-weight:600;text-decoration:none;white-space:nowrap}}
.pack-foot a:hover{{text-decoration:underline}}
.pack-foot code{{font-family:var(--mono);font-size:11.5px;color:var(--faint);background:var(--bg);border:1px solid var(--line);padding:3px 8px;border-radius:5px;white-space:nowrap}}
.rules{{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:10px 30px;margin:0}}
.rules li{{margin:15px 0;color:var(--muted);font-size:15px}}
.rules li strong{{color:var(--ink)}}
.rules li::marker{{color:var(--amber);font-weight:800}}
.steps{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}}
.step{{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:26px 24px}}
.step .n{{display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;border-radius:50%;background:var(--amber-dim);border:1px solid var(--amber-line);color:var(--amber);font-weight:800;font-size:14px;margin-bottom:14px}}
.step h3{{font-size:16.5px;margin:0 0 10px;letter-spacing:-.01em}}
.step p{{font-size:14.5px;color:var(--muted);margin:0}}
.step code{{font-family:var(--mono);font-size:12.5px;color:var(--ink);background:var(--bg);border:1px solid var(--line);padding:2px 8px;border-radius:5px;white-space:nowrap}}
table.eps{{width:100%;border-collapse:collapse;font-size:14px;background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden}}
table.eps td{{padding:13px 20px;border-bottom:1px solid var(--line);vertical-align:top}}
table.eps tr:last-child td{{border-bottom:0}}
table.eps td.c{{font-family:var(--mono);font-size:13px;color:var(--amber);white-space:nowrap;width:230px}}
table.eps td.d{{color:var(--muted)}}
.faq{{margin-top:26px}}
.faq details{{background:var(--panel);border:1px solid var(--line);border-radius:10px;margin-bottom:10px}}
.faq summary{{cursor:pointer;padding:16px 20px;font-weight:650;font-size:15px;list-style:none}}
.faq summary::-webkit-details-marker{{display:none}}
.faq summary::after{{content:"+";float:right;color:var(--amber);font-weight:800}}
.faq details[open] summary::after{{content:"–"}}
.faq .a{{padding:0 20px 18px;color:var(--muted);font-size:14.5px}}
.faq .a code{{font-family:var(--mono);font-size:12.5px;color:var(--ink);background:var(--bg);border:1px solid var(--line);padding:2px 8px;border-radius:5px}}
.faq .a a{{color:var(--amber);font-weight:600;text-decoration:none}}
.foot{{border-top:1px solid var(--line);padding-top:26px;display:flex;justify-content:space-between;gap:14px;font-size:13px;color:var(--faint);flex-wrap:wrap}}
.foot a{{color:var(--muted);text-decoration:none}}
.foot a:hover{{color:var(--amber)}}
@media (max-width:820px){{.hero{{grid-template-columns:1fr;gap:36px;padding:48px 0}}.packs,.steps{{grid-template-columns:1fr}}table.eps td.c{{width:auto}}}}
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <span class="brand">TIGER OPERATIONS</span>
    {pill}
  </header>

  <section class="hero">
    <div>
      <p class="eyebrow">Agent data supply · x402 paywall</p>
      <h1>Published business contacts. Source-linked JSON. One payment.</h1>
      <p class="lede">B2B lead packs and per-lead enrichment lookups for agents and operators. From $0.01. No account, API key, or subscription.</p>
    </div>
    <div class="record">
      <div class="rec-label">Sample record · from the 25-pack</div>
      <div class="contact-card">
        <div class="cc-name">{fe['company_name']}</div>
        <div class="cc-meta">{fe['city_state']} · {fe['category']}</div>
        <div class="cc-row"><span>Email</span><code>{fe['contact_email']}</code></div>
        <div class="cc-row"><span>Source</span><a href="{fe['source_url']}">{fe_domain}</a></div>
        <div class="cc-row"><span>Checked</span>{fe['verified']}</div>
        <div class="cc-note">{fe['verification']}</div>
      </div>
      <pre class="rec-json">{feat_json}</pre>
      <p class="caption">Inspect the record. Check the source. Then authorize payment.</p>
    </div>
  </section>

  <section class="section">
    <h2 class="sec">Available packs</h2>
    <p class="sec-sub">Fixed sizes, fixed prices. Every pack is the same record shape as the sample above.</p>
    <div class="packs">{cards}</div>
  </section>

  <section class="section">
    <h2 class="sec">Verification rules</h2>
    <p class="sec-sub">What &ldquo;verified&rdquo; means here — precisely, and what it doesn&rsquo;t.</p>
    <ul class="rules">
      <li><strong>Published business email.</strong> Every lead carries an email address the business itself made public — on its own website or a public business listing.</li>
      <li><strong>Source URL, always.</strong> Every lead carries the exact page where the email was found. Open it and check our work.</li>
      <li><strong>If it isn&rsquo;t published, it isn&rsquo;t in the pack.</strong> No scraping contact forms, no inferring addresses from directories.</li>
      <li><strong>Nothing guessed.</strong> We never pattern-match addresses (no <em>firstname.lastname@</em> guesses) and never synthesize contacts.</li>
      <li><strong>No deliverability claims.</strong> &ldquo;Verified&rdquo; means the email was found published and recorded with its source on the check date. We don&rsquo;t send test emails and don&rsquo;t run bounce checks.</li>
    </ul>
  </section>

  <section class="section">
    <h2 class="sec">Purchase flow</h2>
    <p class="sec-sub">Three steps. There is no signup page — there is nothing to sign up for.</p>
    <div class="steps">
      <div class="step"><span class="n">1</span><h3>Choose a pack</h3><p><code>GET /packs/25</code> (or <code>/50</code>, <code>/100</code>) answers <code>402 Payment Required</code> with the exact terms: amount, asset, destination address.</p></div>
      <div class="step"><span class="n">2</span><h3>Pay with signed x402</h3><p>Sign an EIP-3009 USDC authorization on Base for the exact amount and retry with the signature in <code>X-PAYMENT</code> (v1) or <code>PAYMENT-SIGNATURE</code> (v2). Settled via facilitator — your wallet, your keys, no separate transfer needed.</p></div>
      <div class="step"><span class="n">3</span><h3>Receive JSON</h3><p>The 25-pack downloads immediately; 50 and 100 are assembled and delivered within 24 hours. Prefer manual? Send the USDC yourself, then <code>POST /fulfill</code> with your transaction hash.</p></div>
    </div>
  </section>

  <section class="section">
    <h2 class="sec">Technical details &amp; FAQ</h2>
    <p class="sec-sub">For the agents (and operators) doing the buying.</p>
    <table class="eps">
      <tr><td class="c">GET /catalog</td><td class="d">Pack list and prices — free</td></tr>
      <tr><td class="c">GET /.well-known/x402</td><td class="d">Machine-readable payment terms for all packs + lookup — free</td></tr>
      <tr><td class="c">GET /llms.txt</td><td class="d">Agent-readable service description — free</td></tr>
      <tr><td class="c">GET /skill.md</td><td class="d">Agent skill file (lead lookup usage) — free</td></tr>
      <tr><td class="c">GET /lookup?query=&lt;company&gt;</td><td class="d">One verified business email per company — 402 paywall ($0.01)</td></tr>
      <tr><td class="c">POST /fulfill-lookup</td><td class="d">Submit <code>&#123;"tx_hash", "query"&#125;</code>, receive the verified contact — paid</td></tr>
      <tr><td class="c">/mcp</td><td class="d">MCP streamable-HTTP endpoint (same tools, durable HTTPS) — free tools, paid lookup</td></tr>
      <tr><td class="c">GET /packs/&#123;25,50,100&#125;</td><td class="d">The pack itself — 402 paywall (x402 v2 + v1 headers)</td></tr>
      <tr><td class="c">GET /packs/&#123;25,50,100&#125;/preview</td><td class="d">Redacted sample, emails masked — free</td></tr>
      <tr><td class="c">POST /fulfill</td><td class="d">Submit <code>&#123;"tx_hash", "pack"&#125;</code>, receive the pack — paid</td></tr>
    </table>
    <div class="faq">
      <details>
        <summary>How do I receive a 50 or 100-pack without an account?</summary>
        <div class="a">Pay with a signed x402 payment (<code>X-PAYMENT</code> / <code>PAYMENT-SIGNATURE</code>), or pay manually then <code>POST /fulfill</code> with <code>&#123;"tx_hash": "0x…", "pack": "50"&#125;</code> — add <code>"deliver_to"</code> if you want it sent somewhere specific. We verify the USDC transfer on-chain and queue your pack for assembly. Your transaction hash <em>is</em> your receipt; there is nothing to log into.</div>
      </details>
      <details>
        <summary>What exactly am I authorizing?</summary>
        <div class="a">Exactly $0.01 in USDC on Base (<code>eip155:8453</code>), authorized to the address in the 402 payment terms via a signed x402 payment. One payment. No subscription, no recurring charge. Pricing is a demand probe and may change; the 402 terms always show the current price.</div>
      </details>
      <details>
        <summary>What does &ldquo;verified&rdquo; mean?</summary>
        <div class="a">Each email was found published on the business&rsquo;s own site or public listing and recorded with the source URL on the check date. We don&rsquo;t guess addresses and don&rsquo;t run deliverability tests. See the verification rules above.</div>
      </details>
      <details>
        <summary>Can I inspect before buying?</summary>
        <div class="a">Yes. The sample record above is real inventory from the 25-pack, and every pack has a free redacted preview at <code>/packs/&#123;size&#125;/preview</code> with emails masked. The full catalog is public at <code>/catalog</code>.</div>
      </details>
    </div>
  </section>

  <footer class="foot">
    <span>Tiger Operations — Agent Data Supply Company</span>
    <span><a href="https://github.com/tigerops-win/scout-packs">Open-source MCP server</a> · Paid in USDC on Base</span>
  </footer>
</div>
</body>
</html>"""
        self.send_text(200, html, "text/html; charset=utf-8")
    def catalog(self):
        return {"seller": "Tiger Operations",
                "packs": {f"scout-pack-{s}": {"leads": p["count"], "price_usd": p["price_usd"],
                           "currency": "USDC", "network": NETWORK, "fulfillment_eta": p["eta"]}
                          for s, p in PACKS.items()},
                "sales_enabled": SALES_ENABLED}

    def well_known(self):
        base = base_url(self)
        resources = []
        # Primary product: $0.01/lookup B2B lead enrichment. Representative resource URL;
        # actual queries use /lookup?query=<company or domain>.
        lookup_accept = {
            "scheme": "exact",
            "network": NETWORK,
            "amount": str(LOOKUP_AMOUNT),
            "description": LOOKUP_DESC,
            "mimeType": "application/json",
            "payTo": RECEIVING if SALES_ENABLED else ZERO,
            "maxTimeoutSeconds": 300,
            "asset": USDC_BASE,
            "extra": {"name": "USD Coin", "version": "2"},
            "extensions": {"bazaar": BAZAAR_LOOKUP},
        }
        resources.append({"resource": f"{base}/lookup", "accepts": [lookup_accept]})
        # Per-call service endpoints (added 2026-10-05; previously missing from
        # the manifest — registries ingesting /.well-known/x402 couldn't see them).
        for svc_path, amount, desc, bazaar in (
            ("/deliverability", DELIVERABILITY_AMOUNT, DELIVERABILITY_DESC, BAZAAR_DELIVERABILITY),
            ("/packsize", PACKSIZE_AMOUNT, PACKSIZE_DESC, BAZAAR_PACKSIZE),
            ("/domain-intel", DOMAININTEL_AMOUNT, DOMAININTEL_DESC, BAZAAR_DOMAININTEL),
        ):
            resources.append({"resource": f"{base}{svc_path}", "accepts": [{
                "scheme": "exact",
                "network": NETWORK,
                "amount": str(amount),
                "description": desc,
                "mimeType": "application/json",
                "payTo": RECEIVING if SALES_ENABLED else ZERO,
                "maxTimeoutSeconds": 300,
                "asset": USDC_BASE,
                "extra": {"name": "USD Coin", "version": "2"},
                "extensions": {"bazaar": bazaar},
            }]})
        for s, p in PACKS.items():
            t = payment_terms(self, s)
            resources.append({"resource": f"{base}/packs/{s}", "accepts": t["accepts"]})
        return {"x402Version": 2, "sales_enabled": SALES_ENABLED, "resources": resources}

    def verify_file(self):
        if os.path.exists(VERIFY_PATH):
            with open(VERIFY_PATH) as f:
                return self.send_text(200, f.read().strip())
        return self.send_text(404, "not claimed yet")

    def proxy_mcp(self):
        """Reverse-proxy /mcp to the sibling MCP streamable-HTTP server.

        Active only when MCP_PROXY_PORT is set. The MCP server runs in
        stateless_http mode, so each request is an independent JSON-RPC
        POST (or SSE-capable GET) returning a single JSON body — a simple
        forward/relay is sufficient. Any upstream failure surfaces as 502,
        never as a fake MCP response.
        """
        if not MCP_PROXY_PORT.isdigit():
            return self.send_json(404, {"error": "not_found"})
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except (TypeError, ValueError):
            length = 0
        body = self.rfile.read(length) if length > 0 else None
        upstream = f"http://127.0.0.1:{MCP_PROXY_PORT}/mcp"
        fwd_headers = {k: v for k, v in self.headers.items()
                       if k.lower() not in ("host", "content-length", "connection")}
        req = urllib.request.Request(upstream, data=body, headers=fwd_headers,
                                     method=self.command)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                resp_body = r.read()
                status, ctype = r.status, r.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as e:
            resp_body = e.read() or b""
            status, ctype = e.code, e.headers.get("Content-Type", "application/json")
        except Exception:
            return self.send_json(502, {"error": "mcp_upstream_unreachable",
                                        "hint": "start mcp/http_server.py on MCP_PROXY_PORT"})
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(resp_body)))
        self.end_headers()
        self.wfile.write(resp_body)

    def serve_logo(self):
        logo_path = os.path.join(BASE_DIR, "assets", "scout-packs-logo-512.png")
        if os.path.exists(logo_path):
            with open(logo_path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(data)
            return
        return self.send_json(404, {"error": "not_found"})

    def paywall(self, size):
        version, payment_b64 = x402_incoming_payment(self.headers)
        if payment_b64:
            return self.serve_paid_pack(size, version, payment_b64)
        body = paywall_body(self, size)
        terms_b64_v2 = base64.b64encode(json.dumps(body["x402"]).encode()).decode()
        terms_v1 = {"x402Version": 1, "accepts": [{
            "scheme": "exact", "network": NETWORK_V1, "maxAmountRequired": str(PACKS[size]["amount"]),
            "resource": f"{base_url(self)}/packs/{size}",
            "description": body["x402"]["accepts"][0]["description"],
            "mimeType": "application/json", "payTo": body["x402"]["accepts"][0]["payTo"],
            "maxTimeoutSeconds": 300, "asset": USDC_BASE, "extra": {"name": "USD Coin", "version": "2"}}]}
        terms_b64_v1 = base64.b64encode(json.dumps(terms_v1).encode()).decode()
        self.send_json(402, body, {
            "PAYMENT-REQUIRED": terms_b64_v2,
            "X-PAYMENT-REQUIRED": terms_b64_v1,
        })

    def lookup_paywall(self, query):
        version, payment_b64 = x402_incoming_payment(self.headers)
        if payment_b64:
            return self.serve_paid_lookup(query, version, payment_b64)
        body = lookup_paywall_body(self, query)
        terms_b64_v2 = base64.b64encode(json.dumps(body["x402"]).encode()).decode()
        terms_v1 = {"x402Version": 1, "accepts": [{
            "scheme": "exact", "network": NETWORK_V1, "maxAmountRequired": str(LOOKUP_AMOUNT),
            "resource": f"{base_url(self)}/lookup?query={query}",
            "description": body["x402"]["accepts"][0]["description"],
            "mimeType": "application/json", "payTo": body["x402"]["accepts"][0]["payTo"],
            "maxTimeoutSeconds": 300, "asset": USDC_BASE, "extra": {"name": "USD Coin", "version": "2"}}]}
        terms_b64_v1 = base64.b64encode(json.dumps(terms_v1).encode()).decode()
        self.send_json(402, body, {
            "PAYMENT-REQUIRED": terms_b64_v2,
            "X-PAYMENT-REQUIRED": terms_b64_v1,
        })

    def serve_paid_lookup(self, query, version, payment_b64):
        """Settle a signed x402 payment for /lookup and return the contact."""
        if not SALES_ENABLED:
            return self.send_json(402, {"error": "payment_required",
                                        "detail": "sales_paused"})
        lead = find_lead(query)
        if not lead:
            # Nothing to sell: do not settle, do not charge.
            return self.send_json(404, {"error": "no_match", "query": query,
                "hint": "No verified contact found for this query in the current database."})
        resource = f"{base_url(self)}/lookup?query={query}"
        req = x402_requirements(version, resource, LOOKUP_AMOUNT, LOOKUP_DESC)
        ok, info = settle_x402_payment(version, payment_b64, req)
        if not ok:
            return self.send_json(402, {"error": "payment_not_verified",
                                        "detail": info,
                                        "retry_with": "X-PAYMENT (v1) or PAYMENT-SIGNATURE (v2)"})
        tx_hash, payer = info["tx_hash"], info["payer"]
        log_sale("lookup", {"method": "x402", "query": query, "tx_hash": tx_hash,
                            "sender": payer or "unknown",
                            "amount_usd": LOOKUP_PRICE_USD,
                            "replay": info.get("replay", False)})
        resp_header = ("X-PAYMENT-RESPONSE" if version == 1 else "PAYMENT-RESPONSE")
        return self.send_json(200, {
            "receipt": "ok",
            "service": "lead-lookup",
            "query": query,
            "tx_hash": tx_hash,
            "price_usd": LOOKUP_PRICE_USD,
            "lead": lead,
            "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "note": "Verified business contact delivered. Source URL included for provenance.",
        }, {resp_header: x402_settlement_response_header(version, tx_hash, payer)})

    def deliverability_paywall(self, target):
        version, payment_b64 = x402_incoming_payment(self.headers)
        if payment_b64:
            return self.serve_paid_deliverability(target, version, payment_b64)
        body = deliverability_paywall_body(self, target)
        terms_b64_v2 = base64.b64encode(json.dumps(body["x402"]).encode()).decode()
        terms_v1 = {"x402Version": 1, "accepts": [{
            "scheme": "exact", "network": NETWORK_V1, "maxAmountRequired": str(DELIVERABILITY_AMOUNT),
            "resource": f"{base_url(self)}/deliverability?target={target}",
            "description": body["x402"]["accepts"][0]["description"],
            "mimeType": "application/json", "payTo": body["x402"]["accepts"][0]["payTo"],
            "maxTimeoutSeconds": 300, "asset": USDC_BASE, "extra": {"name": "USD Coin", "version": "2"}}]}
        terms_b64_v1 = base64.b64encode(json.dumps(terms_v1).encode()).decode()
        self.send_json(402, body, {
            "PAYMENT-REQUIRED": terms_b64_v2,
            "X-PAYMENT-REQUIRED": terms_b64_v1,
        })

    def serve_paid_deliverability(self, target, version, payment_b64):
        """Settle a signed x402 payment for /deliverability and return the score."""
        if not SALES_ENABLED:
            return self.send_json(402, {"error": "payment_required",
                                        "detail": "sales_paused"})
        resource = f"{base_url(self)}/deliverability?target={target}"
        req = x402_requirements(version, resource, DELIVERABILITY_AMOUNT, DELIVERABILITY_DESC)
        ok, info = settle_x402_payment(version, payment_b64, req)
        if not ok:
            return self.send_json(402, {"error": "payment_not_verified",
                                        "detail": info,
                                        "retry_with": "X-PAYMENT (v1) or PAYMENT-SIGNATURE (v2)"})
        tx_hash, payer = info["tx_hash"], info["payer"]
        score, verdict, flags, checks = deliverability_score(target)
        log_sale("deliverability", {"method": "x402", "target": target, "tx_hash": tx_hash,
                                    "sender": payer or "unknown",
                                    "amount_usd": DELIVERABILITY_PRICE_USD,
                                    "score": score, "verdict": verdict,
                                    "replay": info.get("replay", False)})
        resp_header = ("X-PAYMENT-RESPONSE" if version == 1 else "PAYMENT-RESPONSE")
        return self.send_json(200, {
            "receipt": "ok",
            "service": "deliverability-score",
            "target": target,
            "tx_hash": tx_hash,
            "price_usd": DELIVERABILITY_PRICE_USD,
            "score": score,
            "verdict": verdict,
            "flags": flags,
            "checks": checks,
            "scored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "note": "Deliverability score 0-100. Verdict: send / caution / do_not_send.",
        }, {resp_header: x402_settlement_response_header(version, tx_hash, payer)})

    def fulfill_deliverability(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self.send_json(400, {"error": "bad_json"})
        target = str(payload.get("target", "")).strip()
        tx_hash = str(payload.get("tx_hash", ""))
        if not target:
            return self.send_json(400, {"error": "missing_target"})
        ok, detail = verify_deliverability_payment(tx_hash)
        if not ok:
            return self.send_json(402, {"error": "payment_not_verified", "detail": detail,
                                        "pay": deliverability_paywall_body(self, target)["how_to_pay"]})
        sender = detail.get("sender", "unknown") if isinstance(detail, dict) else "unknown"
        score, verdict, flags, checks = deliverability_score(target)
        log_sale("deliverability", {"method": "manual", "target": target,
                                    "tx_hash": tx_hash.lower(), "sender": sender,
                                    "amount_usd": DELIVERABILITY_PRICE_USD,
                                    "score": score, "verdict": verdict})
        return self.send_json(200, {
            "receipt": "ok",
            "service": "deliverability-score",
            "target": target,
            "tx_hash": tx_hash.lower(),
            "price_usd": DELIVERABILITY_PRICE_USD,
            "score": score,
            "verdict": verdict,
            "flags": flags,
            "checks": checks,
            "scored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })

    def domainintel_paywall(self, domain):
        version, payment_b64 = x402_incoming_payment(self.headers)
        if payment_b64:
            return self.serve_paid_domainintel(domain, version, payment_b64)
        body = domainintel_paywall_body(self, domain)
        terms_b64_v2 = base64.b64encode(json.dumps(body["x402"]).encode()).decode()
        terms_v1 = {"x402Version": 1, "accepts": [{
            "scheme": "exact", "network": NETWORK_V1, "maxAmountRequired": str(DOMAININTEL_AMOUNT),
            "resource": f"{base_url(self)}/domain-intel?domain={domain}",
            "description": body["x402"]["accepts"][0]["description"],
            "mimeType": "application/json", "payTo": body["x402"]["accepts"][0]["payTo"],
            "maxTimeoutSeconds": 300, "asset": USDC_BASE, "extra": {"name": "USD Coin", "version": "2"}}]}
        terms_b64_v1 = base64.b64encode(json.dumps(terms_v1).encode()).decode()
        self.send_json(402, body, {
            "PAYMENT-REQUIRED": terms_b64_v2,
            "X-PAYMENT-REQUIRED": terms_b64_v1,
        })

    def serve_paid_domainintel(self, domain, version, payment_b64):
        """Settle a signed x402 payment for /domain-intel and return the intel."""
        if not SALES_ENABLED:
            return self.send_json(402, {"error": "payment_required",
                                        "detail": "sales_paused"})
        resource = f"{base_url(self)}/domain-intel?domain={domain}"
        req = x402_requirements(version, resource, DOMAININTEL_AMOUNT, DOMAININTEL_DESC)
        ok, info = settle_x402_payment(version, payment_b64, req)
        if not ok:
            return self.send_json(402, {"error": "payment_not_verified",
                                        "detail": info,
                                        "retry_with": "X-PAYMENT (v1) or PAYMENT-SIGNATURE (v2)"})
        tx_hash, payer = info["tx_hash"], info["payer"]
        intel, flags = domain_intel(domain)
        log_sale("domain-intel", {"method": "x402", "domain": domain, "tx_hash": tx_hash,
                                  "sender": payer or "unknown",
                                  "amount_usd": DOMAININTEL_PRICE_USD,
                                  "flags": flags,
                                  "replay": info.get("replay", False)})
        resp_header = ("X-PAYMENT-RESPONSE" if version == 1 else "PAYMENT-RESPONSE")
        return self.send_json(200, {
            "receipt": "ok",
            "service": "domain-intel",
            "tx_hash": tx_hash,
            "price_usd": DOMAININTEL_PRICE_USD,
            **intel,
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "note": "RDAP registration data + DNS infrastructure signals. Upstreams: rdap.org, Cloudflare DoH.",
        }, {resp_header: x402_settlement_response_header(version, tx_hash, payer)})

    def fulfill_domainintel(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self.send_json(400, {"error": "bad_json"})
        domain = str(payload.get("domain", "")).strip()
        tx_hash = str(payload.get("tx_hash", ""))
        if not domain:
            return self.send_json(400, {"error": "missing_domain"})
        ok, detail = verify_domainintel_payment(tx_hash)
        if not ok:
            return self.send_json(402, {"error": "payment_not_verified", "detail": detail,
                                        "pay": domainintel_paywall_body(self, domain)["how_to_pay"]})
        sender = detail.get("sender", "unknown") if isinstance(detail, dict) else "unknown"
        intel, flags = domain_intel(domain)
        log_sale("domain-intel", {"method": "manual", "domain": domain,
                                  "tx_hash": tx_hash.lower(), "sender": sender,
                                  "amount_usd": DOMAININTEL_PRICE_USD,
                                  "flags": flags})
        return self.send_json(200, {
            "receipt": "ok",
            "service": "domain-intel",
            "tx_hash": tx_hash.lower(),
            "price_usd": DOMAININTEL_PRICE_USD,
            **intel,
            "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })

    def packsize_paywall(self, title, price):
        version, payment_b64 = x402_incoming_payment(self.headers)
        if payment_b64:
            return self.serve_paid_packsize(title, price, version, payment_b64)
        body = packsize_paywall_body(self, title, price)
        terms_b64_v2 = base64.b64encode(json.dumps(body["x402"]).encode()).decode()
        q = f"title={title}" + (f"&price={price}" if price else "")
        terms_v1 = {"x402Version": 1, "accepts": [{
            "scheme": "exact", "network": NETWORK_V1, "maxAmountRequired": str(PACKSIZE_AMOUNT),
            "resource": f"{base_url(self)}/packsize?{q}",
            "description": body["x402"]["accepts"][0]["description"],
            "mimeType": "application/json", "payTo": body["x402"]["accepts"][0]["payTo"],
            "maxTimeoutSeconds": 300, "asset": USDC_BASE, "extra": {"name": "USD Coin", "version": "2"}}]}
        terms_b64_v1 = base64.b64encode(json.dumps(terms_v1).encode()).decode()
        self.send_json(402, body, {
            "PAYMENT-REQUIRED": terms_b64_v2,
            "X-PAYMENT-REQUIRED": terms_b64_v1,
        })

    def _packsize_result(self, title, price, tx_hash, payer, method):
        parsed = packsize_parse(title)
        unit_price = packsize_unit_price(parsed, price) if price else None
        log_sale("packsize", {"method": method, "title": title, "tx_hash": tx_hash,
                              "sender": payer or "unknown",
                              "amount_usd": PACKSIZE_PRICE_USD,
                              "confidence": parsed["confidence"]})
        return {
            "receipt": "ok",
            "service": "packsize-resolver",
            "title": title,
            "tx_hash": tx_hash,
            "price_usd": PACKSIZE_PRICE_USD,
            "pack_count": parsed["pack_count"],
            "pack_evidence": parsed["pack_evidence"],
            "unit_size": parsed["unit_size"],
            "unit_evidence": parsed["unit_evidence"],
            "total_normalized": parsed["total_normalized"],
            "unit_price": unit_price,
            "confidence": parsed["confidence"],
            "flags": parsed["flags"],
            "parsed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "note": "Deterministic pack-size parse. Comparable unit pricing needs the normalized total.",
        }

    def serve_paid_packsize(self, title, price, version, payment_b64):
        """Settle a signed x402 payment for /packsize and return the parse."""
        if not SALES_ENABLED:
            return self.send_json(402, {"error": "payment_required",
                                        "detail": "sales_paused"})
        q = f"title={title}" + (f"&price={price}" if price else "")
        resource = f"{base_url(self)}/packsize?{q}"
        req = x402_requirements(version, resource, PACKSIZE_AMOUNT, PACKSIZE_DESC)
        ok, info = settle_x402_payment(version, payment_b64, req)
        if not ok:
            return self.send_json(402, {"error": "payment_not_verified",
                                        "detail": info,
                                        "retry_with": "X-PAYMENT (v1) or PAYMENT-SIGNATURE (v2)"})
        tx_hash, payer = info["tx_hash"], info["payer"]
        result = self._packsize_result(title, price, tx_hash, payer, "x402")
        resp_header = ("X-PAYMENT-RESPONSE" if version == 1 else "PAYMENT-RESPONSE")
        return self.send_json(200, result,
                              {resp_header: x402_settlement_response_header(version, tx_hash, payer)})

    def fulfill_packsize(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self.send_json(400, {"error": "bad_json"})
        title = str(payload.get("title", "")).strip()
        price = str(payload.get("price", "")).strip() or None
        tx_hash = str(payload.get("tx_hash", ""))
        if not title:
            return self.send_json(400, {"error": "missing_title"})
        ok, detail = verify_packsize_payment(tx_hash)
        if not ok:
            return self.send_json(402, {"error": "payment_not_verified", "detail": detail,
                                        "pay": packsize_paywall_body(self, title, price)["how_to_pay"]})
        sender = detail.get("sender", "unknown") if isinstance(detail, dict) else "unknown"
        result = self._packsize_result(title, price, tx_hash.lower(), sender, "manual")
        return self.send_json(200, result)

    def serve_paid_pack(self, size, version, payment_b64):
        """Settle a signed x402 payment for /packs/{size}."""
        if not SALES_ENABLED:
            return self.send_json(402, {"error": "payment_required",
                                        "detail": "sales_paused"})
        p = PACKS[size]
        base = base_url(self)
        resource = f"{base}/packs/{size}"
        desc = (f"Scout Pack {p['count']} — {p['count']} verified B2B leads as JSON. "
                "Tiger Operations.")
        req = x402_requirements(version, resource, p["amount"], desc)
        ok, info = settle_x402_payment(version, payment_b64, req)
        if not ok:
            return self.send_json(402, {"error": "payment_not_verified",
                                        "detail": info,
                                        "retry_with": "X-PAYMENT (v1) or PAYMENT-SIGNATURE (v2)"})
        tx_hash, payer = info["tx_hash"], info["payer"]
        log_sale("pack", {"method": "x402", "pack": size, "tx_hash": tx_hash,
                          "sender": payer or "unknown",
                          "amount_usd": p["price_usd"],
                          "replay": info.get("replay", False)})
        receipt = {"receipt": "ok", "pack": f"scout-pack-{size}",
                   "tx_hash": tx_hash,
                   "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        if size == "25":
            receipt["leads"] = PACK_25
            receipt["note"] = "Pack 25 delivered as JSON. Retain this receipt."
        else:
            order_id = hashlib.sha256(f"{tx_hash}{size}{time.time()}".encode()).hexdigest()[:16]
            receipt.update({"order_id": order_id, "status": "queued_for_assembly",
                            "eta": "within 24 hours of payment confirmation",
                            "note": ("Your 50/100-lead pack is assembled on demand from the live "
                                     "verified list and delivered within 24h.")})
        resp_header = ("X-PAYMENT-RESPONSE" if version == 1 else "PAYMENT-RESPONSE")
        return self.send_json(200, receipt,
                              {resp_header: x402_settlement_response_header(version, tx_hash, payer)})

    def fulfill(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self.send_json(400, {"error": "bad_json"})
        pack = str(payload.get("pack", ""))
        tx_hash = str(payload.get("tx_hash", ""))
        deliver_to = str(payload.get("deliver_to", ""))[:200]
        if pack not in PACKS:
            return self.send_json(400, {"error": "unknown_pack", "packs": sorted(PACKS)})
        ok, detail = verify_payment(tx_hash, pack)
        if not ok:
            return self.send_json(402, {"error": "payment_not_verified", "detail": detail,
                                        "pay": paywall_body(self, pack)["how_to_pay"]})
        receipt = {"receipt": "ok", "pack": f"scout-pack-{pack}", "tx_hash": tx_hash.lower(),
                   "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        if pack == "25":
            receipt["leads"] = PACK_25
            receipt["note"] = "Pack 25 delivered as JSON. Retain this receipt."
            return self.send_json(200, receipt)
        order_id = hashlib.sha256(f"{tx_hash}{pack}{time.time()}".encode()).hexdigest()[:16]
        receipt.update({"order_id": order_id, "status": "queued_for_assembly",
                        "eta": "within 24 hours of payment confirmation",
                        "deliver_to": deliver_to or "(not specified — reply with a delivery target)",
                        "note": ("Your 50/100-lead pack is assembled on demand from the live verified list "
                                 "and delivered within 24h to your delivery target.")})
        return self.send_json(200, receipt)

    def fulfill_lookup(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self.send_json(400, {"error": "bad_json"})
        query = str(payload.get("query", "")).strip()
        tx_hash = str(payload.get("tx_hash", ""))
        if not query:
            return self.send_json(400, {"error": "missing_query"})
        lead = find_lead(query)
        if not lead:
            return self.send_json(404, {"error": "no_match", "query": query})
        ok, detail = verify_lookup_payment(tx_hash)
        if not ok:
            return self.send_json(402, {"error": "payment_not_verified", "detail": detail,
                                        "pay": lookup_paywall_body(self, query)["how_to_pay"]})
        # Track for the 14-day test: log the sale
        sender = detail.get("sender", "unknown") if isinstance(detail, dict) else "unknown"
        try:
            log_path = os.path.join(BASE_DIR, "data", "lookup_sales.jsonl")
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "a") as f:
                f.write(json.dumps({
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "query": query, "tx_hash": tx_hash.lower(),
                    "sender": sender, "amount_usd": LOOKUP_PRICE_USD,
                }) + "\n")
        except Exception:
            pass
        return self.send_json(200, {
            "receipt": "ok",
            "service": "lead-lookup",
            "query": query,
            "tx_hash": tx_hash.lower(),
            "price_usd": LOOKUP_PRICE_USD,
            "lead": lead,
            "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "note": "Verified business contact delivered. Source URL included for provenance.",
        })

    def log_message(self, *a):
        pass  # quiet

LLMS_TXT = """# Scout Packs — Tiger Operations
Verified B2B lead packs and per-lead enrichment lookups, sold to AI agents over
x402 (USDC on Base, eip155:8453). Demand-probe pricing: $0.01 per lookup or pack.

## Services
- GET /lookup?query=<company or domain> -> 402: one verified business email +
  source URL for the company ($0.01 USDC).
- scout-pack-25: 25 leads, $0.01 USDC — delivered instantly as JSON after payment.
- scout-pack-50: 50 leads, $0.01 USDC — assembled on demand, delivered within 24h.
- scout-pack-100: 100 leads, $0.01 USDC — assembled on demand, delivered within 24h.
Each lead: company_name, city_state, category, contact_email (verified), source_url.

## How to buy
1. GET /lookup?query=<...> or GET /packs/{25,50,100} -> 402 with
   PAYMENT-REQUIRED (x402 v2) and X-PAYMENT-REQUIRED (v1) headers.
2. Standard x402: sign an EIP-3009 authorization for the exact USDC amount on
   Base and retry with X-PAYMENT (v1) or PAYMENT-SIGNATURE (v2). We verify +
   settle via facilitator and return the result with PAYMENT-RESPONSE /
   X-PAYMENT-RESPONSE.
   Manual fallback: send the exact USDC amount on Base to the payTo address,
   then POST /fulfill-lookup {"tx_hash":"0x...","query":"..."} -> verified contact.
   POST /fulfill {"tx_hash":"0x...","pack":"25"} -> pack JSON (25) or 24h order
   receipt (50/100).

## Discovery
- /.well-known/x402 — machine-readable payment terms (includes CDP Bazaar
  discovery extension on every paid route).
- /catalog — service list and prices.
- /packs/25/preview — redacted sample (emails masked).
- /skill.md — agent skill file for the lead lookup.
- /mcp — MCP streamable-HTTP endpoint (list_packs, buy_pack, lookup_lead).
"""

if __name__ == "__main__":
    # Bind 0.0.0.0 for container hosting (Railway, etc.); BIND env can override
    bind_host = os.environ.get("BIND", "0.0.0.0")
    print(f"scout-packs on {bind_host}:{PORT}  sales_enabled={SALES_ENABLED}", flush=True)
    ThreadingHTTPServer((bind_host, PORT), Handler).serve_forever()
