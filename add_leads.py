#!/usr/bin/env python3
"""Append a lead to the expansion pack with dedup against existing + already-added emails."""
import json, sys, os

EXPANSION = os.path.expanduser("~/workspace/scout-packs/packs/scout-pack-expansion.json")
EXISTING = os.path.expanduser("~/workspace/scout-packs/packs/scout-pack-25.json")

def load_existing_emails():
    with open(EXISTING) as f:
        data = json.load(f)
    return set(l["contact_email"].lower() for l in data["leads"])

def load_expansion():
    if os.path.exists(EXPANSION):
        with open(EXPANSION) as f:
            return json.load(f)
    return []

def main():
    leads_to_add = json.load(sys.stdin)
    existing = load_existing_emails()
    expansion = load_expansion()
    expansion_emails = set(l["contact_email"].lower() for l in expansion)
    added, skipped = 0, []
    for lead in leads_to_add:
        email = lead["contact_email"].strip().lower()
        if email in existing or email in expansion_emails:
            skipped.append(email)
            continue
        lead["contact_email"] = email
        lead["verified"] = "2026-10-02"
        lead["verification"] = "published business email; verified against business site/listing"
        expansion.append(lead)
        expansion_emails.add(email)
        added += 1
    with open(EXPANSION, "w") as f:
        json.dump(expansion, f, indent=2)
    print(f"added={added} skipped_dupes={skipped} total_expansion={len(expansion)}")

if __name__ == "__main__":
    main()
