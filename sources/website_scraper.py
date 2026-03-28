"""
Source: Competitor website scraping.
Scrapes client pages, case studies, testimonials, and partner pages
from competitor platform websites to extract company names.

Uses curl subprocess to avoid Python 3.14 SSL issues.
"""

import json
import re
import subprocess


# URLs to scrape per platform, organized by page type
SCRAPE_TARGETS = {
    "Dynamo": {
        "urls": [
            "https://www.dynamosoftware.com/our-customers/",
            "https://www.dynamosoftware.com/client-services/",
            "https://www.dynamosoftware.com/resource/cynosure/",
            "https://www.dynamosoftware.com/resource/client-testimonial-capinsights-partners/",
            "https://www.dynamosoftware.com/resource/client-testimonial-clearbell-capital-llp/",
            "https://www.dynamosoftware.com/resource/client-testimonial-harris-preston-partners/",
            "https://www.dynamosoftware.com/resource/client-testimonial-infrared-capital-partners/",
            "https://www.dynamosoftware.com/resource/client-testimonial-bu-investment-office/",
        ],
        "known_clients": [
            "Cape Capital", "Basin Street Properties", "SQN Investors",
            "Nord Holding", "Board of Pensions", "Frontier Growth",
            "CapInsights Partners", "Clearbell Capital", "Harris Preston & Partners",
            "InfraRed Capital Partners", "The Cynosure Group", "BU Investment Office",
        ],
    },
    "InvestorFlow": {
        "urls": [
            "https://www.investorflow.com/why-investorflow/client-relationships/",
            "https://www.investorflow.com/why-investorflow/partnership-network/",
        ],
        "known_clients": [
            "Warburg Pincus", "Verde Technology Ventures", "Alpha Alternatives",
        ],
    },
    "ARKPES": {
        "urls": [
            "https://www.arkpes.com/",
            "https://www.arkpes.com/case-study/lake-street-capital-private-equity-operations/",
        ],
        "known_clients": [
            "Lake Street Capital Partners", "Blue Star Innovation Partners",
            "Grayhawk Capital", "Shasta Ventures", "4Pines Fund Services",
        ],
    },
    "eFront / Investment Cafe": {
        "urls": [
            "https://www.efront.com/about-us/clients/",
            "https://www.efront.com/en/resources/case-studies",
            "https://www.efront.com/en/case-studies/mch-private-equity-implements-efront-investment-cafe",
            "https://www.efront.com/en/case-studies/foresight-implements-efront-invest-efront-investment-cafe",
        ],
        "known_clients": [
            "MCH Private Equity", "Foresight", "NPS",
            "Luxembourg Investment Solutions", "Wellershoff & Partners",
            "Old Mutual Alternative Investment", "Acumen",
        ],
    },
    "Intralinks": {
        "urls": [
            "https://www.intralinks.com/our-customers",
            "https://www.intralinks.com/customer-reviews",
            "https://www.intralinks.com/resources/case-studies",
        ],
        "known_clients": [
            "HCI Equity Partners", "Sectoral Asset Management",
            "Clyde Blowers Capital", "Huron Capital Partners",
            "New Mountain Capital", "Golden Gate Capital",
            "Ares Management", "Vue Group", "Interflex Group",
            "Fresh Insurance", "Essex Industries", "Globalvia",
        ],
    },
    "AllVue / AltaReturn": {
        "urls": [
            "https://www.allvuesystems.com/about/partners/",
            "https://www.allvuesystems.com/resources/video-case-study-phoenix-fund-services/",
            "https://www.allvuesystems.com/resources/case-study-trident-trust/",
            "https://www.allvuesystems.com/resources/case-study-polaris/",
            "https://www.allvuesystems.com/resources/case-study-albacore-capital-group/",
        ],
        "known_clients": [
            "Phoenix Fund Services", "Trident Trust", "Polaris",
            "AlbaCore Capital Group", "KPMG", "Standish Management",
            "RSM", "APEX Group", "IQEQ", "alterDomus",
            "Permian", "Phoenix Fund Services Group",
        ],
    },
    "DX / FIS": {
        "urls": [
            "https://www.fisglobal.com/products/fis-private-capital-suite",
            "https://www.fisglobal.com/insights/fis-client-stories",
        ],
        "known_clients": [
            "Maples Fund Services", "Centaur",
        ],
    },
    "Sharesecure": {
        "urls": [
            "https://altvia.com/",
            "https://altvia.com/case-studies/ivp/",
            "https://altvia.com/case-studies/clearvision-equity/",
            "https://altvia.com/case-studies/plexus-capital/",
            "https://altvia.com/case-studies/growth-catalyst-partners-case-study/",
        ],
        "known_clients": [
            "Commonfund", "IVP", "NEA", "Pathstone", "Ridgewood Energy",
            "Tecum", "Pritzker Private Capital", "Cendana",
            "Paladin Capital Group", "Brighton Park Capital", "Spire Capital",
            "Plexus Capital", "Growth Catalyst Partners",
            "Crosslink Capital", "Accolade Partners", "Sandlot Partners",
            "Falfurrias Management Partners", "Wind Point Partners",
            "Edge Natural Resources",
        ],
    },
}


