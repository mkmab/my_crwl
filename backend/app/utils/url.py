from urllib.parse import urljoin, urlparse, urlunparse


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.scheme:
        parsed = urlparse(f"https://{url.strip()}")
    clean = parsed._replace(fragment="")
    return urlunparse(clean)


def is_internal(base_url: str, candidate: str) -> bool:
    base_host = urlparse(base_url).netloc.lower().removeprefix("www.")
    candidate_host = urlparse(candidate).netloc.lower().removeprefix("www.")
    return bool(candidate_host) and candidate_host == base_host


def absolute_url(base_url: str, href: str | None) -> str | None:
    if not href:
        return None
    href = href.strip()
    if href.startswith(("mailto:", "tel:", "javascript:", "#")):
        return None
    return normalize_url(urljoin(base_url, href))
