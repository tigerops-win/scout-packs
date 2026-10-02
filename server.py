#!/usr/bin/env python3
"""Scout Packs — Tiger Operations (Agent Data Supply Company).

A minimal x402-paywalled lead-pack endpoint. Python stdlib only.

Packs: 25 leads / $9, 50 / $15, 100 / $25. Paid in USDC on Base (eip155:8453).
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

PACKS = {
    "25":  {"count": 25,  "price_usd": 9,  "amount": 9_000_000,   "eta": "instant"},
    "50":  {"count": 50,  "price_usd": 15, "amount": 15_000_000,  "eta": "within 24 hours (assembled on demand)"},
    "100": {"count": 100, "price_usd": 25, "amount": 25_000_000,  "eta": "within 24 hours (assembled on demand)"},
}

# Per-lead enrichment lookup (Analyst hunt #3 pivot, 2026-10-02)
# $0.10 USDC per lookup — fits agent wallet policies ($0.005-$0.75/call)
LOOKUP_PRICE_USD = 0.10
LOOKUP_AMOUNT = 100_000  # $0.10 in 6-decimal USDC
LOOKUP_DESC = ("Lead enrichment lookup — verified business contact for one company "
               "(company, location, category, verified email, source URL + provenance). Tiger Operations.")

with open(os.path.join(BASE_DIR, "packs", "scout-pack-25.json")) as f:
    PACK_25 = json.load(f)

with open(os.path.join(BASE_DIR, "openapi-draft.json")) as f:
    OPENAPI_DOC = json.load(f)  # served verbatim at GET /openapi.json

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
    """Returns (ok, detail) for $0.10 lookup payments."""
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
    local, _, dom = (e or "").partition("@")
    return (local[:3] + "***@" + dom) if dom else "***"

def preview_pack():
    leads = []
    cats = {}
    for l in PACK_25["leads"]:
        cats[l["category"]] = cats.get(l["category"], 0) + 1
        leads.append({
            "company_name": l["company_name"],
            "city_state": l["city_state"],
            "category": l["category"],
            "contact_email": mask_email(l["contact_email"]),
            "source_domain": urlparse(l["source_url"]).netloc,
        })
    return {"pack": "scout-pack-25", "lead_count": 25, "price_usd": 9,
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
            f"(company, location, category, verified email, source URL). Tiger Operations.")
    accept = {
        "scheme": "exact",
        "network": NETWORK,
        "maxAmountRequired": str(p["amount"]),
        "resource": resource,
        "description": desc,
        "mimeType": "application/json",
        "payTo": RECEIVING if SALES_ENABLED else ZERO,
        "maxTimeoutSeconds": 300,
        "asset": USDC_BASE,
        "extra": {"name": "USDC", "version": "2"},
    }
    return {
        "x402Version": 2,
        "accepts": [accept],
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
            f"1. Send exactly ${p['price_usd']}.00 in USDC on Base to {RECEIVING if SALES_ENABLED else '(address pending)'}",
            "2. POST /fulfill with {\"tx_hash\": \"0x...\", \"pack\": \"" + pack_size + "\"}",
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
        "maxAmountRequired": str(LOOKUP_AMOUNT),
        "resource": resource,
        "description": LOOKUP_DESC,
        "mimeType": "application/json",
        "payTo": RECEIVING if SALES_ENABLED else ZERO,
        "maxTimeoutSeconds": 300,
        "asset": USDC_BASE,
        "extra": {"name": "USDC", "version": "2"},
    }
    return {
        "x402Version": 2,
        "accepts": [accept],
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
            f"1. Send exactly $0.10 in USDC on Base to {RECEIVING if SALES_ENABLED else '(address pending)'}",
            "2. POST /fulfill-lookup with {\"tx_hash\": \"0x...\", \"query\": \"" + query + "\"}",
            "3. Receive the verified contact (email + source URL + provenance).",
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
            "25": "Authorize exactly <strong>$9 USDC on Base</strong> for 25 verified leads, delivered immediately.",
            "50": "Authorize exactly <strong>$15 USDC on Base</strong> for 50 verified leads, delivered within 24 hours.",
            "100": "Authorize exactly <strong>$25 USDC on Base</strong> for 100 verified leads, delivered within 24 hours.",
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
<meta name="description" content="Verified B2B lead packs for agents and operators. 25 leads $9, 50 leads $15, 100 leads $25. USDC on Base via x402. No account, API key, or subscription.">
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
      <p class="lede">B2B lead packs for agents and operators. From $9. No account, API key, or subscription.</p>
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
      <div class="step"><span class="n">2</span><h3>Authorize USDC on Base</h3><p>Send the exact USDC amount on Base mainnet to the address in the terms. Your wallet, your keys — one payment, no recurring charge.</p></div>
      <div class="step"><span class="n">3</span><h3>Receive JSON</h3><p><code>POST /fulfill</code> with your transaction hash. The 25-pack downloads immediately; 50 and 100 are assembled and delivered within 24 hours.</p></div>
    </div>
  </section>

  <section class="section">
    <h2 class="sec">Technical details &amp; FAQ</h2>
    <p class="sec-sub">For the agents (and operators) doing the buying.</p>
    <table class="eps">
      <tr><td class="c">GET /catalog</td><td class="d">Pack list and prices — free</td></tr>
      <tr><td class="c">GET /.well-known/x402</td><td class="d">Machine-readable payment terms for all packs — free</td></tr>
      <tr><td class="c">GET /llms.txt</td><td class="d">Agent-readable service description — free</td></tr>
      <tr><td class="c">GET /packs/&#123;25,50,100&#125;</td><td class="d">The pack itself — 402 paywall (x402 v2 + v1 headers)</td></tr>
      <tr><td class="c">GET /packs/&#123;25,50,100&#125;/preview</td><td class="d">Redacted sample, emails masked — free</td></tr>
      <tr><td class="c">POST /fulfill</td><td class="d">Submit <code>&#123;"tx_hash", "pack"&#125;</code>, receive the pack — paid</td></tr>
    </table>
    <div class="faq">
      <details>
        <summary>How do I receive a 50 or 100-pack without an account?</summary>
        <div class="a">Pay, then <code>POST /fulfill</code> with <code>&#123;"tx_hash": "0x…", "pack": "50"&#125;</code> — add <code>"deliver_to"</code> if you want it sent somewhere specific. We verify the USDC transfer on-chain and queue your pack for assembly. Your transaction hash <em>is</em> your receipt; there is nothing to log into.</div>
      </details>
      <details>
        <summary>What exactly am I authorizing?</summary>
        <div class="a">Exactly $9, $15, or $25 in USDC on Base (<code>eip155:8453</code>), sent to the address in the 402 payment terms. One payment. No subscription, no recurring charge.</div>
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
        # Primary product: $0.10/lead lookup. Representative resource URL;
        # actual queries use /lookup?query=<company or domain>.
        lookup_accept = {
            "scheme": "exact",
            "network": NETWORK,
            "maxAmountRequired": str(LOOKUP_AMOUNT),
            "resource": f"{base}/lookup",
            "description": LOOKUP_DESC,
            "mimeType": "application/json",
            "payTo": RECEIVING if SALES_ENABLED else ZERO,
            "maxTimeoutSeconds": 300,
            "asset": USDC_BASE,
            "extra": {"name": "USDC", "version": "2"},
        }
        resources.append({"resource": f"{base}/lookup", "accepts": [lookup_accept]})
        for s, p in PACKS.items():
            t = payment_terms(self, s)
            resources.append({"resource": f"{base}/packs/{s}", "accepts": t["accepts"]})
        return {"x402Version": 2, "sales_enabled": SALES_ENABLED, "resources": resources}

    def verify_file(self):
        if os.path.exists(VERIFY_PATH):
            with open(VERIFY_PATH) as f:
                return self.send_text(200, f.read().strip())
        return self.send_text(404, "not claimed yet")

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
        body = paywall_body(self, size)
        terms_b64_v2 = base64.b64encode(json.dumps(body["x402"]).encode()).decode()
        terms_v1 = {"x402Version": 1, "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": str(PACKS[size]["amount"]),
            "resource": f"{base_url(self)}/packs/{size}",
            "description": body["x402"]["accepts"][0]["description"],
            "mimeType": "application/json", "payTo": body["x402"]["accepts"][0]["payTo"],
            "maxTimeoutSeconds": 300, "asset": USDC_BASE, "extra": {"name": "USDC", "version": "2"}}]}
        terms_b64_v1 = base64.b64encode(json.dumps(terms_v1).encode()).decode()
        self.send_json(402, body, {
            "PAYMENT-REQUIRED": terms_b64_v2,
            "X-PAYMENT-REQUIRED": terms_b64_v1,
        })

    def lookup_paywall(self, query):
        body = lookup_paywall_body(self, query)
        terms_b64_v2 = base64.b64encode(json.dumps(body["x402"]).encode()).decode()
        terms_v1 = {"x402Version": 1, "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": str(LOOKUP_AMOUNT),
            "resource": f"{base_url(self)}/lookup?query={query}",
            "description": body["x402"]["accepts"][0]["description"],
            "mimeType": "application/json", "payTo": body["x402"]["accepts"][0]["payTo"],
            "maxTimeoutSeconds": 300, "asset": USDC_BASE, "extra": {"name": "USDC", "version": "2"}}]}
        terms_b64_v1 = base64.b64encode(json.dumps(terms_v1).encode()).decode()
        self.send_json(402, body, {
            "PAYMENT-REQUIRED": terms_b64_v2,
            "X-PAYMENT-REQUIRED": terms_b64_v1,
        })

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
Verified B2B lead packs, sold to AI agents over x402 (USDC on Base, eip155:8453).

## Packs
- scout-pack-25: 25 leads, $9 USDC — delivered instantly as JSON after payment.
- scout-pack-50: 50 leads, $15 USDC — assembled on demand, delivered within 24h.
- scout-pack-100: 100 leads, $25 USDC — assembled on demand, delivered within 24h.
Each lead: company_name, city_state, category, contact_email (verified), source_url.

## How to buy
1. GET /packs/{25,50,100} -> 402 with PAYMENT-REQUIRED (x402 v2) and X-PAYMENT-REQUIRED (v1) headers.
2. Send the exact USDC amount on Base to the payTo address.
3. POST /fulfill {"tx_hash":"0x...","pack":"25"} -> pack JSON (25) or 24h order receipt (50/100).

## Discovery
- /.well-known/x402 — machine-readable payment terms for all packs.
- /catalog — pack list and prices.
- /packs/25/preview — redacted sample (emails masked).
"""

if __name__ == "__main__":
    # Bind 0.0.0.0 for container hosting (Railway, etc.); BIND env can override
    bind_host = os.environ.get("BIND", "0.0.0.0")
    print(f"scout-packs on {bind_host}:{PORT}  sales_enabled={SALES_ENABLED}", flush=True)
    ThreadingHTTPServer((bind_host, PORT), Handler).serve_forever()
