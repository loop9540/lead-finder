"""
Source: 9at Export — Fund Administrator Competitors.
Reads the 9at contacts export and extracts unique companies that use
competitor fund administrators (not Gen II) as leads.
"""

import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openpyxl
from collections import defaultdict
from db import init_db, create_run, update_run, insert_leads

EXPORT_PATH = "/Users/idavid/Downloads/9at_export_contacts_2026_03_09.xlsx"

# Competitor administrators to target (case-insensitive matching)
COMPETITOR_ADMINS = [
    "SS&C TECHNOLOGIES",
    "APEX GROUP",
    "CITCO",
    "ALTER DOMUS",
    "STANDISH MANAGEMENT",
    "IQ-EQ",
    "FIS GLOBAL",
    "MAPLES",
    "TMF GROUP INC",
    "HEDGESERV",
    "AZTEC GROUP",
    "CSC",
    "LANGHAM HALL",
    "OCORIAN",
    "OPUS FUND SERVICES",
    "TRIDENT TRUST",
    "STONE COAST FUND SERVICES",
    "HC GLOBAL FUND SERVICES",
    "PETRA FUNDS GROUP",
    "JTC GROUP",
    "WAYSTONE",
    "VISTRA",
    "FORMIDIUM",
    "NAV CONSULTING, INC",
    "ADURO ADVISORS",
]

# Build a lookup set for fast matching
_ADMIN_LOOKUP = {a.upper().strip() for a in COMPETITOR_ADMINS}

SKIP_ADMINS = {"GEN II FUND SERVICES"}

SOURCE_NAME = "9at_admin"


def _clean_url(raw: str) -> str:
    """Extract the first usable domain/URL from a cell value."""
    if not raw:
        return ""
    raw = str(raw).strip()
    # Split on common separators (semicolon, comma, space, newline)
    parts = re.split(r"[;\s,\n]+", raw)
    for part in parts:
        part = part.strip().strip("/")
        if not part:
            continue
        # Remove protocol prefix for storage
        cleaned = re.sub(r"^https?://", "", part)
        cleaned = cleaned.strip("/")
        if "." in cleaned:
            return cleaned
    return ""


def _match_admin(admin_value: str) -> str | None:
    """Return the canonical competitor admin name if it matches, else None."""
    if not admin_value:
        return None
    upper = admin_value.upper().strip()
    # Exact match first
    if upper in _ADMIN_LOOKUP:
        return upper
    # Skip Gen II
    for skip in SKIP_ADMINS:
        if skip in upper:
            return None
    # Substring/contains match for flexibility
    for admin in _ADMIN_LOOKUP:
        if admin in upper or upper in admin:
            return admin
    return None


def extract_leads() -> list[dict]:
    """Read the 9at export and return deduplicated leads."""
    print(f"Opening {EXPORT_PATH} ...")
    wb = openpyxl.load_workbook(EXPORT_PATH, read_only=False, data_only=True)
    ws = wb.active

    # Track unique companies: company_name -> {domain, platform}
    seen = {}  # company_name_upper -> lead dict
    admin_counts = defaultdict(int)
    total_rows = 0
    skipped_gen2 = 0

    # Data starts at row 3 (row 1 empty, row 2 headers)
    for row in ws.iter_rows(min_row=3, values_only=True):
        total_rows += 1
        # Column D (index 3) = Parent Adviser Name
        # Column V (index 21) = Administrator
        # Column AB (index 27) = All Websites
        if len(row) < 22:
            continue

        company_name = row[3]  # Column D
        administrator = row[21]  # Column V

        if not company_name or not administrator:
            continue

        company_name = str(company_name).strip()
        administrator = str(administrator).strip()

        # Check if Gen II — skip
        if "GEN II" in administrator.upper():
            skipped_gen2 += 1
            continue

        # Check if competitor admin
        matched_admin = _match_admin(administrator)
        if not matched_admin:
            continue

        # Deduplicate by company name (case-insensitive)
        key = company_name.upper()
        if key in seen:
            continue

        # Get website from column AB (index 27)
        website = ""
        if len(row) > 27 and row[27]:
            website = _clean_url(str(row[27]))

        lead = {
            "company_name": company_name,
            "domain": website,
            "platform": matched_admin,
            "source": SOURCE_NAME,
        }
        seen[key] = lead
        admin_counts[matched_admin] += 1

    wb.close()

    print(f"\nProcessed {total_rows:,} data rows")
    print(f"Skipped {skipped_gen2:,} Gen II rows")
    print(f"\n{'Administrator':<35} {'Unique Companies':>18}")
    print("-" * 55)
    for admin in sorted(admin_counts.keys()):
        print(f"  {admin:<33} {admin_counts[admin]:>16,}")
    print("-" * 55)
    print(f"  {'TOTAL':<33} {len(seen):>16,}")

    return list(seen.values())


def run():
    """Extract leads and insert into the database."""
    init_db()
    leads = extract_leads()

    if not leads:
        print("\nNo leads found.")
        return

    # Create a run record
    run_id = create_run(sources=[SOURCE_NAME])
    print(f"\nCreated run #{run_id}")

    # Insert leads
    insert_leads(leads, run_id)

    # Update run record
    update_run(
        run_id,
        status="completed",
        total_raw=len(leads),
        total_deduped=len(leads),
        finished_at="datetime('now')",
    )

    # Report DB total
    from db import get_stats
    stats = get_stats()
    print(f"\nImported {len(leads):,} leads into DB (run #{run_id})")
    print(f"New DB total: {stats['total']:,} leads")

    return leads


if __name__ == "__main__":
    run()
