import asyncio
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urlparse
import sys

import requests

from app.crawler.extractors import (
    detect_technologies,
    extract_colors,
    extract_logo_and_favicon,
    extract_page,
    important_internal_links,
)
from app.models import CrawlResult, PageContent
from app.utils.config import settings
from app.utils.storage import public_url, storage_path
from app.utils.url import is_internal, normalize_url


HEADERS = {
    "User-Agent": "MyCRWLBot/1.0 (+local website intelligence crawler)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


@dataclass
class FetchResult:
    url: str
    html: str
    headers: dict[str, str]


class WebsiteCrawler:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    async def crawl(self, raw_url: str) -> CrawlResult:
        url = normalize_url(raw_url)
        first = await self.fetch(url)
        candidates = [url] + important_internal_links(first.url, first.html)
        pages: list[PageContent] = []
        seen: set[str] = set()

        for candidate in candidates:
            if len(pages) >= settings.crawl_max_pages:
                break
            if candidate in seen or not is_internal(first.url, candidate):
                continue
            seen.add(candidate)
            if not self._allowed_by_robots(first.url, candidate):
                continue
            fetched = first if candidate == url else await self.fetch(candidate)
            if fetched.html:
                pages.append(extract_page(fetched.url, fetched.html))

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
        )

    async def fetch(self, url: str) -> FetchResult:
        try:
            response = self.session.get(url, timeout=settings.crawl_timeout_seconds, allow_redirects=True)
            content_type = response.headers.get("content-type", "")
            if response.ok and "text/html" in content_type:
                html = response.text
                if self._needs_browser(html):
                    rendered = await self.fetch_with_playwright(response.url)
                    if rendered:
                        return FetchResult(response.url, rendered, dict(response.headers))
                return FetchResult(response.url, html, dict(response.headers))
        except requests.RequestException:
            pass

        rendered = await self.fetch_with_playwright(url)
        return FetchResult(url, rendered, {})

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
                page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
                page.goto(url, wait_until="networkidle", timeout=settings.crawl_timeout_seconds * 1000)
                page.screenshot(path=str(path), full_page=False)
                browser.close()
        finally:
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(previous_policy)
        return public_url(path)

    def _needs_browser(self, html: str) -> bool:
        lower = html.lower()
        text_size = len(lower.replace("<script", ""))
        return text_size < 1800 and any(token in lower for token in ("__next", "id=\"root\"", "id=\"app\"", "vite"))

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
