import re
from collections import Counter
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.models import PageContent
from app.utils.url import absolute_url


# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------

EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)

# Obfuscated email patterns: "name [at] domain [dot] com"
EMAIL_OBFUSCATED_RE = re.compile(
    r"([\w._%+\-]+)\s*[\[\(]?\s*(?:at|@)\s*[\]\)]?\s*([\w.\-]+)\s*[\[\(]?\s*(?:dot|\.)\s*[\]\)]?\s*(\w{2,6})",
    re.I,
)

PHONE_RE = re.compile(r"(?:\+?\d[\s().\-]?){8,}\d")

SOCIAL_HOSTS = (
    "linkedin.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "youtube.com",
    "tiktok.com",
    "github.com",
    "pinterest.com",
    "threads.net",
)

# Title/role markers for owner detection
OWNER_TITLE_MARKERS = (
    "ceo", "founder", "co-founder", "cofounder", "owner",
    "director", "managing director", "president", "chief",
    "principal", "partner", "head of", "chief executive",
)

GENERIC_EMAIL_PREFIXES = (
    "info", "contact", "support", "admin", "sales", "hello", "team", "mail",
    "office", "service", "help", "careers", "jobs", "press", "marketing",
    "billing", "accounts", "no-reply", "noreply",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NON_NAME_TOKENS = {
    "about", "academy", "admin", "advisor", "agency", "blog", "book", "brand", "business",
    "careers", "ceo", "chief", "co", "company", "contact", "customer", "demo", "department",
    "design", "digital", "director", "download", "enterprise", "executive", "expert", "faq", "footer",
    "founder", "founders", "get", "global", "group", "head", "hero", "home", "inc", "info",
    "leadership", "learn", "llc", "login", "management", "manager", "marketing", "member", "mission", "officer", "operations", "our",
    "owner", "page", "partner", "people", "person", "portfolio", "president", "pricing", "privacy",
    "product", "resources", "sales", "service", "solutions", "staff", "story", "success", "support", "technology", "team", "terms",
    "the", "trust", "us", "view", "welcome", "who", "with", "work",
}


def clean_text(value: str | None, max_length: int = 500) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()[:max_length]


def looks_like_person_name(value: str | None) -> bool:
    if not value:
        return False
    cleaned = clean_text(value, 120)
    if not cleaned:
        return False
    if any(ch.isdigit() for ch in cleaned):
        return False

    parts = [p.strip(".,") for p in re.split(r"\s+", cleaned) if p.strip(".,")]
    if not 2 <= len(parts) <= 4:
        return False

    normalized: list[str] = []
    for part in parts:
        simple = part.replace("-", "").replace("'", "")
        if len(simple) < 2 or not simple.isalpha():
            return False
        if simple.lower() in NON_NAME_TOKENS:
            return False
        if not (part[:1].isupper() or part.isupper()):
            return False
        normalized.append(simple.lower())

    if len(set(normalized)) != len(normalized):
        return False
    return True


def soup_from_html(html: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return soup


# ---------------------------------------------------------------------------
# Deep email extraction
# ---------------------------------------------------------------------------

def extract_emails_deep(html: str) -> list[str]:
    """
    Find emails using three strategies:
    1. Standard regex on visible text
    2. mailto: hrefs (catches emails hidden from visible text)
    3. Obfuscated patterns like 'name [at] domain [dot] com'
    """
    emails: set[str] = set()

    # 1. Standard regex on raw html (catches data attrs, comments, etc.)
    emails.update(EMAIL_RE.findall(html))

    # 2. mailto hrefs
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = str(a["href"])
        if href.lower().startswith("mailto:"):
            addr = href[7:].split("?")[0].strip()
            if addr and "@" in addr:
                emails.add(addr)

    # 3. Obfuscated
    for match in EMAIL_OBFUSCATED_RE.finditer(html):
        user, domain, tld = match.group(1), match.group(2), match.group(3)
        addr = f"{user}@{domain}.{tld}"
        if EMAIL_RE.match(addr):
            emails.add(addr)

    # Filter junk
    bad = (".png", ".jpg", ".gif", ".svg", ".css", ".js", ".woff")
    return sorted(e for e in emails if not any(e.lower().endswith(b) for b in bad))


def rank_emails(emails: list[str]) -> list[str]:
    """
    Sort emails so personal/owner-like ones come first.
    Generic support/info addresses go last.
    """
    generic = ("info@", "contact@", "support@", "admin@", "sales@",
                "hello@", "no-reply@", "noreply@", "team@", "mail@")

    def score(e: str) -> int:
        e_lower = e.lower()
        if any(e_lower.startswith(g) for g in generic):
            return 0    # generic — lowest priority
        if re.match(r"^[a-z]+\.[a-z]+@", e_lower):
            return 3    # firstname.lastname@ — best signal
        if re.match(r"^[a-z]+@", e_lower):
            return 2    # single name prefix
        return 1

    return sorted(emails, key=score, reverse=True)


def is_personal_email(email: str | None) -> bool:
    if not email or "@" not in email:
        return False
    local = email.split("@", 1)[0].lower().strip()
    if not local or local in GENERIC_EMAIL_PREFIXES:
        return False
    if any(local.startswith(prefix + ".") or local.startswith(prefix + "-") for prefix in GENERIC_EMAIL_PREFIXES):
        return False
    return bool(re.match(r"^[a-z][a-z.\-_]{1,48}$", local))

# ---------------------------------------------------------------------------
# Owner name extraction from HTML structure
# ---------------------------------------------------------------------------

def extract_owner_from_soup(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    """
    Try to find a decision-maker name + title from team/about page HTML.
    Returns (name, title) or (None, None).
    """
    # Strategy 1: Structured team cards
    card_selectors = [
        ".team-member", ".team-card", ".founder", ".staff-member",
        "[class*=team]", "[class*=people]", "[class*=member]",
        "[class*=founder]", "[class*=leadership]",
        "article", ".card",
    ]
    for selector in card_selectors:
        for card in soup.select(selector):
            title_text = card.get_text(" ").lower()
            if not any(m in title_text for m in OWNER_TITLE_MARKERS):
                continue
            name_el = card.find(["h2", "h3", "h4", "strong", "b"])
            if name_el:
                name = clean_text(name_el.get_text(" "), 80)
                if looks_like_person_name(name):
                    return name, None

    # Strategy 2: Scan all text lines for "Name, CEO" or "CEO: Name" patterns
    full_text = soup.get_text("\n")
    for line in full_text.splitlines():
        line = line.strip()
        if not line or len(line) > 120:
            continue
        low = line.lower()
        if any(m in low for m in OWNER_TITLE_MARKERS):
            # Try to extract a proper name: consecutive Title-cased words
            names = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b", line)
            for name in names:
                if looks_like_person_name(name):
                    return name, None

    return None, None


# ---------------------------------------------------------------------------
# Page extraction
# ---------------------------------------------------------------------------

def extract_page(url: str, html: str) -> PageContent:
    soup = soup_from_html(html)
    title = clean_text(soup.title.string if soup.title else "")
    meta = soup.find("meta", attrs={"name": "description"})
    meta_description = clean_text(meta.get("content") if meta else "")
    headings = [
        clean_text(h.get_text(" "))
        for h in soup.find_all(["h1", "h2", "h3"])
        if clean_text(h.get_text(" "))
    ]
    paragraphs = [
        clean_text(p.get_text(" "), 800)
        for p in soup.find_all("p")
        if clean_text(p.get_text(" "))
    ]
    buttons = [clean_text(b.get_text(" ")) for b in soup.find_all(["button", "a"]) if _looks_like_cta(b)]
    nav_links = _extract_nav_links(url, soup)
    footer_node = soup.find("footer")
    footer = clean_text(footer_node.get_text(" "), 1200) if footer_node else ""
    visible_text = clean_text(soup.get_text(" "), 8000)

    # Deep email extraction
    emails = rank_emails(extract_emails_deep(html))
    phones = sorted(set(clean_text(match) for match in PHONE_RE.findall(visible_text)))
    images = [img for img in (_image_url(url, tag) for tag in soup.find_all("img")) if img]
    social_links = sorted({
        link["href"]
        for link in soup.find_all("a", href=True)
        if any(host in link["href"] for host in SOCIAL_HOSTS)
    })

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


# ---------------------------------------------------------------------------
# Logo / favicon / og:image
# ---------------------------------------------------------------------------

def extract_logo_and_favicon(base_url: str, html: str) -> tuple[str, str, str]:
    soup = BeautifulSoup(html, "html.parser")
    logo_selectors = [
        "img.logo",
        ".logo img",
        "img[class*=logo]",
        "img[alt*=logo i]",
        ".navbar-brand img",
        "header img",
        "a[href='/'] img",
    ]
    logo = ""
    for selector in logo_selectors:
        node = soup.select_one(selector)
        logo = _image_url(base_url, node) if node else ""
        if logo:
            break

    icon = soup.find(
        "link",
        rel=lambda value: value and any("icon" in item.lower() for item in value),
    )
    favicon = (
        absolute_url(base_url, icon.get("href"))
        if icon
        else absolute_url(base_url, "/favicon.ico")
    )
    og = soup.find("meta", property="og:image")
    og_image = absolute_url(base_url, og.get("content")) if og else ""

    # Fallback: Clearbit logo CDN (free, no API key)
    domain = urlparse(base_url).netloc.lower().removeprefix("www.")
    clearbit_logo = f"https://logo.clearbit.com/{domain}" if domain else ""

    return logo or og_image or clearbit_logo or favicon or "", favicon or "", og_image or ""


# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------

def extract_colors(html: str) -> list[str]:
    colors = re.findall(r"#[0-9a-fA-F]{3,6}\b|rgba?\([^)]+\)", html)
    normalized = [_normalize_color(color) for color in colors]
    # Filter out near-black, near-white, and grey — keep brand colours
    filtered = [
        c for c in normalized
        if c and not _is_neutral(c)
    ]
    top = [color for color, _ in Counter(filtered).most_common(12)]
    # If we filtered too aggressively, fall back to all colors
    if not top:
        top = [color for color, _ in Counter(c for c in normalized if c).most_common(8)]
    return top[:8]


def _is_neutral(hex_color: str) -> bool:
    """Return True if the color is near-white, near-black, or grey."""
    try:
        h = hex_color.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        brightness = (r + g + b) / 3
        # Is it grey? (R ≈ G ≈ B)
        spread = max(r, g, b) - min(r, g, b)
        if spread < 25:
            return True
        # Is it near-white or near-black?
        if brightness > 230 or brightness < 25:
            return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Technology detection
# ---------------------------------------------------------------------------

def detect_technologies(html: str, headers: dict[str, str] | None = None) -> list[str]:
    haystack = html.lower()
    clues = {
        "React": ("react", "__react", "data-reactroot"),
        "Next.js": ("__next", "next/static", "next-route"),
        "Vue": ("vue", "__vue__"),
        "Angular": ("ng-version", "angular"),
        "WordPress": ("wp-content", "wp-json", "wordpress"),
        "Shopify": ("cdn.shopify.com", "shopify"),
        "Webflow": ("webflow", "wf-form"),
        "Squarespace": ("squarespace", "static.squarespace"),
        "Wix": ("wix.com", "wixstatic"),
        "Framer": ("framer.com", "framer-motion"),
        "Tailwind": ("tailwind", "font-sans", "text-slate"),
        "Bootstrap": ("bootstrap", "btn btn-", "container-fluid"),
        "jQuery": ("jquery", "$.fn", "$.ajax"),
        "HubSpot": ("hubspot", "hs-cta", "hbspt"),
        "Intercom": ("intercom", "intercomcdn"),
        "Stripe": ("stripe.com/v3", "stripe.js"),
        "Google Analytics": ("gtag", "google-analytics", "ga('send"),
        "Hotjar": ("hotjar", "hj("),
    }
    found = [name for name, tokens in clues.items() if any(token in haystack for token in tokens)]
    if headers:
        server = headers.get("server") or headers.get("Server") or ""
        powered = headers.get("x-powered-by") or headers.get("X-Powered-By") or ""
        if server:
            found.append(f"Server: {server}")
        if powered:
            found.append(f"Powered-By: {powered}")
    return sorted(set(found))


# ---------------------------------------------------------------------------
# Internal link ranking
# ---------------------------------------------------------------------------

def important_internal_links(base_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")

    # High-value paths — especially for owner/team discovery
    keywords = (
        "about", "team", "people", "founders", "leadership", "staff", "who-we-are",
        "service", "services", "pricing", "feature", "features",
        "contact", "contact-us", "get-in-touch",
        "product", "products", "solution", "solutions",
        "case-study", "testimonial", "portfolio", "work",
        "blog", "news",
    )

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


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

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
    src = (
        node.get("src")
        or node.get("data-src")
        or node.get("data-lazy-src")
        or node.get("data-original")
    )
    return absolute_url(base_url, src) or ""


def _looks_like_cta(node) -> bool:
    text = clean_text(node.get_text(" "), 120).lower()
    class_name = " ".join(node.get("class", [])).lower()
    cta_words = (
        "start", "try", "buy", "book", "contact", "demo",
        "sign up", "get", "learn", "download", "subscribe",
        "schedule", "request", "free", "quote", "consult",
    )
    return bool(text) and (
        node.name == "button"
        or "btn" in class_name
        or any(word in text for word in cta_words)
    )


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

