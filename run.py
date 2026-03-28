#!/usr/bin/env python3
"""
Lead Finder — Discover companies using competitor fund admin platforms.

Sources:
  - crt.sh (Certificate Transparency logs)
  - website (competitor website scraping — clients, case studies, testimonials)
  - reviews (G2, Capterra review site scraping)
  - google (Google dork searches)
  - edgar (SEC EDGAR filing search)

Usage:
  python3 run.py                           # Run all sources
  python3 run.py --source crt              # Only crt.sh
  python3 run.py --source website          # Only website scraping
  python3 run.py --source crt,website      # Multiple sources
  python3 run.py --existing file.xlsx      # Deduplicate against existing list
"""

import argparse
import time
from datetime import datetime

from config import COMPETITOR_PLATFORMS, OUTPUT_DIR
from sources.crt_sh import discover as crt_discover
from sources.google_dorks import discover as google_discover
from sources.website_scraper import discover as website_discover
from sources.review_sites import discover as reviews_discover
from sources.sec_edgar import discover as edgar_discover
from sources.website_tech_detect import discover_from_9at
from dedup import deduplicate
from export import export_to_excel

# Standard sources that iterate over COMPETITOR_PLATFORMS
SOURCE_MAP = {
    "crt": crt_discover,
    "google": google_discover,
    "website": website_discover,
    "reviews": reviews_discover,
    "edgar": edgar_discover,
}

# Path to 9at data file
NINE_AT_FILE = "/Users/idavid/Downloads/9at_export_contacts_2026_03_09.xlsx"


def run_discovery(active_sources: list[str], existing_file: str = "",
                  progress_callback=None) -> tuple[list[dict], dict]:
    """
    Run discovery for the given sources.
    Returns (unique_leads, metadata).
    progress_callback(message: str) is called with status updates if provided.
    """
    def log(msg):
        print(msg)
        if progress_callback:
            progress_callback(msg)

    log(f"Sources: {', '.join(active_sources)}")

    all_leads = []

    # Standard sources: iterate over competitor platforms
    standard_sources = [s for s in active_sources if s in SOURCE_MAP]
    if standard_sources:
        total_platforms = len(COMPETITOR_PLATFORMS)
        for i, (platform_name, platform_domain) in enumerate(COMPETITOR_PLATFORMS, 1):
            log(f"[{i}/{total_platforms}] {platform_name} ({platform_domain})")

            for source_name in standard_sources:
                discover_fn = SOURCE_MAP[source_name]
                leads = discover_fn(platform_name, platform_domain)
                all_leads.extend(leads)

                if source_name in ("crt", "google"):
                    time.sleep(2)

    # Tech detect source: scans 9at company websites
    if "tech_detect" in active_sources:
        import os
        if os.path.exists(NINE_AT_FILE):
            log("Running 9at website tech detection...")
            tech_leads = discover_from_9at(NINE_AT_FILE, progress_callback=log)
            all_leads.extend(tech_leads)
            log(f"Tech detect found {len(tech_leads)} leads")
        else:
            log(f"9at file not found: {NINE_AT_FILE}")

    total_raw = len(all_leads)
    log(f"Total raw leads: {total_raw}")

    log("Deduplicating...")
    unique_leads = deduplicate(all_leads, existing_file=existing_file)
    unique_leads.sort(key=lambda x: (x["platform"], x["company_name"]))

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"{OUTPUT_DIR}/leads_{timestamp}.xlsx"
    export_to_excel(unique_leads, output_file)

    metadata = {
        "total_raw": total_raw,
        "total_deduped": len(unique_leads),
        "output_file": output_file,
    }

    log(f"Done: {len(unique_leads)} unique leads -> {output_file}")
    return unique_leads, metadata


def main():
    parser = argparse.ArgumentParser(description="Discover companies using competitor platforms")
    parser.add_argument(
        "--source", type=str, default="all",
        help="Comma-separated sources: crt,website,reviews,google,edgar,all (default: all)",
    )
    parser.add_argument(
        "--existing", type=str, default="",
        help="Path to existing leads Excel file for deduplication",
    )
    args = parser.parse_args()

    if args.source == "all":
        active_sources = list(SOURCE_MAP.keys())
    else:
        active_sources = [s.strip() for s in args.source.split(",")]
        for s in active_sources:
            if s not in SOURCE_MAP:
                print(f"Unknown source: {s}. Available: {', '.join(SOURCE_MAP.keys())}")
                return

    print("=" * 60)
    print("Lead Finder — Competitor Platform Discovery")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    leads, meta = run_discovery(active_sources, args.existing)

    print(f"\n{'=' * 60}")
    print(f"Final: {meta['total_deduped']} unique new leads")
    print(f"Output: {meta['output_file']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
