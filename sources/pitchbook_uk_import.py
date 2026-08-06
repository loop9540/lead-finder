#!/usr/bin/env python3
"""
Import a PitchBook UK investor export into leads.db.

Replaces the ad-hoc load behind commit ccd2e38, which put 2,500 of the
sheet's 2,681 rows into the database and left 25 firms out entirely
(ICG at $127bn among them).

Every sheet row ends up represented exactly once:
  - exact / normalised name match  -> enrich the existing lead in place
  - legal-entity match             -> "Baillie Gifford" finds
                                      "BAILLIE GIFFORD & CO LIMITED"
  - no match                       -> insert a new lead

Enrichment only fills blanks; a value already in the database is never
overwritten. That makes the script safe to re-run.

Usage:
    python3 -m sources.pitchbook_uk_import <file.xlsx> [--source TAG] [--commit]

Without --commit it is a dry run and prints what it would change.
"""

import argparse
import re
import sqlite3
import sys

import openpyxl

from config import DB_PATH

# Sheet layout — PitchBook puts 7 rows of provenance above the header
HEADER_ROW = 8
SHEET = "Data"

# AUM, Dry Powder and fund sizes are reported in $M
MILLIONS = 1_000_000

COLUMNS = {
    "name": "Investors",
    "website": "Website",
    "country": "HQ Country/Territory/Region",
    "raising": "Most Likely Fundraising",
    "funds_open": "# Funds Open",
    "last_strategy": "Last Closed Fund Strategy",
    "aum": "AUM",
    "dry_powder": "Dry Powder",
    "hq": "HQ Location",
    "description": "Description",
    "status": "Investor Status",
    "contact": "Primary Contact",
    "contact_title": "Primary Contact Title",
    "contact_email": "Primary Contact Email",
    "contact_phone": "Primary Contact Phone",
}

HYPERLINK = re.compile(r'HYPERLINK\("([^"]+)"', re.I)


def domain_of(cell) -> str:
    """Website cells are =HYPERLINK("http://x.com", "x.com") formulas."""
    if not cell:
        return ""
    m = HYPERLINK.search(str(cell))
    url = m.group(1) if m else str(cell)
    url = re.sub(r"^https?://", "", url.strip())
    return url.split("/")[0].lower()


def tokens(name: str) -> list[str]:
    """Comparable word tokens: 'BAILLIE GIFFORD & CO' -> [baillie, gifford, co]."""
    name = re.sub(r"\([^)]*\)", " ", str(name).lower())
    return [t for t in re.split(r"[^a-z0-9]+", name) if t]


def key_of(name: str) -> str:
    return "".join(tokens(name))


