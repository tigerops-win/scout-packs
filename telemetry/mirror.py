#!/usr/bin/env python3
"""Scout Packs telemetry ledger mirror — Tiger Operations.

Pulls the service's own sales-ledger state through its authenticated ops
surface (GET /ops/ledger, see telemetry/SPEC.md) into a LOCAL append-only
store, so per-endpoint sales attribution survives independently of the
Railway production volume.

Usage:
    python3 telemetry/mirror.py           # one mirror run
    python3 telemetry/mirror.py summary   # read-only report from local store

Config (env, repo conventions):
    SCOUTPACKS_BASE_URL   default https://scout-packs-production.up.railway.app
    SCOUTPACKS_OPS_TOKEN  ops token; else read from ~/.config/scout-packs/ops-token

Local store (telemetry/store/, gitignored — runtime state like data/):
    sales.jsonl    append-only unified sales ledger (server record verbatim
                   + "_kind" + "_sale_id"); re-runs append nothing twice
    settled.json   merged x402 settlement index (union; server wins conflicts)
    redeemed.json  merged sorted list of manually redeemed tx hashes
    state.json     run bookkeeping (atomic tmp+replace)
    runs.jsonl     append-only run log (success AND failure entries)

Exit codes: 0 ok · 2 config (no token) · 3 HTTP/auth failure · 4 bad payload.
On any failure the store's data files are untouched (fail closed); only
runs.jsonl / state.json bookkeeping records the attempt.
"""

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
STORE_DIR = os.environ.get("SCOUTPACKS_MIRROR_DIR", "").strip() or os.path.join(HERE, "store")
DEFAULT_BASE = "https://scout-packs-production.up.railway.app"
TOKEN_FILE = os.path.expanduser("~/.config/scout-packs/ops-token")

EXIT_OK, EXIT_CONFIG, EXIT_HTTP, EXIT_PAYLOAD = 0, 2, 3, 4


def now_ts():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def resolve_token():
    tok = os.environ.get("SCOUTPACKS_OPS_TOKEN", "").strip()
    if tok:
        return tok
    try:
        with open(TOKEN_FILE) as f:
            return f.read().strip()
    except OSError:
        return ""


