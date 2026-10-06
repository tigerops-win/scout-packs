#!/usr/bin/env python3
"""Scout Packs MCP server — Tiger Operations (Agent Data Supply Company).

Exposes Scout Packs (verified B2B lead packs, sold over x402 / USDC on Base)
to MCP clients so AI agents can discover and buy packs from inside their
own tooling.

Endpoint: the sibling Scout Packs HTTP server. Configure with BASE_URL
(default http://localhost:8000). This MCP server only ever talks to BASE_URL.

Tools:
  list_packs  — free. Pack sizes, prices, and a redacted sample.
  buy_pack    — returns the exact x402 payment requirements and the step-by-step
                flow for buying a pack. The USDC payment itself is executed by
                the buying agent's own wallet against the endpoint; this tool
                never moves funds and never holds keys.
  lookup_lead — $0.01/lookup (demand probe, 2026-10-04). Enrich one company by
                name or domain; returns the verified contact (email + source URL
                + provenance) after x402 payment. This is the primary per-call
                product.

Run:  BASE_URL=http://localhost:8000 .venv/bin/python scout_packs_mcp.py
"""

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict

from mcp.server.mcpserver import MCPServer

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")

FULFILLMENT_NOTE = (
    "Fulfillment: packs are assembled and verified by the Tiger Operations "
    "operator team and delivered within 24 hours of payment confirmation."
)

# Hard fallback mirrors the endpoint's documented catalog. Used only when the
# endpoint is unreachable; every response is labeled so it is never mistaken
# for live data.
FALLBACK_PACKS = {
    "25": {"leads": 25, "price_usd": 0.01, "currency": "USDC",
           "network": "eip155:8453", "fulfillment_eta": "instant"},
    "50": {"leads": 50, "price_usd": 0.01, "currency": "USDC",
           "network": "eip155:8453",
           "fulfillment_eta": "within 24 hours (assembled on demand)"},
    "100": {"leads": 100, "price_usd": 0.01, "currency": "USDC",
            "network": "eip155:8453",
            "fulfillment_eta": "within 24 hours (assembled on demand)"},
}

mcp = MCPServer("scout-packs")


