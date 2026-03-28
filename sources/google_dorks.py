"""
Source: Google search — find companies referencing competitor platforms.

NOTE: Google rate-limits automated searches aggressively.
This module uses a conservative approach with delays.
For production scale, consider using a SERP API (SerpAPI, ScaleSerp, etc.)

Uses curl subprocess to avoid Python 3.14 SSL issues.
"""

import re
import subprocess
import time
from urllib.parse import quote_plus


# Dork templates — {domain} gets replaced with the competitor platform domain
DORK_TEMPLATES = [
    'site:{domain} -www.{domain}',           # Client subdomains
    '"{domain}" "log in" -site:{domain}',     # Pages referencing the login
    '"{domain}" "client portal"',             # Client portal references
    '"{domain}" "fund" "private equity"',     # Industry-specific mentions
]


def _search_google(query: str, num_results: int = 20) -> list[str]:
    """
    Perform a Google search via curl and extract result URLs.
    """
    url = f"https://www.google.com/search?q={quote_plus(query)}&num={num_results}"

    try:
        result = subprocess.run(
            [
                "curl", "-s", "--max-time", "15",
                "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
                url,
            ],
            capture_output=True, text=True, timeout=20,
        )
        if result.returncode != 0 or not result.stdout:
            return []

        text = result.stdout
        if "detected unusual traffic" in text.lower():
            print("    [google] Rate limited — skipping this query")
            return []

        # Extract URLs from search results
        urls = re.findall(r'href="(https?://[^"&]+)"', text)
        filtered = [
            u for u in urls
            if "google.com" not in u
            and "googleapis.com" not in u
            and "gstatic.com" not in u
            and "youtube.com" not in u
        ]
        return filtered
    except subprocess.TimeoutExpired:
        return []


def _extract_domain_from_url(url: str) -> str | None:
    """Extract the base domain from a URL."""
    match = re.match(r'https?://([^/]+)', url)
    if not match:
        return None
    host = match.group(1).lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _domain_to_company(domain: str, platform_domain: str) -> str | None:
    """Try to derive a company name from a domain, filtering out noise."""
    noise = {
        "linkedin.com", "facebook.com", "twitter.com", "x.com",
        "crunchbase.com", "bloomberg.com", "pitchbook.com",
        "google.com", "wikipedia.org", "reddit.com", "github.com",
        platform_domain,
    }
    for n in noise:
        if domain.endswith(n):
            return None

    parts = domain.split(".")
    if len(parts) >= 2:
        return parts[-2]
    return None


def discover(platform_name: str, platform_domain: str) -> list[dict]:
    """Discover companies via Google dork searches for a competitor platform."""
    print(f"  [google] Searching for {platform_domain}...")
    results = []
    seen = set()

    for template in DORK_TEMPLATES:
        query = template.format(domain=platform_domain)
        urls = _search_google(query)

        for url in urls:
            domain = _extract_domain_from_url(url)
            if not domain:
                continue
            company = _domain_to_company(domain, platform_domain)
            if company and company not in seen:
                seen.add(company)
                results.append({
                    "company_name": company,
                    "domain": domain,
                    "platform": platform_name,
                    "source": "google",
                })

        time.sleep(5)

    print(f"  [google] Found {len(results)} unique companies for {platform_domain}")
    return results