def fetch_snapshot(base_url, token, timeout=30):
    """GET {base}/ops/ledger. Returns decoded dict. Raises urllib errors /
    ValueError on a malformed payload."""
    req = urllib.request.Request(
        base_url.rstrip("/") + "/ops/ledger",
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/json",
                 "User-Agent": "scout-packs-telemetry-mirror/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        payload = json.load(r)
    if not isinstance(payload, dict):
        raise ValueError("payload is not a JSON object")
    for key in ("sales", "settled", "redeemed", "counts"):
        if key not in payload:
            raise ValueError("payload missing key: " + key)
    if not isinstance(payload["sales"], dict) or not isinstance(payload["settled"], dict) \
            or not isinstance(payload["redeemed"], list):
        raise ValueError("payload field types wrong")
    return payload


def sale_id(kind, record):
    """Dedup key: sha256 of kind + canonical JSON of the verbatim record."""
    canon = json.dumps(record, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((kind + "|" + canon).encode()).hexdigest()


def store_paths(store_dir):
    return {
        "sales": os.path.join(store_dir, "sales.jsonl"),
        "settled": os.path.join(store_dir, "settled.json"),
        "redeemed": os.path.join(store_dir, "redeemed.json"),
        "state": os.path.join(store_dir, "state.json"),
        "runs": os.path.join(store_dir, "runs.jsonl"),
    }


def load_existing_sale_ids(sales_path):
    ids = set()
    try:
        with open(sales_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict) and rec.get("_sale_id"):
                    ids.add(rec["_sale_id"])
    except OSError:
        pass
    return ids


def load_json_file(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def write_json_atomic(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


def append_run_log(paths, entry):
    os.makedirs(os.path.dirname(paths["runs"]), exist_ok=True)
    entry = dict(entry)
    entry["ts"] = now_ts()
    with open(paths["runs"], "a") as f:
        f.write(json.dumps(entry) + "\n")


def merge_snapshot(store_dir, payload):
    """Merge a validated snapshot into the store. Returns run stats.
    Only called after the payload has been fully validated, so a bad
    payload can never half-write the store."""
    paths = store_paths(store_dir)
    os.makedirs(store_dir, exist_ok=True)
    existing_ids = load_existing_sale_ids(paths["sales"])
    fetched, appended, dupes = 0, 0, 0
    new_lines = []
    for kind in sorted(payload["sales"]):
        records = payload["sales"][kind]
        if not isinstance(records, list):
            raise ValueError("sales[%r] is not a list" % kind)
        for rec in records:
            if not isinstance(rec, dict):
                raise ValueError("sales record is not an object")
            fetched += 1
            sid = sale_id(kind, rec)
            if sid in existing_ids:
                dupes += 1
                continue
            existing_ids.add(sid)
            out = dict(rec)
            out["_kind"] = kind
            out["_sale_id"] = sid
            new_lines.append(json.dumps(out, sort_keys=True))
            appended += 1
    # settled: union; server record wins on key conflict (count them)
    settled = load_json_file(paths["settled"], {})
    if not isinstance(settled, dict):
        settled = {}
    conflicts = 0
    for k, v in payload["settled"].items():
        if k in settled and settled[k] != v:
            conflicts += 1
        settled[k] = v
    redeemed = sorted(set(load_json_file(paths["redeemed"], []) or []) | set(payload["redeemed"]))
    # All validation done above this line; writes start here.
    if new_lines:
        with open(paths["sales"], "a") as f:
            for line in new_lines:
                f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
    write_json_atomic(paths["settled"], settled)
    write_json_atomic(paths["redeemed"], redeemed)
    state = load_json_file(paths["state"], {})
    if not isinstance(state, dict):
        state = {}
    total = len(load_existing_sale_ids(paths["sales"]))
    state.update({
        "last_run_at": now_ts(),
        "last_success_at": now_ts(),
        "source_counts": payload.get("counts", {}),
        "total_sales_mirrored": total,
        "settled_total": len(settled),
        "redeemed_total": len(redeemed),
    })
    write_json_atomic(paths["state"], state)
    return {"fetched": fetched, "appended": appended, "duplicates_skipped": dupes,
            "settled_total": len(settled), "redeemed_total": len(redeemed),
            "settled_conflicts": conflicts, "total_sales_mirrored": total}


def run_mirror(store_dir=None, base_url=None, token=None):
    """One mirror run. Returns (exit_code, stats_or_error_dict)."""
    store_dir = store_dir or STORE_DIR
    paths = store_paths(store_dir)
    token = token if token is not None else resolve_token()
    if not token:
        append_run_log(paths, {"ok": False, "error": "no_ops_token_configured"})
        return EXIT_CONFIG, {"error": "no_ops_token_configured"}
    base_url = base_url or os.environ.get("SCOUTPACKS_BASE_URL", "").strip() or DEFAULT_BASE
    try:
        payload = fetch_snapshot(base_url, token)
    except urllib.error.HTTPError as e:
        append_run_log(paths, {"ok": False, "error": "http_%d" % e.code})
        return EXIT_HTTP, {"error": "http_%d" % e.code}
    except ValueError as e:
        # Undecodable JSON or a payload missing the ledger keys: the server
        # answered, but not with a ledger snapshot.
        append_run_log(paths, {"ok": False, "error": "bad_payload:%s" % e})
        return EXIT_PAYLOAD, {"error": "bad_payload:%s" % e}
    except Exception as e:
        append_run_log(paths, {"ok": False, "error": "fetch_failed:%s" % type(e).__name__})
        return EXIT_HTTP, {"error": "fetch_failed:%s" % type(e).__name__}
    try:
        stats = merge_snapshot(store_dir, payload)
    except ValueError as e:
        append_run_log(paths, {"ok": False, "error": "bad_payload:%s" % e})
        return EXIT_PAYLOAD, {"error": "bad_payload:%s" % e}
    append_run_log(paths, dict({"ok": True}, **stats))
    return EXIT_OK, stats


def cmd_summary(store_dir=None):
    """Read-only report from the LOCAL store only. Prints attributed sales
    and settled settlements as separate lines — they count different things
    (sales lines include manual redemptions and x402 replays), so no
    reconciliation figure is invented."""
    store_dir = store_dir or STORE_DIR
    paths = store_paths(store_dir)
    per_kind, per_kind_usd, senders = {}, {}, set()
    total = 0
    try:
        with open(paths["sales"]) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if not isinstance(rec, dict):
                    continue
                kind = rec.get("_kind", "?")
                per_kind[kind] = per_kind.get(kind, 0) + 1
                amt = rec.get("amount_usd")
                if isinstance(amt, (int, float)):
                    per_kind_usd[kind] = per_kind_usd.get(kind, 0.0) + float(amt)
                if rec.get("sender"):
                    senders.add(str(rec["sender"]))
                total += 1
    except OSError:
        pass
    settled = load_json_file(paths["settled"], {})
    redeemed = load_json_file(paths["redeemed"], [])
    state = load_json_file(paths["state"], {})
    grand = sum(per_kind_usd.values())
    print("Scout Packs telemetry — LOCAL mirror summary")
    print("store: %s" % store_dir)
    print("last_success_at: %s" % (state.get("last_success_at") or "[UNKNOWN — never mirrored]"))
    print("sales lines mirrored (attributed): %d" % total)
    for kind in sorted(per_kind):
        print("  %-16s %4d sales   $%.2f" % (kind, per_kind[kind], per_kind_usd.get(kind, 0.0)))
    print("attributed amount_usd total: $%.2f" % grand)
    print("distinct senders (sales lines): %d" % len(senders))
    print("settled settlements (x402 index, NO endpoint attribution): %d"
          % (len(settled) if isinstance(settled, dict) else 0))
    print("redeemed manual tx hashes: %d" % (len(redeemed) if isinstance(redeemed, list) else 0))
    print("note: sales lines and settled settlements count different things "
          "(manual redemptions + x402 replays appear as sales lines; a settlement "
          "with no sales line is [UNKNOWN] attribution — see ACCEPTANCE.md).")
    return EXIT_OK


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "summary":
        sys.exit(cmd_summary())
    code, result = run_mirror()
    print(json.dumps(result, sort_keys=True))
    sys.exit(code)
