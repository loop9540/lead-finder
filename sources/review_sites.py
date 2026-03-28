"""
Source: G2, Capterra, TrustRadius review sites.
Reviewers publicly list their company name and job title.
Each review = a confirmed user of that platform.

Uses curl subprocess to avoid Python 3.14 SSL issues.
"""

import re
import subprocess
import time


# Review page URLs per platform
REVIEW_TARGETS = {
    "Dynamo": {
        "g2": "https://www.g2.com/products/dynamo-software/reviews",
        "capterra": "https://www.capterra.com/p/155498/Dynamo/reviews/",
    },
    "InvestorFlow": {
        "g2": "https://www.g2.com/products/investorflow/reviews",
    },
    "ARKPES": {
        "g2": "https://www.g2.com/products/ark-pes/reviews",
    },
    "eFront / Investment Cafe": {
        "g2": "https://www.g2.com/products/efront/reviews",
        "capterra": "https://www.capterra.com/p/178355/eFront/reviews/",
    },
    "Intralinks": {
        "g2": "https://www.g2.com/products/ss-c-intralinks/reviews",
        "capterra": "https://www.capterra.com/p/28653/Intralinks/reviews/",
    },
    "AllVue / AltaReturn": {
        "g2": "https://www.g2.com/products/allvue-systems/reviews",
    },
    "Sharesecure": {
        "g2": "https://www.g2.com/products/altvia/reviews",
    },
}


def _fetch_page(url: str) -> str:
    """Fetch page HTML using curl."""
    try:
        result = subprocess.run(
            [
                "curl", "-s", "-L", "--max-time", "15",
                "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
                "-H", "Accept: text/html,application/xhtml+xml",
                "-H", "Accept-Language: en-US,en;q=0.9",
                url,
            ],
            capture_output=True, text=True, timeout=20,
        )
        return result.stdout if result.returncode == 0 else ""
    except subprocess.TimeoutExpired:
        return ""


def _extract_g2_reviewers(html: str) -> list[dict]:
    """Extract reviewer company names from G2 review pages."""
    companies = []

    # G2 shows reviewer info in structured patterns.
    # Look for company names near review metadata.

    # Pattern: "User in [Industry]" at "Company Name"
    # or reviewer title blocks with company info
    for match in re.findall(
        r'(?:at|of|from)\s+(?:<[^>]*>)*\s*([A-Z][A-Za-z0-9\s&.,\'-]+?)(?:</|<|\n|\|)',
        html,
    ):
        name = match.strip().rstrip(".,")
        if 5 < len(name) < 80:
            companies.append({"name": name, "source_site": "g2"})

    # Also look for structured data / JSON-LD
    for match in re.findall(r'"organizationName"\s*:\s*"([^"]+)"', html):
        if 3 < len(match) < 80:
            companies.append({"name": match, "source_site": "g2"})

    # Look for "works at" pattern
    for match in re.findall(r'works?\s+at\s+([A-Z][A-Za-z0-9\s&.,\'-]+?)(?:<|\n|\||")', html):
        name = match.strip().rstrip(".,")
        if 3 < len(name) < 80:
            companies.append({"name": name, "source_site": "g2"})

    return companies


def _extract_capterra_reviewers(html: str) -> list[dict]:
    """Extract reviewer company names from Capterra review pages."""
    companies = []

    # Capterra shows "Industry: X" and company size info
    # Look for company names in reviewer profiles
    for match in re.findall(
        r'(?:"companyName"|company-name|"company")\s*[":]\s*"?([^"<\n]+)"?',
        html,
    ):
        name = match.strip()
        if 3 < len(name) < 80:
            companies.append({"name": name, "source_site": "capterra"})

    return companies


def _search_google_reviews(platform_name: str) -> list[dict]:
    """
    Search Google for review pages mentioning the platform.
    This catches reviews on sites we haven't directly scraped.
    """
    companies = []
    queries = [
        f'site:g2.com "{platform_name}" review',
        f'site:trustradius.com "{platform_name}" review',
    ]

    for query in queries:
        from urllib.parse import quote_plus
        url = f"https://www.google.com/search?q={quote_plus(query)}&num=20"

        try:
            result = subprocess.run(
                [
                    "curl", "-s", "--max-time", "10",
                    "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                           "AppleWebKit/537.36",
                    url,
                ],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                # Extract company names from Google snippet text
                for match in re.findall(
                    r'(?:at|from)\s+([A-Z][A-Za-z0-9\s&]+(?:Capital|Partners|Group|Fund|Management|Advisors))',
                    result.stdout,
                ):
                    companies.append({"name": match.strip(), "source_site": "google_reviews"})

            time.sleep(3)
        except subprocess.TimeoutExpired:
            pass

    return companies


def discover(platform_name: str, platform_domain: str) -> list[dict]:
    """
    Discover companies from review sites for a competitor platform.
    """
    target = REVIEW_TARGETS.get(platform_name)
    if not target:
        return []

    print(f"  [reviews] Scraping review sites for {platform_name}...")

    all_companies = []

    # Scrape G2
    if "g2" in target:
        html = _fetch_page(target["g2"])
        if html:
            companies = _extract_g2_reviewers(html)
            all_companies.extend(companies)
            print(f"    [g2] Found {len(companies)} reviewer companies")

            # Try additional pages
            for page in range(2, 4):
                page_url = f"{target['g2']}?page={page}"
                html = _fetch_page(page_url)
                if html:
                    more = _extract_g2_reviewers(html)
                    all_companies.extend(more)
                time.sleep(2)

    # Scrape Capterra
    if "capterra" in target:
        html = _fetch_page(target["capterra"])
        if html:
            companies = _extract_capterra_reviewers(html)
            all_companies.extend(companies)
            print(f"    [capterra] Found {len(companies)} reviewer companies")

    # Deduplicate
    seen = set()
    results = []
    for comp in all_companies:
        key = comp["name"].lower().strip()
        if key not in seen:
            seen.add(key)
            results.append({
                "company_name": comp["name"],
                "domain": "",
                "platform": platform_name,
                "source": f"review:{comp['source_site']}",
            })

    print(f"  [reviews] Total unique companies for {platform_name}: {len(results)}")
    return results
