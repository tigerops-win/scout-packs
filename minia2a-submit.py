#!/usr/bin/env python3
"""minia2a.uk listing submission for Scout Packs.
Generates (or reuses) a Tiger Operations operational wallet, registers it,
and publishes the Scout Packs listing. The key is stored 600-perm; it is an
identity key for the listing, not a funds wallet.
"""
import json, os, sys, urllib.request

KEY_PATH = os.path.expanduser("~/.minia2a-wallet.json")
API = "https://minia2a.uk"

def load_or_create():
    from eth_keys import keys
    import secrets
    if os.path.exists(KEY_PATH):
        d = json.load(open(KEY_PATH))
        priv = keys.PrivateKey(bytes.fromhex(d["private_key"]))
    else:
        priv = keys.PrivateKey(secrets.token_bytes(32))
        json.dump({"address": priv.public_key.to_checksum_address(),
                   "private_key": priv.to_hex()[2:]}, open(KEY_PATH, "w"))
        os.chmod(KEY_PATH, 0o600)
    return priv

def personal_sign(priv, message: str) -> str:
    from eth_hash.auto import keccak
    msg = message.encode()
    prefix = f"\x19Ethereum Signed Message:\n{len(msg)}".encode()
    h = keccak(prefix + msg)
    sig = priv.sign_msg_hash(h)
    v = sig.v + 27
    return "0x" + sig.r.to_bytes(32, "big").hex() + sig.s.to_bytes(32, "big").hex() + v.to_bytes(1, "big").hex()

def post(path, payload):
    req = urllib.request.Request(API + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read().decode())

def main():
    priv = load_or_create()
    wallet = priv.public_key.to_checksum_address()
    print("wallet:", wallet)

    # Step 1: register
    reg_msg = f"minia2a register: {wallet}"
    reg_sig = personal_sign(priv, reg_msg)
    try:
        st, resp = post("/api/v1/register-simple",
                         {"name": "Tiger Operations", "wallet": wallet, "signature": reg_sig})
        print("register:", st, json.dumps(resp)[:300])
    except Exception as e:
        print("register note:", getattr(e, "read", lambda: str(e))() if hasattr(e, "read") else e)

    # Step 2: publish
    pub_msg = f"minia2a publish: {wallet}"
    pub_sig = personal_sign(priv, pub_msg)
    payload = {
        "name": "Scout Packs",
        "endpoint": "https://scout-packs-production.up.railway.app/lookup?query=Julie%20Services%20Auto%20Repair",
        "price_cents": 1,
        "category": "data",
        "description": ("Scout Packs: pay-per-call B2B lead lookup for AI agents. "
                        "Query a company or domain, get a verified business email back. "
                        "987 verified leads. $0.01 USDC per lookup on Base via x402. "
                        "Contact: tigeroperations@protonmail.com"),
        "wallet": wallet,
        "signature": pub_sig,
    }
    st, resp = post("/api/v1/publish-service", payload)
    print("publish:", st)
    print(json.dumps(resp, indent=2)[:1500])
    json.dump(resp, open(os.path.expanduser("~/workspace/scout-packs/minia2a-listing.json"), "w"), indent=2)

if __name__ == "__main__":
    main()
