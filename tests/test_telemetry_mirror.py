#!/usr/bin/env python3
"""Fixture tests for the telemetry ledger mirror (GET /ops/ledger + mirror.py).

Expected answers are hand-written in telemetry/ACCEPTANCE.md (written before
this implementation) from the ledger shapes in server.py's log_sale() call
sites. Fixture tx hashes / wallets are invented test data, NOT real sales.

Run from the repo root:
    python3 -m unittest tests.test_telemetry_mirror -v

Everything runs on 127.0.0.1 with an ephemeral port; no external network.
"""

import importlib.util
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN = "test-token"

# Env must be set BEFORE the server module is exec'd: it reads
# SCOUTPACKS_OPS_TOKEN at import time (its config convention).
os.environ["SCOUTPACKS_OPS_TOKEN"] = TOKEN

spec = importlib.util.spec_from_file_location("scout_server_telemetry",
                                              os.path.join(BASE_DIR, "server.py"))
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

sys.path.insert(0, os.path.join(BASE_DIR, "telemetry"))
import mirror  # noqa: E402  (telemetry/mirror.py)

# ------------------------------------------------------------- fixtures
# Verbatim from telemetry/ACCEPTANCE.md.
LOOKUP_LINE_1 = {"method": "x402", "query": "acme.com", "tx_hash": "0xaaa1",
                 "sender": "0xwallet1", "amount_usd": 0.01, "replay": False,
                 "ts": "2026-10-10T01:02:03Z"}
LOOKUP_LINE_2 = {"ts": "2026-10-11T04:05:06Z", "query": "beta.com",
                 "tx_hash": "0xbbb2", "sender": "0xwallet2", "amount_usd": 0.01}
DOSSIER_LINE = {"method": "manual", "domain": "gamma.com", "tx_hash": "0xccc3",
                "sender": "0xwallet1", "amount_usd": 0.05, "ts": "2026-10-12T07:08:09Z"}
NEW_LOOKUP_LINE = {"method": "x402", "query": "delta.com", "tx_hash": "0xeee5",
                   "sender": "0xwallet2", "amount_usd": 0.01, "replay": False,
                   "ts": "2026-10-13T01:01:01Z"}
SETTLED = {"digestA": {"tx_hash": "0xaaa1", "payer": "0xwallet1", "ts": "2026-10-10T01:02:03Z"},
           "digestB": {"tx_hash": "0xddd4", "payer": "0xwallet3", "ts": "2026-10-12T09:10:11Z"}}
REDEEMED = ["0xbbb2", "0xccc3"]


def write_fixture_ledger(root):
    data = os.path.join(root, "data")
    os.makedirs(data, exist_ok=True)
    with open(os.path.join(data, "lookup_sales.jsonl"), "w") as f:
        f.write(json.dumps(LOOKUP_LINE_1) + "\n")
        f.write(json.dumps(LOOKUP_LINE_2) + "\n")
    with open(os.path.join(data, "dossier_sales.jsonl"), "w") as f:
        f.write(json.dumps(DOSSIER_LINE) + "\n")
    with open(os.path.join(data, "x402_settled.json"), "w") as f:
        json.dump(SETTLED, f)
    with open(os.path.join(data, "redeemed.json"), "w") as f:
        json.dump(REDEEMED, f)
    return data


def point_server_at(root):
    server.BASE_DIR = root
    server.X402_SETTLED_PATH = os.path.join(root, "data", "x402_settled.json")
    server.REDEEMED_PATH = os.path.join(root, "data", "redeemed.json")


def http_get(url, token=None):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    if token is not None:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


class RunningServer:
    def __enter__(self):
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%d" % self.port
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


class EndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="sp-fixture-")
        write_fixture_ledger(cls.tmp)
        point_server_at(cls.tmp)
        cls.rs = RunningServer().__enter__()
        cls.base = cls.rs.base

    @classmethod
    def tearDownClass(cls):
        cls.rs.__exit__()

    def test_correct_token_full_snapshot(self):
        code, body = http_get(self.base + "/ops/ledger", token=TOKEN)
        self.assertEqual(code, 200)
        self.assertEqual(body["sales"]["lookup"], [LOOKUP_LINE_1, LOOKUP_LINE_2])
        self.assertEqual(body["sales"]["dossier"], [DOSSIER_LINE])
        self.assertEqual(body["settled"], SETTLED)
        self.assertEqual(body["redeemed"], REDEEMED)
        self.assertEqual(body["counts"], {"sales_total": 3,
                                          "per_kind": {"dossier": 1, "lookup": 2},
                                          "settled": 2, "redeemed": 2,
                                          "unparseable_lines": 0})
        self.assertIsInstance(body["generated_at"], str)

    def test_no_token_401(self):
        code, body = http_get(self.base + "/ops/ledger")
        self.assertEqual(code, 401)
        self.assertEqual(body, {"error": "unauthorized"})

    def test_wrong_token_401(self):
        code, body = http_get(self.base + "/ops/ledger", token="wrong")
        self.assertEqual(code, 401)
        self.assertEqual(body, {"error": "unauthorized"})

    def test_since_filter(self):
        code, body = http_get(self.base + "/ops/ledger?since=2026-10-11T00:00:00Z",
                              token=TOKEN)
        self.assertEqual(code, 200)
        self.assertEqual(body["sales"]["lookup"], [LOOKUP_LINE_2])
        self.assertEqual(body["sales"]["dossier"], [DOSSIER_LINE])
        self.assertEqual(body["counts"]["sales_total"], 2)
        self.assertEqual(body["settled"], SETTLED)
        self.assertEqual(body["redeemed"], REDEEMED)

    def test_no_regressions_and_not_enumerated(self):
        code, body = http_get(self.base + "/health")
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        code, body = http_get(self.base + "/nonexistent")
        self.assertEqual(code, 404)
        self.assertEqual(body, {"error": "not_found"})
        code, body = http_get(self.base + "/catalog")
        self.assertEqual(code, 200)
        self.assertNotIn("/ops/ledger", json.dumps(body))


class EndpointDisabledTests(unittest.TestCase):
    def test_token_unset_is_404(self):
        saved = server.OPS_TOKEN
        server.OPS_TOKEN = ""
        try:
            with RunningServer() as rs:
                code, body = http_get(rs.base + "/ops/ledger", token=TOKEN)
                self.assertEqual(code, 404)
                self.assertEqual(body, {"error": "not_found"})
        finally:
            server.OPS_TOKEN = saved


class EndpointMalformedLineTests(unittest.TestCase):
    def test_unparseable_line_carried_verbatim(self):
        tmp = tempfile.mkdtemp(prefix="sp-fixture-bad-")
        data = write_fixture_ledger(tmp)
        with open(os.path.join(data, "dossier_sales.jsonl"), "a") as f:
            f.write("not json{\n")
        saved = (server.BASE_DIR, server.X402_SETTLED_PATH, server.REDEEMED_PATH)
        point_server_at(tmp)
        try:
            with RunningServer() as rs:
                code, body = http_get(rs.base + "/ops/ledger", token=TOKEN)
            self.assertEqual(code, 200)
            self.assertIn({"_raw": "not json{", "_parse_error": True},
                          body["sales"]["dossier"])
            self.assertEqual(body["counts"]["unparseable_lines"], 1)
        finally:
            server.BASE_DIR, server.X402_SETTLED_PATH, server.REDEEMED_PATH = saved


class MirrorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="sp-fixture-mirror-")
        cls.data = write_fixture_ledger(cls.tmp)
        point_server_at(cls.tmp)
        cls.rs = RunningServer().__enter__()
        cls.base = cls.rs.base
        cls.store = tempfile.mkdtemp(prefix="sp-store-")
        cls.paths = mirror.store_paths(cls.store)

    @classmethod
    def tearDownClass(cls):
        cls.rs.__exit__()

    def read(self, path):
        with open(path, "rb") as f:
            return f.read()

    def test_full_flow(self):
        # Run 1: everything is new (ACCEPTANCE #8)
        code, stats = mirror.run_mirror(store_dir=self.store, base_url=self.base, token=TOKEN)
        self.assertEqual(code, 0)
        self.assertEqual((stats["fetched"], stats["appended"], stats["duplicates_skipped"]), (3, 3, 0))
        lines = self.read(self.paths["sales"]).decode().strip().splitlines()
        self.assertEqual(len(lines), 3)
        recs = [json.loads(l) for l in lines]
        kinds = sorted(r["_kind"] for r in recs)
        self.assertEqual(kinds, ["dossier", "lookup", "lookup"])
        ids = [r["_sale_id"] for r in recs]
        self.assertEqual(len(set(ids)), 3)
        for sid in ids:
            self.assertEqual(len(sid), 64)
            self.assertTrue(all(c in "0123456789abcdef" for c in sid))
        bare = [{k: v for k, v in r.items() if not k.startswith("_")} for r in recs]
        self.assertIn(LOOKUP_LINE_1, bare)
        self.assertIn(LOOKUP_LINE_2, bare)
        self.assertIn(DOSSIER_LINE, bare)
        self.assertEqual(json.loads(self.read(self.paths["settled"])), SETTLED)
        self.assertEqual(json.loads(self.read(self.paths["redeemed"])), REDEEMED)
        state = json.loads(self.read(self.paths["state"]))
        self.assertEqual(state["total_sales_mirrored"], 3)
        self.assertTrue(state["last_success_at"])
        runlog = [json.loads(l) for l in self.read(self.paths["runs"]).decode().strip().splitlines()]
        self.assertTrue(runlog[-1]["ok"])
        self.assertEqual((runlog[-1]["appended"], runlog[-1]["duplicates_skipped"]), (3, 0))
        sales_after_run1 = self.read(self.paths["sales"])

        # Run 2: unchanged server -> byte-identical sales, all dupes (#9)
        code, stats = mirror.run_mirror(store_dir=self.store, base_url=self.base, token=TOKEN)
        self.assertEqual(code, 0)
        self.assertEqual((stats["appended"], stats["duplicates_skipped"]), (0, 3))
        self.assertEqual(self.read(self.paths["sales"]), sales_after_run1)

        # Run 3: one new server line -> exactly one append, prefix intact (#10)
        with open(os.path.join(self.data, "lookup_sales.jsonl"), "a") as f:
            f.write(json.dumps(NEW_LOOKUP_LINE) + "\n")
        code, stats = mirror.run_mirror(store_dir=self.store, base_url=self.base, token=TOKEN)
        self.assertEqual(code, 0)
        self.assertEqual((stats["appended"], stats["duplicates_skipped"]), (1, 3))
        after3 = self.read(self.paths["sales"])
        self.assertTrue(after3.startswith(sales_after_run1))
        self.assertEqual(len(after3.decode().strip().splitlines()), 4)

        # Run 4: wrong token -> exit 3, store untouched (#11)
        before = {k: self.read(p) for k, p in self.paths.items() if k != "runs"}
        code, _ = mirror.run_mirror(store_dir=self.store, base_url=self.base, token="wrong")
        self.assertEqual(code, 3)
        for k, p in self.paths.items():
            if k != "runs":
                self.assertEqual(self.read(p), before[k], k)
        runlog = [json.loads(l) for l in self.read(self.paths["runs"]).decode().strip().splitlines()]
        self.assertFalse(runlog[-1]["ok"])

        # Summary (#14): attributed 4 (lookup 3, dossier 1), $0.08, 2 senders
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(mirror.cmd_summary(store_dir=self.store), 0)
        out = buf.getvalue()
        self.assertIn("sales lines mirrored (attributed): 4", out)
        self.assertIn("attributed amount_usd total: $0.08", out)
        self.assertIn("distinct senders (sales lines): 2", out)
        self.assertIn("settled settlements (x402 index, NO endpoint attribution): 2", out)
        self.assertIn("redeemed manual tx hashes: 2", out)


class BadPayloadTests(unittest.TestCase):
    def test_malformed_payload_exit_4_store_untouched(self):
        from http.server import BaseHTTPRequestHandler

        class Stub(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps({"bogus": 1}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        httpd = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        store = tempfile.mkdtemp(prefix="sp-store-bad-")
        try:
            code, _ = mirror.run_mirror(store_dir=store,
                                        base_url="http://127.0.0.1:%d" % httpd.server_address[1],
                                        token=TOKEN)
            self.assertEqual(code, 4)
            paths = mirror.store_paths(store)
            self.assertFalse(os.path.exists(paths["sales"]))
            self.assertFalse(os.path.exists(paths["settled"]))
            runlog = [json.loads(l) for l in open(paths["runs"]).read().strip().splitlines()]
            self.assertFalse(runlog[-1]["ok"])
        finally:
            httpd.shutdown()
            httpd.server_close()


class NoTokenTests(unittest.TestCase):
    def test_no_token_exit_2(self):
        store = tempfile.mkdtemp(prefix="sp-store-notoken-")
        saved_env = os.environ.pop("SCOUTPACKS_OPS_TOKEN", None)
        saved_file = mirror.TOKEN_FILE
        mirror.TOKEN_FILE = os.path.join(store, "does-not-exist")
        try:
            code, _ = mirror.run_mirror(store_dir=store, base_url="http://127.0.0.1:1", token=None)
        finally:
            mirror.TOKEN_FILE = saved_file
            if saved_env is not None:
                os.environ["SCOUTPACKS_OPS_TOKEN"] = saved_env
        self.assertEqual(code, 2)
        paths = mirror.store_paths(store)
        self.assertFalse(os.path.exists(paths["sales"]))
        self.assertTrue(os.path.exists(paths["runs"]))  # bookkeeping only


if __name__ == "__main__":
    unittest.main()
