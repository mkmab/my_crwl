import asyncio
import urllib.robotparser
import urllib.parse
from dataclasses import dataclass, field
from urllib.parse import urlparse
import sys

import requests
from bs4 import BeautifulSoup

from app.crawler.extractors import (
    detect_technologies,
    extract_colors,
    extract_emails_deep,
    extract_logo_and_favicon,
    extract_owner_from_soup,
    extract_page,
    important_internal_links,
    looks_like_person_name,
    is_personal_email,
    rank_emails,
    OWNER_TITLE_MARKERS,
    EMAIL_RE,
    clean_text,
)
from app.models import CrawlResult, PageContent
from app.utils.config import settings
from app.utils.storage import public_url, storage_path
from app.utils.url import extract_domain, is_internal, normalize_url


HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SiteIntelBot/2.0; +local)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Paths that are most likely to contain owner/team info — crawled first
OWNER_PRIORITY_PATHS = [
    "/about", "/about-us", "/about_us",
    "/team", "/our-team", "/meet-the-team",
    "/founders", "/leadership", "/management",
    "/people", "/who-we-are", "/staff",
    "/contact", "/contact-us", "/get-in-touch",
]


@dataclass
class FetchResult:
    url: str
    html: str
    headers: dict[str, str] = field(default_factory=dict)


