#!/usr/bin/env python3
"""
Regenerate the static site's data files from leads.db.

The docs/ site is served straight from JSON, so nothing loaded into the
database appears in the app until this runs. Previously this was done by
hand, which is how the database and the published site drifted apart.

Usage:
    python3 export_static.py [--out docs/data]
"""

import argparse
import json
import os
import sqlite3

from config import DB_PATH

LEAD_FIELDS = [
    "id", "company_name", "aum", "fund_count", "fund_types", "total_gav",
    "platform", "admin", "source", "domain", "asset_class", "country",
    "hq_location", "dry_powder", "fundraising_status", "funds_open",
    "last_fund_strategy", "description", "target_product",
    "investor_status", "raising_now",
]

CONTACT_FIELDS = [
    "first_name", "last_name", "title", "email", "email_status",
    "phone", "linkedin", "company_name_9at", "target_product",
]


def column_names(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/data")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    have_leads = column_names(conn, "leads")
    have_contacts = column_names(conn, "contacts")
    lead_cols = [f for f in LEAD_FIELDS if f in have_leads]
    contact_cols = [f for f in CONTACT_FIELDS if f in have_contacts]

    counts = dict(conn.execute(
        "SELECT lead_id, COUNT(*) FROM contacts GROUP BY lead_id"
    ).fetchall())

    leads = []
    for row in conn.execute(f"SELECT {', '.join(lead_cols)} FROM leads ORDER BY id"):
        rec = {c: row[c] for c in lead_cols}
        rec["contact_count"] = counts.get(row["id"], 0)
        leads.append(rec)

    contacts = {}
    for row in conn.execute(
        f"SELECT lead_id, {', '.join(contact_cols)} FROM contacts ORDER BY lead_id, id"
    ):
        contacts.setdefault(str(row["lead_id"]), []).append(
            {c: row[c] for c in contact_cols}
        )

    def one(sql):
        return conn.execute(sql).fetchone()[0]

    stats = {
        "total_leads": len(leads),
        "total_sponsors": one("SELECT COUNT(*) FROM leads WHERE target_product = ''"),
        "total_portal_targets": one("SELECT COUNT(*) FROM leads WHERE target_product = 'Portal'"),
        "total_funded_targets": one("SELECT COUNT(*) FROM leads WHERE target_product = 'Funded'"),
        "total_contacts": one("SELECT COUNT(*) FROM contacts"),
        "contacts_with_email": one("SELECT COUNT(*) FROM contacts WHERE email != ''"),
        "leads_matched": one("SELECT COUNT(DISTINCT lead_id) FROM contacts"),
        "uk_pe_enriched": one("SELECT COUNT(*) FROM leads WHERE source LIKE '%pitchbook_uk%'"),
    }

    for name, payload in (("leads", leads), ("contacts", contacts), ("stats", stats)):
        path = os.path.join(args.out, f"{name}.json")
        with open(path, "w") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        print(f"  {path}  {os.path.getsize(path) / 1e6:.1f} MB")

    print(json.dumps(stats, indent=2))
    conn.close()


if __name__ == "__main__":
    main()
