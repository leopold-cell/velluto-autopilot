"""
Internal-link normalization for generated content.

Two directions are supported because the right format depends on the channel:

- On-site HTML (Shopify ``body_html``, GEO/blog content): internal links must be
  **root-relative** (``/products/handle``). Use :func:`to_relative_links`.
- Email / ads: relative links do not resolve there, so internal links must be
  **absolute** on the canonical storefront domain. Use :func:`to_absolute_links`.

An "internal" link is one pointing at the canonical storefront domain
(``settings.storefront_domain``), its ``www.`` variant, or the shop's
``*.myshopify.com`` domain. External links are always left untouched.
"""

from __future__ import annotations

import re
from typing import Any

from app.config import settings

# URL terminators: whitespace, quotes, angle brackets, and the closing
# delimiters of markdown links / parentheses. Keeps href="...", ](...) and
# bare URLs all working.
_TERM = r"\s\"'<>)\]"

# Matches absolute or protocol-relative URLs, capturing host + the remainder
# (path/query/fragment). The scheme is optional to also catch ``//host/...``.
_ABS_URL = re.compile(
    rf"(?P<scheme>https?:)?//(?P<host>[^/{_TERM}]+)(?P<rest>[/?#][^{_TERM}]*)?",
    re.IGNORECASE,
)

# Root-relative links inside an href attribute or a markdown link target.
# The negative lookahead ``(?!/)`` skips protocol-relative URLs (``//host``),
# which are handled by ``_ABS_URL`` instead.
_HREF_REL = re.compile(r"""(?P<pre>href\s*=\s*["'])(?P<path>/(?!/)[^"']*)""", re.IGNORECASE)
_MD_REL = re.compile(r"""(?P<pre>\]\()(?P<path>/(?!/)[^)\s]*)""")


def canonical_host() -> str:
    return settings.storefront_domain.strip().lower().rstrip("/")


def canonical_base() -> str:
    return f"https://{canonical_host()}"


def internal_hosts() -> set[str]:
    """Hosts that count as internal (lowercased, no port)."""
    hosts: set[str] = set()
    domain = canonical_host()
    if domain:
        hosts.add(domain)
        hosts.add(f"www.{domain}")
    shop = settings.shopify_shop_name.strip().lower()
    if shop:
        hosts.add(shop)
    return hosts


def _host_only(host: str) -> str:
    return host.split(":", 1)[0].lower()


def to_relative_links(text: str) -> str:
    """Rewrite absolute internal URLs to root-relative paths.

    ``https://velluto-shop.com/products/x?v=1#a`` -> ``/products/x?v=1#a``.
    External hosts and already-relative links are returned unchanged.
    """
    if not text:
        return text
    hosts = internal_hosts()

    def _sub(m: re.Match[str]) -> str:
        if _host_only(m.group("host")) not in hosts:
            return m.group(0)
        return m.group("rest") or "/"

    return _ABS_URL.sub(_sub, text)


def to_absolute_links(text: str, base: str | None = None) -> str:
    """Make internal links absolute on the canonical storefront domain.

    - Root-relative links in ``href`` / markdown targets gain the domain.
    - Absolute links on a non-canonical *internal* host (``www.``/myshopify)
      are normalized to the canonical host.
    External links are left untouched.
    """
    if not text:
        return text
    base = (base or canonical_base()).rstrip("/")
    hosts = internal_hosts()
    canon = canonical_host()

    def _canonicalize(m: re.Match[str]) -> str:
        host = _host_only(m.group("host"))
        if host not in hosts or host == canon:
            return m.group(0)
        return f"https://{canon}{m.group('rest') or '/'}"

    text = _ABS_URL.sub(_canonicalize, text)
    text = _HREF_REL.sub(lambda m: f"{m.group('pre')}{base}{m.group('path')}", text)
    text = _MD_REL.sub(lambda m: f"{m.group('pre')}{base}{m.group('path')}", text)
    return text


def normalize_content_links(obj: Any, mode: str = "relative") -> Any:
    """Recursively normalize every string field in a JSON-like structure.

    ``mode="relative"`` for on-site content, ``mode="absolute"`` for email/ads.
    """
    transform = to_absolute_links if mode == "absolute" else to_relative_links
    if isinstance(obj, str):
        return transform(obj)
    if isinstance(obj, dict):
        return {k: normalize_content_links(v, mode) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize_content_links(v, mode) for v in obj]
    return obj