def _fetch_page(url: str) -> str:
    """Fetch a page's HTML content using curl."""
    try:
        result = subprocess.run(
            [
                "curl", "-s", "-L", "--max-time", "15",
                "-H", "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
                url,
            ],
            capture_output=True, text=True, timeout=20,
        )
        return result.stdout if result.returncode == 0 else ""
    except subprocess.TimeoutExpired:
        return ""


def _extract_company_names_from_html(html: str) -> list[str]:
    """
    Extract potential company names from HTML.
    Focused on high-confidence extractions only:
    - Alt text on images that contain "logo" (logo walls)
    - Structured data with organization names
    - Testimonial attribution patterns
    """
    names = set()

    # Noise words — these appear in alt text / page content but aren't companies
    noise = {
        "facebook", "twitter", "linkedin", "instagram", "youtube",
        "google", "microsoft", "close", "menu", "search", "arrow",
        "image", "photo", "banner", "icon", "back", "next", "prev",
        "submit", "download", "learn more", "read more", "contact",
        "consent", "cookie", "privacy", "subscribe",
    }

    # 1. Alt text on images — only those that look like company logos
    for alt in re.findall(r'alt=["\']([^"\']+)["\']', html):
        alt = alt.strip()
        # Only grab alt text that contains "logo" — indicates a logo wall
        if "logo" in alt.lower() and len(alt) < 80:
            # Strip " logo", " Logo", "-logo" etc.
            company = re.sub(r'\s*[-_]?\s*logo\s*$', '', alt, flags=re.IGNORECASE).strip()
            if company and len(company) > 2 and company.lower() not in noise:
                names.add(company)

    # 2. Structured data / JSON-LD organization names
    for match in re.findall(r'"(?:organizationName|name)"\s*:\s*"([^"]+)"', html):
        match = match.strip()
        # Only if it looks like a company (has capital letter, reasonable length)
        if 3 < len(match) < 60 and match[0].isupper() and match.lower() not in noise:
            # Skip if it's a page title or product name
            if not any(w in match.lower() for w in ["case study", "review", "testimonial", "blog", "page"]):
                names.add(match)

    # 3. Testimonial attribution: "— Name, Title at Company"
    for match in re.findall(
        r'[—–]\s*[A-Z][a-z]+\s+[A-Z][a-z]+,\s*[^,]+(?:at|of|from)\s+([A-Z][A-Za-z\s&\'-]+)',
        html,
    ):
        company = match.strip().rstrip(".,")
        if 3 < len(company) < 60 and company.lower() not in noise:
            names.add(company)

    return list(names)


def _extract_case_study_links(html: str, base_url: str) -> list[str]:
    """Find links to case study pages for further scraping."""
    links = []
    for href in re.findall(r'href=["\']([^"\']*case-stud[^"\']*)["\']', html):
        if href.startswith("http"):
            links.append(href)
        elif href.startswith("/"):
            # Extract base domain
            m = re.match(r'(https?://[^/]+)', base_url)
            if m:
                links.append(m.group(1) + href)
    return links


def discover(platform_name: str, platform_domain: str) -> list[dict]:
    """
    Discover companies from competitor website content.
    Combines known clients (from research) with live scraping.
    """
    target = SCRAPE_TARGETS.get(platform_name)
    if not target:
        return []

    print(f"  [website] Scraping {platform_name} website...")

    results = []
    seen = set()

    # First: add known clients from research
    for client in target.get("known_clients", []):
        key = client.lower().strip()
        if key not in seen:
            seen.add(key)
            results.append({
                "company_name": client,
                "domain": "",
                "platform": platform_name,
                "source": "website",
            })

    # Second: scrape live pages for additional names
    for url in target.get("urls", []):
        html = _fetch_page(url)
        if not html:
            continue

        scraped_names = _extract_company_names_from_html(html)
        for name in scraped_names:
            key = name.lower().strip()
            if key not in seen:
                seen.add(key)
                results.append({
                    "company_name": name,
                    "domain": "",
                    "platform": platform_name,
                    "source": "website",
                })

        # Follow case study links
        case_study_links = _extract_case_study_links(html, url)
        for cs_url in case_study_links[:10]:  # Limit to avoid hammering
            cs_html = _fetch_page(cs_url)
            if cs_html:
                cs_names = _extract_company_names_from_html(cs_html)
                for name in cs_names:
                    key = name.lower().strip()
                    if key not in seen:
                        seen.add(key)
                        results.append({
                            "company_name": name,
                            "domain": "",
                            "platform": platform_name,
                            "source": "website",
                        })

    print(f"  [website] Found {len(results)} companies for {platform_name}")
    return results
