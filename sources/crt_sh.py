"""
Source: crt.sh — Certificate Transparency log search.
Competitor platforms often provision client-specific subdomains like
clientname.dynamosoftware.com. Each subdomain reveals a customer company.

Uses curl subprocess to avoid Python 3.14 SSL issues.
"""

import json
import re
import subprocess
import time


def fetch_subdomains(domain: str, retries: int = 3) -> list[str]:
    """Query crt.sh for all subdomains issued under a domain."""
    url = f"https://crt.sh/?q=%25.{domain}&output=json"

    for attempt in range(retries):
        try:
            result = subprocess.run(
                ["curl", "-s", "--max-time", "60", url],
                capture_output=True, text=True, timeout=90,
            )
            if result.returncode == 0 and result.stdout.strip():
                entries = json.loads(result.stdout)
                subdomains = set()
                for entry in entries:
                    name = entry.get("name_value", "")
                    for line in name.split("\n"):
                        line = line.strip().lower()
                        if line and line != f"*.{domain}" and line != domain:
                            subdomains.add(line)
                return sorted(subdomains)
        except (json.JSONDecodeError, subprocess.TimeoutExpired):
            time.sleep(3 * (attempt + 1))

    return []


# Platform-specific extraction patterns.
# Some platforms use clientname.platform.com, others use infrastructure subdomains.
# This dict maps platform domains to regex patterns that capture client names.
CLIENT_PATTERNS = {
    "dynamosoftware.com": [
        # clientname.dynamosoftware.com (direct subdomain, not multi-level)
        r"^([a-z][a-z0-9-]+)\.dynamosoftware\.com$",
    ],
    "investorflow.com": [
        # clientname.investorflow.com
        r"^([a-z0-9][a-z0-9-]+)\.investorflow\.com$",
        # clientname-irm.investorflow.com
        r"^([a-z0-9][a-z0-9-]+)-irm\.investorflow\.com$",
    ],
}

# Subdomains that are infrastructure, not clients
GENERIC_SUBDOMAINS = {
    "www", "www-fallback", "mail", "smtp", "pop", "imap", "ftp",
    "api", "api-prod", "api-dev", "api-stg", "api-intg", "api-qa",
    "app", "apps", "dev", "developer",
    "staging", "stg", "test", "qa", "intg", "uat", "npe",
    "demo", "mydemo", "beta", "preview",
    "admin", "portal", "login", "auth", "sso", "okta",
    "cdn", "static", "docs", "help", "support", "clientsupport",
    "status", "sitestatus", "blog", "news", "careers", "contact",
    "vpn", "rackvpn", "rsvpn", "remote", "webmail",
    "mx", "ns1", "ns2", "ns3", "ns4", "cpanel",
    "dynamo", "dynamoeu", "dynamomcp-nextminor", "content", "pages",
    "sales", "hello", "email",
    "services", "prod", "registry", "maintenance", "maintenance-page",
    "maintenancepage", "ideas", "recognize", "related",
    "upflow-email", "searchfunds", "viewmyportal", "familyoffice",
    "addin", "addin-dev", "addin-feature", "stg-portal",
    "data-automation", "clients-rds-web", "debug", "migrations",
    "gcp", "eu2", "eu3", "sg2", "uae",
    "challenge", "aus", "alts", "help3", "d10", "d11", "d12",
    "api-viking", "citadelportalprod", "dda", "bop", "bhr", "bii",
    "poceu", "pocsg", "pocus", "portmigr", "rome", "sfs",
    "rpaapidev", "keycloak-qa",
}


def extract_company_name(subdomain: str, platform_domain: str) -> str | None:
    """
    Extract a client company name from a subdomain.
    Uses platform-specific patterns when available, falls back to generic extraction.
    """
    patterns = CLIENT_PATTERNS.get(platform_domain)

    # Only extract from platforms where we've confirmed client-named subdomains.
    # Other platforms use infrastructure subdomains that don't reveal client names.
    if not patterns:
        return None

    for pattern in patterns:
        m = re.match(pattern, subdomain)
        if m:
            candidate = m.group(1)
            candidate = re.sub(r"-irm$", "", candidate)
            if _is_valid_client_name(candidate):
                return candidate
    return None


def _is_valid_client_name(name: str) -> bool:
    """Check if a candidate string looks like a real client/company name."""
    if name in GENERIC_SUBDOMAINS:
        return False

    # Environment/deployment suffixes and prefixes
    env_patterns = [
        r"uat$", r"-dev$", r"-qa$", r"-stg$", r"-prod$", r"-npe$",
        r"^uat-", r"^stg-", r"^dev-", r"^qa-", r"^poc",
        r"^staging", r"^testing",
        r"-preview$", r"-test$", r"-staging$",
    ]
    for pat in env_patterns:
        if re.search(pat, name):
            return False

    # Skip random hex hashes
    if re.match(r"^[0-9a-f]{8,}$", name):
        return False
    # Skip pure numbers or very short names (likely codes, not companies)
    if re.match(r"^[a-z]?\d+$", name):
        return False
    if len(name) <= 3:
        return False
    # Skip names that look like infrastructure components
    if re.search(r"(api|mcp|rpa|keycloak|nextminor|portmigr|saml)", name):
        return False

    return True


def discover(platform_name: str, platform_domain: str) -> list[dict]:
    """
    Discover companies using a competitor platform via crt.sh.
    Returns list of dicts with company info.
    """
    print(f"  [crt.sh] Searching subdomains for {platform_domain}...")
    subdomains = fetch_subdomains(platform_domain)
    print(f"  [crt.sh] Found {len(subdomains)} subdomains for {platform_domain}")

    results = []
    seen = set()

    for sub in subdomains:
        company = extract_company_name(sub, platform_domain)
        if company and company not in seen:
            seen.add(company)
            results.append({
                "company_name": company,
                "domain": sub,
                "platform": platform_name,
                "source": "crt.sh",
            })

    print(f"  [crt.sh] Extracted {len(results)} unique company names from {platform_domain}")
    return results
