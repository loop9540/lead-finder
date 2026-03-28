"""
Source: SEC EDGAR full-text search (EFTS).
Searches SEC filings for mentions of competitor platforms as technology vendors.
Companies that reference "Intralinks data room", "Investran", etc. in filings
are confirmed users of those platforms.

Uses the free EDGAR EFTS API — no API key needed.
SEC requires a User-Agent with company name and email.
"""

import json
import re
import subprocess
import time

# Search phrases mapped to platform names
# These phrases indicate the company USES the platform (not just mentions it)
SEARCH_PHRASES = {
    "Intralinks": [
        "intralinks+virtual+data+room",
        "intralinks+data+room",
        "intralinks+platform",
        "intralinks+deal+room",
    ],
    "DX / FIS": [
        "investran",
    ],
    "eFront / Investment Cafe": [
        "efront+investment+cafe",
    ],
    "Sharesecure": [
        "sharesecure",
    ],
}

# Company names to exclude (platform parent companies, not leads)
EXCLUDE_PATTERNS = [
    "intralinks", "ss&c tech", "sungard", "fidelity national information",
    "allvue systems holdings",
]

USER_AGENT = "Gen2Fund idavid@gen2fund.com"


def _search_filings(phrase: str) -> list[dict]:
    """Search EDGAR EFTS for a phrase and return filer companies."""
    url = (
        f"https://efts.sec.gov/LATEST/search-index"
        f"?q=%22{phrase}%22"
        f"&_source=display_names,root_forms"
        f"&from=0&size=0"
    )

    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", "15", "-H", f"User-Agent: {USER_AGENT}", url],
            capture_output=True, text=True, timeout=20,
        )
        if result.returncode != 0:
            return []

        d = json.loads(result.stdout)
        companies = []
        for b in d.get("aggregations", {}).get("entity_filter", {}).get("buckets", []):
            raw = b["key"]
            name = raw.split("(CIK")[0].strip()
            companies.append(name)
        return companies

    except (json.JSONDecodeError, subprocess.TimeoutExpired, KeyError):
        return []


def _clean_company_name(name: str) -> str:
    """Clean SEC filing company names — remove ticker symbols, standardize."""
    # Remove ticker info in parentheses at the end
    name = re.sub(r'\s*\([A-Z, -]+\)\s*$', '', name)
    # Remove /DE/, /CA/, /MA/ etc.
    name = re.sub(r'\s*/[A-Z]{2}/\s*$', '', name)
    # Remove trailing commas, periods
    name = name.strip().rstrip(",.")
    return name


def _is_excluded(name: str) -> bool:
    """Check if company should be excluded."""
    low = name.lower()
    return any(ex in low for ex in EXCLUDE_PATTERNS)


def discover(platform_name: str, platform_domain: str) -> list[dict]:
    """Discover companies from SEC EDGAR filings mentioning a platform."""
    phrases = SEARCH_PHRASES.get(platform_name)
    if not phrases:
        return []

    print(f"  [edgar] Searching SEC filings for {platform_name}...")

    all_names = set()
    for phrase in phrases:
        companies = _search_filings(phrase)
        for c in companies:
            if not _is_excluded(c):
                all_names.add(c)
        time.sleep(1)  # Be nice to SEC servers

    results = []
    for name in sorted(all_names):
        clean = _clean_company_name(name)
        if clean:
            results.append({
                "company_name": clean,
                "domain": "",
                "platform": platform_name,
                "source": "sec_edgar",
            })

    print(f"  [edgar] Found {len(results)} companies for {platform_name}")
    return results
