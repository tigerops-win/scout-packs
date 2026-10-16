#!/usr/bin/env python3
"""Fixture tests for the composite /dossier endpoint.

Expected answers are hand-written from the EXISTING endpoints' documented /
observed behaviour in server.py (see dossier/ACCEPTANCE.md, written before
this implementation). They are NOT computed by re-running the fusion logic.

Run from the repo root:
    python3 -m unittest tests.test_dossier -v
or:
    python3 tests/test_dossier.py

Live-upstream values (RDAP, the target's website, TLS) are asserted for
presence/type only — see [CHECK] notes in dossier/ACCEPTANCE.md.
"""

import base64
import importlib.util
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

spec = importlib.util.spec_from_file_location("scout_server", os.path.join(BASE_DIR, "server.py"))
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

# Known answer from email_pattern() in server.py: the hard-coded pattern list
# for any valid domain, rendered for example.com, in exact order.
EXAMPLE_COM_PATTERNS = [
    "first@example.com",
    "last@example.com",
    "first.last@example.com",
    "firstlast@example.com",
    "first_last@example.com",
    "first-last@example.com",
    "f.last@example.com",
    "flast@example.com",
    "firstl@example.com",
    "last.first@example.com",
]

SECTIONS = ["domain-intel", "tech-stack", "email-pattern", "ssl-check"]


class Fixture1InvalidDomain(unittest.TestCase):
    def test_exact_fused_output(self):
        expected = {
            "domain": "not-a-domain",
            # domain_intel() returns early on an invalid domain BEFORE it sets
            # intel["signals"] — so this section verbatim has no signals key;
            # the flag still surfaces in the top-level aggregated list via
            # the function's second return value. See ACCEPTANCE.md Fixture 1.
            "domain_intel": {"domain": "not-a-domain"},
            "tech_stack": {"domain": "not-a-domain", "technologies": [],
                           "server_header": "", "signals": ["invalid_domain"]},
            "email_pattern": {"domain": "not-a-domain", "patterns": [],
                              "mx_found": False, "catch_all_unknown": True,
                              "signals": ["invalid_domain"]},
            "ssl_check": {"domain": "not-a-domain", "valid": False, "issuer": "",
                          "subject": "", "expires": "", "days_remaining": None,
                          "tls_version": "", "signals": ["invalid_domain"]},
            "signals": ["invalid_domain"],
            "sections": SECTIONS,
        }
        self.assertEqual(server.dossier("not-a-domain"), expected)


