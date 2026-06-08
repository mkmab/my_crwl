import re
from collections import Counter
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.models import PageContent
from app.utils.url import absolute_url


EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+?\d[\s().-]?){8,}\d")
SOCIAL_HOSTS = ("linkedin.com", "twitter.com", "x.com", "facebook.com", "instagram.com", "youtube.com", "tiktok.com")


def clean_text(value: str | None, max_length: int = 500) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()[:max_length]


def soup_from_html(html: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return soup


def extract_page(url: str, html: str) -> PageContent:
    soup = soup_from_html(html)
    title = clean_text(soup.title.string if soup.title else "")
    meta = soup.find("meta", attrs={"name": "description"})
    meta_description = clean_text(meta.get("content") if meta else "")
    headings = [clean_text(h.get_text(" ")) for h in soup.find_all(["h1", "h2", "h3"]) if clean_text(h.get_text(" "))]
    paragraphs = [clean_text(p.get_text(" "), 800) for p in soup.find_all("p") if clean_text(p.get_text(" "))]
    buttons = [clean_text(b.get_text(" ")) for b in soup.find_all(["button", "a"]) if _looks_like_cta(b)]
    nav_links = _extract_nav_links(url, soup)
    footer_node = soup.find("footer")
    footer = clean_text(footer_node.get_text(" "), 1200) if footer_node else ""
    visible_text = clean_text(soup.get_text(" "), 8000)
    emails = sorted(set(EMAIL_RE.findall(visible_text)))
    phones = sorted(set(clean_text(match) for match in PHONE_RE.findall(visible_text)))
    images = [img for img in (_image_url(url, tag) for tag in soup.find_all("img")) if img]
    social_links = sorted({link["href"] for link in soup.find_all("a", href=True) if any(host in link["href"] for host in SOCIAL_HOSTS)})

    return PageContent(
        url=url,
        title=title,
        meta_description=meta_description,
        headings=headings[:40],
        paragraphs=paragraphs[:80],
        buttons=buttons[:30],
        navigation_links=nav_links[:60],
        footer=footer,
        cta_text=buttons[:20],
        emails=emails,
        phone_numbers=phones,
        social_links=social_links,
        images=images[:80],
        visible_text=visible_text,
    )


def extract_logo_and_favicon(base_url: str, html: str) -> tuple[str, str, str]:
    soup = BeautifulSoup(html, "html.parser")
    logo_selectors = [
        "img.logo",
        ".logo img",
        "img[class*=logo]",
        "img[alt*=logo i]",
        ".navbar-brand img",
        "header img",
    ]
    logo = ""
    for selector in logo_selectors:
        node = soup.select_one(selector)
        logo = _image_url(base_url, node) if node else ""
        if logo:
            break

    icon = soup.find("link", rel=lambda value: value and any("icon" in item.lower() for item in value))
    favicon = absolute_url(base_url, icon.get("href")) if icon else absolute_url(base_url, "/favicon.ico")
    og = soup.find("meta", property="og:image")
    og_image = absolute_url(base_url, og.get("content")) if og else ""
    return logo or og_image or favicon or "", favicon or "", og_image or ""


def extract_colors(html: str) -> list[str]:
    colors = re.findall(r"#[0-9a-fA-F]{3,6}\b|rgba?\([^)]+\)", html)
    normalized = [_normalize_color(color) for color in colors]
    return [color for color, _ in Counter(c for c in normalized if c).most_common(8)]


def detect_technologies(html: str, headers: dict[str, str] | None = None) -> list[str]:
    haystack = html.lower()
    clues = {
        "React": ("react", "__react", "data-reactroot"),
        "Next.js": ("__next", "next/static", "next-route"),
        "Vue": ("vue", "__vue__"),
        "Angular": ("ng-version", "angular"),
        "WordPress": ("wp-content", "wp-json", "wordpress"),
        "Shopify": ("cdn.shopify.com", "shopify"),
        "Tailwind": ("tailwind", "font-sans", "text-slate"),
        "Bootstrap": ("bootstrap", "btn btn-", "container-fluid"),
    }
    found = [name for name, tokens in clues.items() if any(token in haystack for token in tokens)]
    if headers:
        server = headers.get("server") or headers.get("Server") or ""
        if server:
            found.append(f"Server: {server}")
    return sorted(set(found))


def important_internal_links(base_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    keywords = ("about", "service", "pricing", "feature", "contact", "product", "solution")
    ranked: list[tuple[int, str]] = []
    for link in soup.find_all("a", href=True):
        href = absolute_url(base_url, link["href"])
        if not href:
            continue
        path = urlparse(href).path.lower()
        text = clean_text(link.get_text(" ")).lower()
        score = sum(1 for keyword in keywords if keyword in path or keyword in text)
        if score:
            ranked.append((score, href))
    return list(dict.fromkeys(url for _, url in sorted(ranked, reverse=True)))


def _extract_nav_links(base_url: str, soup: BeautifulSoup) -> list[dict[str, str]]:
    nodes = soup.select("nav a[href], header a[href], a[href]")
    links = []
    for node in nodes:
        href = absolute_url(base_url, node.get("href"))
        text = clean_text(node.get_text(" "), 120)
        if href and text:
            links.append({"text": text, "url": href})
    return links


def _image_url(base_url: str, node) -> str:
    if not node:
        return ""
    src = node.get("src") or node.get("data-src") or node.get("data-lazy-src")
    return absolute_url(base_url, src) or ""


def _looks_like_cta(node) -> bool:
    text = clean_text(node.get_text(" "), 120).lower()
    class_name = " ".join(node.get("class", [])).lower()
    cta_words = ("start", "try", "buy", "book", "contact", "demo", "sign up", "get", "learn", "download", "subscribe")
    return bool(text) and (node.name == "button" or "btn" in class_name or any(word in text for word in cta_words))


def _normalize_color(value: str) -> str:
    value = value.strip()
    if value.startswith("#"):
        if len(value) == 4:
            return "#" + "".join(ch * 2 for ch in value[1:]).lower()
        return value[:7].lower()
    nums = [int(float(num)) for num in re.findall(r"[\d.]+", value)[:3]]
    if len(nums) == 3:
        return "#{:02x}{:02x}{:02x}".format(*[max(0, min(255, n)) for n in nums])
    return ""