def to_float(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def to_int(v) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def ensure_columns(conn):
    """raising_now keeps the sheet's real Yes/No fundraising signal.

    The previous import wrote Investor Status ('Out of Business', ...) into
    fundraising_status and dropped the Yes/No column entirely. Existing rows
    are left alone so the app's current filter keeps working.
    """
    existing = {r[1] for r in conn.execute("PRAGMA table_info(leads)")}
    if "raising_now" not in existing:
        conn.execute("ALTER TABLE leads ADD COLUMN raising_now TEXT DEFAULT ''")
    if "investor_status" not in existing:
        conn.execute("ALTER TABLE leads ADD COLUMN investor_status TEXT DEFAULT ''")


def read_sheet(path: str) -> list[dict]:
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb[SHEET]
    rows = list(ws.iter_rows(min_row=HEADER_ROW, values_only=True))
    header = [str(c) if c is not None else "" for c in rows[0]]
    idx = {}
    for field, label in COLUMNS.items():
        if label not in header:
            sys.exit(f"column missing from sheet: {label!r}")
        idx[field] = header.index(label)

    out = []
    for r in rows[1:]:
        if not any(r):
            continue
        name = str(r[idx["name"]] or "").strip()
        if not name:
            continue
        out.append({
            "name": name,
            "domain": domain_of(r[idx["website"]]),
            "country": str(r[idx["country"]] or "").strip(),
            "hq": str(r[idx["hq"]] or "").strip(),
            "description": str(r[idx["description"]] or "").strip(),
            "status": str(r[idx["status"]] or "").strip(),
            "raising": str(r[idx["raising"]] or "").strip(),
            "last_strategy": str(r[idx["last_strategy"]] or "").strip(),
            "aum": to_float(r[idx["aum"]]) * MILLIONS,
            "dry_powder": to_float(r[idx["dry_powder"]]) * MILLIONS,
            "funds_open": to_int(r[idx["funds_open"]]),
            "contact": str(r[idx["contact"]] or "").strip(),
            "contact_title": str(r[idx["contact_title"]] or "").strip(),
            "contact_email": str(r[idx["contact_email"]] or "").strip(),
            "contact_phone": str(r[idx["contact_phone"]] or "").strip(),
        })
    wb.close()
    return out


def build_index(conn):
    """Map existing leads by exact name, normalised key, and token list."""
    by_name, by_key, by_tokens = {}, {}, []
    for row in conn.execute("SELECT id, company_name FROM leads"):
        lead_id, name = row
        by_name[name] = lead_id
        by_key.setdefault(key_of(name), lead_id)
        by_tokens.append((tokens(name), lead_id))
    return by_name, by_key, by_tokens


def match(rec, by_name, by_key, by_tokens):
    """Return (lead_id, how) or (None, 'new')."""
    if rec["name"] in by_name:
        return by_name[rec["name"]], "exact"

    k = key_of(rec["name"])
    if k in by_key:
        return by_key[k], "normalised"

    # Legal-entity match: sheet tokens are a strict prefix of the db name's
    # tokens, i.e. the db row is the same firm carrying "LLP"/"& CO LIMITED".
    t = tokens(rec["name"])
    if t and (len(t) > 1 or len(t[0]) >= 6):
        hits = [lid for dbt, lid in by_tokens
                if len(dbt) > len(t) and dbt[:len(t)] == t]
        if len(hits) == 1:
            return hits[0], "legal-entity"
        if len(hits) > 1:
            return None, "ambiguous"
    return None, "new"


# Only ever fill a blank; never clobber data already in the database.
ENRICH = [
    ("domain", "domain", ""),
    ("country", "country", ""),
    ("hq_location", "hq", ""),
    ("description", "description", ""),
    ("fundraising_status", "status", ""),
    ("investor_status", "status", ""),
    ("raising_now", "raising", ""),
    ("last_fund_strategy", "last_strategy", ""),
    ("aum", "aum", 0),
    ("dry_powder", "dry_powder", 0),
    ("funds_open", "funds_open", 0),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--source", default="pitchbook_uk_2026-04-16")
    ap.add_argument("--commit", action="store_true", help="write changes")
    args = ap.parse_args()

    records = read_sheet(args.path)
    print(f"sheet rows: {len(records)}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ensure_columns(conn)
    by_name, by_key, by_tokens = build_index(conn)

    stats = {"exact": 0, "normalised": 0, "legal-entity": 0, "new": 0, "ambiguous": 0}
    fields_filled = 0
    contacts_added = 0
    ambiguous = []

    for rec in records:
        lead_id, how = match(rec, by_name, by_key, by_tokens)
        stats[how] += 1
        if how == "ambiguous":
            ambiguous.append(rec["name"])
            # fall through and insert it rather than silently dropping it
            lead_id = None

        if lead_id is None:
            cur = conn.execute(
                """INSERT INTO leads
                   (company_name, domain, platform, source, country, hq_location,
                    description, fundraising_status, investor_status, raising_now,
                    last_fund_strategy, aum, dry_powder, funds_open)
                   VALUES (?,?,'',?,?,?,?,?,?,?,?,?,?,?)""",
                (rec["name"], rec["domain"], args.source, rec["country"], rec["hq"],
                 rec["description"], rec["status"], rec["status"], rec["raising"],
                 rec["last_strategy"], rec["aum"], rec["dry_powder"], rec["funds_open"]),
            )
            lead_id = cur.lastrowid
            by_name[rec["name"]] = lead_id
            by_key.setdefault(key_of(rec["name"]), lead_id)
            by_tokens.append((tokens(rec["name"]), lead_id))
        else:
            row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
            sets, vals = [], []
            for col, field, blank in ENRICH:
                if row[col] in (blank, None) and rec[field] not in ("", 0, 0.0):
                    sets.append(f"{col} = ?")
                    vals.append(rec[field])
            if sets:
                fields_filled += len(sets)
                conn.execute(f"UPDATE leads SET {', '.join(sets)} WHERE id = ?",
                             vals + [lead_id])
            tag = row["source"] or ""
            if "pitchbook_uk" not in tag:
                conn.execute("UPDATE leads SET source = ? WHERE id = ?",
                             (f"{tag} + pitchbook_uk".strip(" +"), lead_id))

        # Primary contact
        if rec["contact"]:
            parts = rec["contact"].split()
            first, last = parts[0], " ".join(parts[1:]) if len(parts) > 1 else ""
            dupe = conn.execute(
                """SELECT 1 FROM contacts WHERE lead_id = ?
                   AND (( email != '' AND email = ?) OR (first_name = ? AND last_name = ?))""",
                (lead_id, rec["contact_email"], first, last),
            ).fetchone()
            if not dupe:
                conn.execute(
                    """INSERT INTO contacts
                       (lead_id, first_name, last_name, title, email, email_status,
                        phone, linkedin, company_name_9at)
                       VALUES (?,?,?,?,?,'',?,'',?)""",
                    (lead_id, first, last, rec["contact_title"], rec["contact_email"],
                     rec["contact_phone"], rec["name"]),
                )
                contacts_added += 1

    print(f"  matched exact       : {stats['exact']}")
    print(f"  matched normalised  : {stats['normalised']}")
    print(f"  matched legal-entity: {stats['legal-entity']}")
    print(f"  inserted new        : {stats['new'] + stats['ambiguous']}")
    if ambiguous:
        print(f"  (of which ambiguous, inserted rather than dropped: {len(ambiguous)})")
        for n in ambiguous[:10]:
            print(f"      {n}")
    print(f"  blank fields filled : {fields_filled}")
    print(f"  contacts added      : {contacts_added}")

    if args.commit:
        conn.commit()
        print("committed")
    else:
        conn.rollback()
        print("DRY RUN — nothing written (pass --commit)")
    conn.close()


if __name__ == "__main__":
    main()