class WebsiteCrawler:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def crawl(self, raw_url: str) -> CrawlResult:
        url = normalize_url(raw_url)
        first = await self.fetch(url)
        domain = extract_domain(first.url)

        # Collect candidate URLs: prioritise owner-relevant pages
        owner_paths = [
            f"{urlparse(first.url).scheme}://{urlparse(first.url).netloc}{p}"
            for p in OWNER_PRIORITY_PATHS
        ]
        content_links = important_internal_links(first.url, first.html)
        # Owner pages first, then content pages, deduplicated
        candidates = [url] + owner_paths + content_links

        pages: list[PageContent] = []
        seen: set[str] = set()
        owner_name: str | None = None
        owner_email: str | None = None
        owner_title: str | None = None

        for candidate in candidates:
            if len(pages) >= settings.crawl_max_pages:
                break
            if candidate in seen or not is_internal(first.url, candidate):
                continue
            seen.add(candidate)
            if not self._allowed_by_robots(first.url, candidate):
                continue

            fetched = first if candidate == url else await self.fetch(candidate)
            if not fetched.html:
                continue

            page = extract_page(fetched.url, fetched.html)
            pages.append(page)

            # Try to find owner info from this page's HTML
            if not (owner_name and owner_email):
                soup = BeautifulSoup(fetched.html, "html.parser")
                found_name, found_title = extract_owner_from_soup(soup)
                if found_name and not owner_name and looks_like_person_name(found_name):
                    owner_name = found_name
                    owner_title = found_title

                # Find best personal email from this page
                if not owner_email:
                    personal_emails = [
                        email
                        for email in rank_emails(extract_emails_deep(fetched.html))
                        if is_personal_email(email)
                    ]
                    if personal_emails:
                        owner_email = personal_emails[0]

        # Cross-check: if we have all page emails, pick the best one
        if not owner_email:
            personal_emails = [
                email
                for email in rank_emails([e for p in pages for e in p.emails])
                if is_personal_email(email)
            ]
            if personal_emails:
                owner_email = personal_emails[0]

        # Fallback owner detection from headings/footer (original logic, improved)
        if not owner_name and pages:
            owner_name = self._detect_owner_name_from_pages(pages)

        # Optional external enrichment is disabled by default because it can
        # introduce low-confidence or outdated owner data.
        if settings.allow_external_contact_enrichment:
            whois_info = await asyncio.to_thread(self._whois_lookup, domain)
            if not owner_name and looks_like_person_name(whois_info.get("registrant_name")):
                owner_name = whois_info["registrant_name"]
            if not owner_email and is_personal_email(whois_info.get("registrant_email")):
                owner_email = whois_info["registrant_email"]

            linkedin_info = await self._find_linkedin_owner(domain)
            if not owner_name and looks_like_person_name(linkedin_info.get("likely_name")):
                owner_name = linkedin_info["likely_name"]

        # --- Hunter.io email lookup (free tier) ---
        if not owner_email and settings.hunter_api_key:
            hunter_email = await asyncio.to_thread(self._hunter_lookup, domain)
            if hunter_email and is_personal_email(hunter_email):
                owner_email = hunter_email

        logo, favicon, og_image = extract_logo_and_favicon(first.url, first.html)
        colors = extract_colors(first.html)
        screenshot_url = await self.capture_screenshot(first.url)
        tech = detect_technologies(first.html, first.headers)

        return CrawlResult(
            requested_url=url,
            final_url=first.url,
            pages=pages,
            logo_url=logo,
            favicon_url=favicon,
            og_image_url=og_image,
            screenshot_url=screenshot_url,
            theme_colors=colors,
            technologies=tech,
            owner_name=owner_name,
            owner_email=owner_email,
        )

    # ------------------------------------------------------------------
    # Fetch helpers
    # ------------------------------------------------------------------

    async def fetch(self, url: str) -> FetchResult:
        try:
            response = self.session.get(
                url,
                timeout=settings.crawl_timeout_seconds,
                allow_redirects=True,
            )
            content_type = response.headers.get("content-type", "")
            if response.ok and "text/html" in content_type:
                html = response.text
                if self._needs_browser(html):
                    rendered = await self.fetch_with_playwright(str(response.url))
                    if rendered:
                        return FetchResult(str(response.url), rendered, dict(response.headers))
                return FetchResult(str(response.url), html, dict(response.headers))
        except requests.RequestException:
            pass

        rendered = await self.fetch_with_playwright(url)
        return FetchResult(url, rendered or "", {})

    async def fetch_with_playwright(self, url: str) -> str:
        if not settings.allow_playwright:
            return ""
        try:
            return await asyncio.to_thread(self._fetch_with_playwright_sync, url)
        except Exception:
            return ""

    async def capture_screenshot(self, url: str) -> str:
        if not settings.allow_playwright:
            return ""
        try:
            return await asyncio.to_thread(self._capture_screenshot_sync, url)
        except Exception:
            return ""

    # ------------------------------------------------------------------
    # Owner detection helpers
    # ------------------------------------------------------------------

    def _detect_owner_name_from_pages(self, pages: list[PageContent]) -> str | None:
        """Fallback: scan headings and footer text for owner title markers."""
        for page in pages:
            candidates = list(page.headings[:10])
            if page.footer:
                candidates.append(page.footer)
            for text in candidates:
                low = text.lower()
                if any(marker in low for marker in OWNER_TITLE_MARKERS):
                    import re
                    names = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b", text)
                    for name in names:
                        if looks_like_person_name(name):
                            return name
        return None

    # ------------------------------------------------------------------
    # WHOIS lookup
    # ------------------------------------------------------------------

    def _whois_lookup(self, domain: str) -> dict:
        """
        Use python-whois to get registrant info. Install with:
            pip install python-whois
        Returns empty dict on any failure (not installed, rate limit, etc.)
        """
        try:
            import whois  # type: ignore
            w = whois.whois(domain)
            name = None
            email = None

            # python-whois may return lists or strings
            raw_name = w.get("name") or w.get("registrant_name") or w.get("org")
            if isinstance(raw_name, list):
                raw_name = raw_name[0] if raw_name else None
            if raw_name:
                # Exclude privacy proxies
                proxy_words = ("privacy", "proxy", "redact", "whoisguard", "protect", "domain")
                if not any(p in str(raw_name).lower() for p in proxy_words):
                    name = clean_text(str(raw_name), 80)

            raw_email = w.get("emails")
            if isinstance(raw_email, list):
                raw_email = raw_email[0] if raw_email else None
            if raw_email and "@" in str(raw_email):
                email = str(raw_email).strip()

            return {
                "registrant_name": name,
                "registrant_email": email,
                "registrant_org": str(w.get("org") or ""),
                "creation_date": str(w.get("creation_date", "")),
            }
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # LinkedIn / Google search for decision-maker (free)
    # ------------------------------------------------------------------

    async def _find_linkedin_owner(self, domain: str) -> dict:
        """
        Search Google for a LinkedIn profile of the CEO/founder at this domain.
        Uses Google's public search — no API key required.
        Returns {"likely_name": str, "linkedin_url": str} or {}.
        """
        company = domain.split(".")[0]
        queries = [
            f'site:linkedin.com/in "{company}" CEO OR founder OR owner',
            f'"{company}" founder OR CEO site:linkedin.com/in',
        ]
        for query in queries:
            search_url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&num=5"
            try:
                result = await self.fetch(search_url)
                if not result.html:
                    continue
                soup = BeautifulSoup(result.html, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = str(a["href"])
                    # Google wraps links in /url?q=...
                    if "/url?q=" in href:
                        href = urllib.parse.unquote(href.split("/url?q=")[1].split("&")[0])
                    if "linkedin.com/in/" in href:
                        slug = href.split("linkedin.com/in/")[-1].split("?")[0].strip("/")
                        # slug is typically firstname-lastname or firstname-lastname-XXXXX
                        parts = [p for p in slug.replace("-", " ").split() if p.isalpha()]
                        if 1 < len(parts) <= 4:
                            name = " ".join(p.title() for p in parts[:3])
                            return {"likely_name": name, "linkedin_url": href}
            except Exception:
                continue
        return {}

    # ------------------------------------------------------------------
    # Hunter.io free tier lookup
    # ------------------------------------------------------------------

    def _hunter_lookup(self, domain: str) -> str | None:
        """
        Look up the most likely email for a domain using Hunter.io.
        Free tier: 25 searches/month. Requires HUNTER_API_KEY in .env.
        """
        if not settings.hunter_api_key:
            return None
        try:
            resp = self.session.get(
                "https://api.hunter.io/v2/domain-search",
                params={
                    "domain": domain,
                    "api_key": settings.hunter_api_key,
                    "limit": 5,
                    "type": "personal",
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            emails = data.get("data", {}).get("emails", [])
            # Sort by confidence descending, prefer personal type
            emails.sort(key=lambda e: (e.get("type") == "personal", e.get("confidence", 0)), reverse=True)
            if emails:
                return emails[0].get("value")
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Playwright sync helpers
    # ------------------------------------------------------------------

    def _fetch_with_playwright_sync(self, url: str) -> str:
        from playwright.sync_api import sync_playwright

        previous_policy = asyncio.get_event_loop_policy()
        try:
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 1200})
                page.goto(url, wait_until="networkidle", timeout=settings.crawl_timeout_seconds * 1000)
                html = page.content()
                browser.close()
                return html
        except Exception:
            return ""
        finally:
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(previous_policy)

    def _capture_screenshot_sync(self, url: str) -> str:
        from playwright.sync_api import sync_playwright

        path = storage_path("screenshots", ".png")
        previous_policy = asyncio.get_event_loop_policy()
        try:
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(
                    viewport={"width": 1440, "height": 1000},
                    device_scale_factor=1,
                )
                page.goto(url, wait_until="networkidle", timeout=settings.crawl_timeout_seconds * 1000)
                page.screenshot(path=str(path), full_page=False)
                browser.close()
        except Exception:
            return ""
        finally:
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(previous_policy)
        return public_url(path)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def _needs_browser(self, html: str) -> bool:
        lower = html.lower()
        text_size = len(lower.replace("<script", ""))
        return text_size < 1800 and any(
            token in lower for token in ("__next", 'id="root"', 'id="app"', "vite")
        )

    def _allowed_by_robots(self, base_url: str, url: str) -> bool:
        parsed = urlparse(base_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        parser = urllib.robotparser.RobotFileParser()
        try:
            response = self.session.get(robots_url, timeout=5)
            if not response.ok:
                return True
            parser.parse(response.text.splitlines())
            return parser.can_fetch(HEADERS["User-Agent"], url)
        except Exception:
            return True