class Fixture2ExampleCom(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = server.dossier("example.com")

    def test_email_pattern_known_answers(self):
        ep = self.out["email_pattern"]
        self.assertEqual(ep["domain"], "example.com")
        self.assertEqual(ep["patterns"], EXAMPLE_COM_PATTERNS)
        self.assertIs(ep["catch_all_unknown"], True)
        self.assertIsInstance(ep["mx_found"], bool)  # [CHECK] live DoH value

    def test_section_shapes(self):
        self.assertEqual(self.out["domain"], "example.com")
        self.assertEqual(self.out["sections"], SECTIONS)

        di = self.out["domain_intel"]
        self.assertEqual(di["domain"], "example.com")
        self.assertIsInstance(di["registration"], dict)
        self.assertIsInstance(di["dns"], dict)
        for k in ("nameservers", "nameserver_count", "a_records",
                  "a_record_count", "mx_found", "mx_hosts"):
            self.assertIn(k, di["dns"])
        self.assertIsInstance(di["signals"], list)

        ts = self.out["tech_stack"]
        self.assertEqual(ts["domain"], "example.com")
        self.assertIsInstance(ts["technologies"], list)
        self.assertIsInstance(ts["server_header"], str)
        self.assertIsInstance(ts["signals"], list)

        sc = self.out["ssl_check"]
        self.assertEqual(sc["domain"], "example.com")
        self.assertIsInstance(sc["valid"], bool)
        for k in ("issuer", "subject", "expires", "tls_version"):
            self.assertIsInstance(sc[k], str)
        self.assertTrue(sc["days_remaining"] is None or isinstance(sc["days_remaining"], int))
        self.assertIsInstance(sc["signals"], list)

    def test_aggregated_signals_cover_sections_without_dupes(self):
        agg = self.out["signals"]
        self.assertEqual(len(agg), len(set(agg)))
        for key in ("domain_intel", "tech_stack", "email_pattern", "ssl_check"):
            for sig in self.out[key]["signals"]:
                self.assertIn(sig, agg)


class Fixture3EmailFormInput(unittest.TestCase):
    def test_domain_extracted_for_all_sections(self):
        out = server.dossier("jane@example.com")
        self.assertEqual(out["domain"], "example.com")
        self.assertEqual(out["email_pattern"]["patterns"], EXAMPLE_COM_PATTERNS)
        self.assertEqual(out["email_pattern"]["domain"], "example.com")
        self.assertEqual(out["tech_stack"]["domain"], "example.com")
        self.assertEqual(out["ssl_check"]["domain"], "example.com")
        for key in ("domain_intel", "tech_stack", "email_pattern", "ssl_check"):
            self.assertNotIn("invalid_domain", out[key]["signals"])


class Fixture4CannedFusion(unittest.TestCase):
    """Canned source returns copied from the BAZAAR_* documented output
    examples in server.py; expected fusion is written out literally."""

    def setUp(self):
        self._orig = {n: getattr(server, n) for n in
                      ("domain_intel", "tech_stack", "email_pattern", "ssl_check")}

    def tearDown(self):
        for n, fn in self._orig.items():
            setattr(server, n, fn)

    def test_verbatim_sections_and_aggregation(self):
        server.domain_intel = lambda d: ({
            "domain": "acme.com",
            "registration": {"registrar": "Example Registrar", "created": "2001-05-03"},
            "dns": {"a": ["93.184.216.34"]},
            "domain_age_days": 9280,
            "signals": ["aged-domain"],
        }, ["aged-domain"])
        server.tech_stack = lambda d: ({
            "domain": "acme.com", "technologies": ["nginx", "wordpress"],
            "server_header": "nginx",
        }, {"invalid_domain": False, "request_failed": False, "parse_failed": False})
        server.email_pattern = lambda d: ({
            "domain": "acme.com", "patterns": ["{first}.{last}"],
            "mx_found": True, "catch_all_unknown": False,
        }, {"invalid_domain": False, "dns_query_failed": False})
        server.ssl_check = lambda d: ({
            "domain": "acme.com", "valid": True, "issuer": "Let's Encrypt",
            "subject": "", "expires": "2027-01-01", "days_remaining": 85,
            "tls_version": "TLSv1.3",
        }, {"invalid_domain": False, "expired": False,
            "expiring_soon_lt_30d": False, "self_signed": False,
            "connection_failed": False})

        expected = {
            "domain": "acme.com",
            "domain_intel": {
                "domain": "acme.com",
                "registration": {"registrar": "Example Registrar", "created": "2001-05-03"},
                "dns": {"a": ["93.184.216.34"]},
                "domain_age_days": 9280,
                "signals": ["aged-domain"],
            },
            "tech_stack": {
                "domain": "acme.com", "technologies": ["nginx", "wordpress"],
                "server_header": "nginx", "signals": [],
            },
            "email_pattern": {
                "domain": "acme.com", "patterns": ["{first}.{last}"],
                "mx_found": True, "catch_all_unknown": False, "signals": [],
            },
            "ssl_check": {
                "domain": "acme.com", "valid": True, "issuer": "Let's Encrypt",
                "subject": "", "expires": "2027-01-01", "days_remaining": 85,
                "tls_version": "TLSv1.3", "signals": [],
            },
            "signals": ["aged-domain"],
            "sections": SECTIONS,
        }
        self.assertEqual(server.dossier("acme.com"), expected)

    def test_cross_section_dedup(self):
        server.domain_intel = lambda d: (
            {"domain": "acme.com", "signals": ["shared-flag"]}, ["shared-flag"])
        server.tech_stack = lambda d: (
            {"domain": "acme.com", "technologies": [], "server_header": ""},
            {"shared-flag": True, "invalid_domain": False})
        server.email_pattern = lambda d: (
            {"domain": "acme.com", "patterns": [], "mx_found": False,
             "catch_all_unknown": True}, {"invalid_domain": False})
        server.ssl_check = lambda d: (
            {"domain": "acme.com", "valid": False, "issuer": "", "subject": "",
             "expires": "", "days_remaining": None, "tls_version": ""},
            {"invalid_domain": False})
        out = server.dossier("acme.com")
        self.assertEqual(out["signals"], ["shared-flag"])
        self.assertEqual(out["tech_stack"]["signals"], ["shared-flag"])


class HttpBehaviour(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _req(self, path, method="GET", payload=None):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, r.headers, json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            return e.code, e.headers, json.loads(e.read().decode() or "{}")

    def test_constants(self):
        self.assertEqual(server.DOSSIER_PRICE_USD, 0.05)
        self.assertEqual(server.DOSSIER_AMOUNT, 50000)

    def test_unpaid_402_and_headers(self):
        status, headers, body = self._req("/dossier?domain=example.com")
        self.assertEqual(status, 402)
        self.assertEqual(body["error"], "payment_required")
        self.assertEqual(body["service"], "dossier")
        self.assertEqual(body["domain"], "example.com")
        self.assertEqual(body["price_usd"], 0.05)
        self.assertEqual(body["currency"], "USDC")
        self.assertEqual(body["network"], "eip155:8453")
        self.assertIn("/fulfill-dossier", body["how_to_pay"][1])

        v2 = json.loads(base64.b64decode(headers["PAYMENT-REQUIRED"]).decode())
        self.assertEqual(v2["x402Version"], 2)
        self.assertEqual(v2["accepts"][0]["amount"], "50000")
        self.assertIn("bazaar", v2["extensions"])
        v1 = json.loads(base64.b64decode(headers["X-PAYMENT-REQUIRED"]).decode())
        self.assertEqual(v1["x402Version"], 1)
        self.assertEqual(v1["accepts"][0]["maxAmountRequired"], "50000")

    def test_enumeration_surfaces(self):
        _, _, catalog = self._req("/catalog")
        hits = [s for s in catalog["per_call_services"] if s["path"] == "/dossier"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["price_usd"], 0.05)

        _, _, wk = self._req("/.well-known/x402")
        hits = [r for r in wk["resources"] if r["resource"].endswith("/dossier")]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["accepts"][0]["amount"], "50000")

        _, _, sample = self._req("/sample")
        self.assertEqual(sample["pricing"]["per_call"]["/dossier"], 0.05)

        _, _, oa = self._req("/openapi.json")
        self.assertIn("/dossier", oa["paths"])
        params = oa["paths"]["/dossier"]["get"]["parameters"]
        self.assertEqual(params[0]["name"], "domain")
        self.assertIn("/fulfill-dossier", oa["paths"])

    def test_fulfill_dossier_manual_path_wired(self):
        status, _, body = self._req("/fulfill-dossier", method="POST", payload={})
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "missing_domain")

        status, _, body = self._req(
            "/fulfill-dossier", method="POST",
            payload={"domain": "example.com", "tx_hash": "not-a-hash"})
        self.assertEqual(status, 402)
        self.assertEqual(body["error"], "payment_not_verified")
        self.assertTrue(str(body["detail"]).startswith(("sales_paused", "bad_tx_hash")))

    def test_source_endpoints_unchanged(self):
        for path, amount in (("/domain-intel?domain=example.com", "20000"),
                             ("/tech-stack?domain=example.com", "10000"),
                             ("/email-pattern?domain=example.com", "10000"),
                             ("/ssl-check?domain=example.com", "10000")):
            status, headers, _ = self._req(path)
            self.assertEqual(status, 402, path)
            v2 = json.loads(base64.b64decode(headers["PAYMENT-REQUIRED"]).decode())
            self.assertEqual(v2["accepts"][0]["amount"], amount, path)


class McpTool(unittest.TestCase):
    def test_dossier_tool_defined(self):
        with open(os.path.join(BASE_DIR, "mcp", "scout_packs_mcp.py")) as f:
            src = f.read()
        self.assertIn("def dossier(domain: str)", src)
        self.assertIn('"/dossier", "/fulfill-dossier"', src)
        self.assertIn("$0.05 USDC per call", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