def _get(path: str) -> Dict[str, Any]:
    """GET {BASE_URL}{path}; returns dict with ok/data or ok/error."""
    url = BASE_URL + path
    req = urllib.request.Request(
        url, headers={"User-Agent": "scout-packs-mcp/1.0", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return {"ok": True, "status": r.status,
                    "data": json.loads(r.read().decode() or "{}")}
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode() or "{}")
        except Exception:
            body = {"error": "non_json_body"}
        return {"ok": False, "status": e.code, "data": body}
    except Exception as e:
        return {"ok": False, "status": 0, "data": {"error": "endpoint_unreachable",
                                                  "detail": str(e)[:200]}}


def _pack_key(size: str) -> str:
    s = str(size).strip()
    if s not in ("25", "50", "100"):
        raise ValueError("pack must be one of 25, 50, 100")
    return s


@mcp.tool()
def list_packs() -> str:
    """B2B lead packs for sale: sizes, prices, and a redacted sample. Free.
    Verified business lead enrichment batches (company, contact, verified email)."""
    lines = ["# Scout Packs — Tiger Operations", ""]
    catalog = _get("/catalog")
    if catalog["ok"]:
        d = catalog["data"]
        lines.append(f"Seller: {d.get('seller', 'Tiger Operations')}")
        if not d.get("sales_enabled", False):
            lines.append("Sales status: PAUSED — seller receiving address not configured yet. "
                         "Browsing is free; do not send funds.")
        else:
            lines.append("Sales status: LIVE — accepting USDC on Base.")
        lines.append("")
        for pid, p in d.get("packs", {}).items():
            lines.append(f"- {pid}: {p['leads']} verified B2B leads, "
                         f"${p['price_usd']} {p.get('currency', 'USDC')} "
                         f"({p.get('network', 'eip155:8453')}) — {p.get('fulfillment_eta', '')}")
        source_note = ""
    else:
        lines.append("Sales status: UNKNOWN — endpoint unreachable; showing documented catalog "
                     "(verify at the live endpoint before paying).")
        lines.append("")
        for s, p in FALLBACK_PACKS.items():
            lines.append(f"- scout-pack-{s}: {p['leads']} verified B2B leads, "
                         f"${p['price_usd']} {p['currency']} ({p['network']}) — {p['fulfillment_eta']}")
        source_note = " (documented fallback)"
    lines.append("")
    lines.append("## Redacted sample (emails masked)" + source_note)
    preview = _get("/packs/25/preview")
    if preview["ok"]:
        d = preview["data"]
        lines.append(f"Pack: {d.get('pack')}, leads: {d.get('lead_count')}, "
                     f"price: ${d.get('price_usd')}")
        lines.append(f"Categories: {d.get('category_breakdown')}")
        for lead in d.get("leads", [])[:5]:
            lines.append(f"- {lead['company_name']} ({lead['city_state']}, {lead['category']}) — "
                         f"{lead['contact_email']} via {lead['source_domain']}")
        lines.append(f"... and {d.get('lead_count', 25) - 5} more in the full pack. "
                     f"Full redacted sample: {BASE_URL}/packs/25/preview")
    else:
        lines.append("Sample temporarily unavailable from the endpoint. "
                     f"Try {BASE_URL}/packs/25/preview directly.")
    lines.append("")
    lines.append(FULFILLMENT_NOTE)
    return "\n".join(lines)


@mcp.tool()
def buy_pack(pack: str) -> str:
    """Get the exact x402 payment requirements and step-by-step buying flow
    for a Scout Pack. pack: "25", "50", or "100".
    Returns what the buying agent must do; the agent's own wallet executes
    the USDC payment against the endpoint."""
    size = _pack_key(pack)
    res = _get(f"/packs/{size}")
    if not res["ok"] and res["status"] != 402:
        return ("\n".join([
            "# buy_pack failed",
            f"Could not reach the payment terms for scout-pack-{size}: "
            f"{res['data'].get('error', 'unknown')} (HTTP {res['status']}).",
            f"Endpoint: {BASE_URL}. No payment should be attempted.",
            "",
            FULFILLMENT_NOTE,
        ]))
    body = res["data"]
    lines = [f"# Buy scout-pack-{size}", ""]
    lines.append(f"Pack: {size} verified B2B leads — "
                 f"${body.get('price_usd')} {body.get('currency', 'USDC')} "
                 f"on {body.get('network', 'eip155:8453')}")
    lines.append(f"Fulfillment: {body.get('fulfillment', '')}")
    lines.append("")
    sales = body.get("sales_enabled", False)
    accepts = (body.get("x402", {}) or {}).get("accepts", [{}])[0]
    pay_to = accepts.get("payTo", "")
    amount_raw = accepts.get("maxAmountRequired", "")
    try:
        amount_usdc = int(amount_raw) / 1_000_000
    except (TypeError, ValueError):
        amount_usdc = None
    zero = "0x0000000000000000000000000000000000000000"
    if not sales or not pay_to or pay_to.lower() == zero:
        lines.append("SALES PAUSED: the seller's receiving address is not configured yet. "
                     "Do NOT send any funds. Check back later or contact the operator.")
        lines.append("")
        lines.append(FULFILLMENT_NOTE)
        return "\n".join(lines)
    lines.append("## What your agent must do (step by step)")
    lines.append(f"1. From a wallet you control, send exactly "
                 f"${amount_usdc:.2f} USDC on Base (eip155:8453) to:")
    lines.append(f"   {pay_to}")
    lines.append(f"   Asset contract (Base USDC): {accepts.get('asset', '')}")
    lines.append("2. Wait for the transaction to confirm on-chain.")
    lines.append("3. POST to the endpoint to redeem:")
    lines.append(f"   POST {BASE_URL}/fulfill")
    lines.append('   Body: {"tx_hash": "0x...", "pack": "' + size + '"}')
    lines.append("   (Optionally add \"deliver_to\" with a delivery target for 50/100 packs.)")
    lines.append("4. The endpoint verifies the USDC transfer on-chain and responds with:")
    lines.append("   - pack 25: the full lead JSON (company, city/state, category, "
                 "verified email, source URL);")
    lines.append("   - pack 50/100: an order receipt with order_id; the assembled pack is "
                 "delivered within 24h.")
    lines.append("")
    lines.append("Payment rules enforced by the endpoint: exact-amount (or greater) USDC "
                 "transfer to the payTo address; tx hashes are single-use (replay-protected); "
                 "transactions older than 30 days are rejected.")
    lines.append("")
    lines.append(FULFILLMENT_NOTE)
    return "\n".join(lines)


@mcp.tool()
def lookup_lead(query: str) -> str:
    """B2B lead enrichment: contact lookup by company name or domain. Enrich one
    lead with a verified business email + source URL. $0.01 USDC per lookup.
    Returns the x402 payment requirements; your agent's wallet executes the payment.
    Example: lookup_lead(query="Acme Corp") or lookup_lead(query="acme.com")"""
    q = (query or "").strip()
    if not q:
        return "Error: query is required. Provide a company name or domain."
    from urllib.parse import quote_plus
    res = _get(f"/lookup?query={quote_plus(q)}")
    if res["ok"]:
        # Should not happen (lookup always 402s on match, 404 on no-match)
        return f"Unexpected response: {res['data']}"
    if res["status"] == 404:
        body = res["data"]
        return "\n".join([
            "# lookup_lead — no match",
            f"No verified contact found for '{q}' in the current database.",
            f"Database: 100+ verified B2B leads and growing.",
            "Try a different company name or domain.",
        ])
    if res["status"] != 402:
        return "\n".join([
            "# lookup_lead failed",
            f"Endpoint error: {res['data'].get('error', 'unknown')} (HTTP {res['status']}).",
            f"Endpoint: {BASE_URL}. No payment should be attempted.",
        ])
    body = res["data"]
    lines = [f"# Lead lookup: '{q}'", ""]
    lines.append(f"Price: ${body.get('price_usd', 0.01)} {body.get('currency', 'USDC')} "
                 f"on {body.get('network', 'eip155:8453')}")
    lines.append("")
    accepts = (body.get("x402", {}) or {}).get("accepts", [{}])[0]
    pay_to = accepts.get("payTo", "")
    amount_raw = accepts.get("maxAmountRequired", "10000")
    try:
        amount_usdc = int(amount_raw) / 1_000_000
    except (TypeError, ValueError):
        amount_usdc = 0.01
    zero = "0x0000000000000000000000000000000000000000"
    if not pay_to or pay_to.lower() == zero:
        lines.append("SALES PAUSED. Do NOT send funds.")
        return "\n".join(lines)
    lines.append("## What your agent must do")
    lines.append(f"1. Send exactly ${amount_usdc:.2f} USDC on Base to:")
    lines.append(f"   {pay_to}")
    lines.append(f"   Asset: {accepts.get('asset', '')}")
    lines.append("2. Wait for confirmation, then POST:")
    lines.append(f"   POST {BASE_URL}/fulfill-lookup")
    lines.append(f'   Body: {{"tx_hash": "0x...", "query": "{q}"}}')
    lines.append("3. Receive the verified contact (company, location, category, "
                 "verified email, source URL + provenance).")
    lines.append("")
    lines.append("Payment is verified on-chain; tx hashes are single-use.")
    return "\n".join(lines)


def _x402_instructions(title: str, path: str, fulfill_path: str,
                       field_name: str, field_value: str,
                       result_desc: str, service_label: str) -> str:
    """Shared 402-flow renderer for the per-call x402 endpoints."""
    from urllib.parse import quote_plus
    q = (field_value or "").strip()
    if not q:
        return f"Error: {field_name} is required."
    res = _get(f"{path}?{field_name}={quote_plus(q)}")
    if res["ok"]:
        return f"Unexpected response: {res['data']}"
    if res["status"] != 402:
        return "\n".join([
            f"# {service_label} failed",
            f"Endpoint error: {res['data'].get('error', 'unknown')} (HTTP {res['status']}).",
            f"Endpoint: {BASE_URL}. No payment should be attempted.",
        ])
    body = res["data"]
    lines = [f"# {title}: '{q}'", ""]
    lines.append(f"Price: ${body.get('price_usd', 0.01)} {body.get('currency', 'USDC')} "
                 f"on {body.get('network', 'eip155:8453')}")
    lines.append("")
    accepts = (body.get("x402", {}) or {}).get("accepts", [{}])[0]
    pay_to = accepts.get("payTo", "")
    amount_raw = accepts.get("maxAmountRequired", "10000")
    try:
        amount_usdc = int(amount_raw) / 1_000_000
    except (TypeError, ValueError):
        amount_usdc = 0.01
    zero = "0x0000000000000000000000000000000000000000"
    if not pay_to or pay_to.lower() == zero:
        lines.append("SALES PAUSED. Do NOT send funds.")
        return "\n".join(lines)
    lines.append("## What your agent must do")
    lines.append(f"1. Send exactly ${amount_usdc:.2f} USDC on Base to:")
    lines.append(f"   {pay_to}")
    lines.append(f"   Asset: {accepts.get('asset', '')}")
    lines.append("2. Wait for confirmation, then POST:")
    lines.append(f"   POST {BASE_URL}{fulfill_path}")
    lines.append(f'   Body: {{"tx_hash": "0x...", "{field_name}": "{q}"}}')
    lines.append(f"3. {result_desc}")
    lines.append("")
    lines.append("Payment is verified on-chain; tx hashes are single-use.")
    return "\n".join(lines)


@mcp.tool()
def tech_stack(domain: str) -> str:
    """Detect the web technologies powering a domain (CMS, frameworks, analytics,
    CDNs) from HTTP headers and page markup, with per-technology confidence and
    evidence. $0.01 USDC per call.
    Returns the x402 payment requirements; your agent's wallet executes the payment.
    Example: tech_stack(domain="acme.com")"""
    return _x402_instructions(
        "Tech-stack detection", "/tech-stack", "/fulfill-tech-stack",
        "domain", domain,
        "Receive the detected technology stack with confidence scores and evidence.",
        "tech_stack")


@mcp.tool()
def email_pattern(domain: str) -> str:
    """Find the most likely corporate email address patterns for a domain
    (first.last@, first@, flast@, ...) plus MX verification that the domain can
    receive mail. $0.01 USDC per call.
    Returns the x402 payment requirements; your agent's wallet executes the payment.
    Example: email_pattern(domain="acme.com")"""
    return _x402_instructions(
        "Email-pattern finder", "/email-pattern", "/fulfill-email-pattern",
        "domain", domain,
        "Receive ranked email patterns plus MX verification.",
        "email_pattern")


@mcp.tool()
def ssl_check(domain: str) -> str:
    """Check a domain's SSL/TLS certificate: issuer, expiry date, days remaining,
    TLS version, and risk flags (expired, expiring soon, self-signed).
    $0.01 USDC per call.
    Returns the x402 payment requirements; your agent's wallet executes the payment.
    Example: ssl_check(domain="acme.com")"""
    return _x402_instructions(
        "SSL certificate check", "/ssl-check", "/fulfill-ssl-check",
        "domain", domain,
        "Receive certificate details and risk flags.",
        "ssl_check")


def main() -> None:
    """Entry point for the `scout-packs-mcp` console script (uvx/pipx)."""
    mcp.run()


if __name__ == "__main__":
    main()
