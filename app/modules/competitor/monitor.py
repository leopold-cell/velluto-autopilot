"""
Competitor monitoring — scrapes competitor product pages daily.
Tracks pricing changes, new products, and promotional activity.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog
from bs4 import BeautifulSoup

from app.config import settings
from app.redis_client import get_redis

log = structlog.get_logger()


class CompetitorMonitor:
    def __init__(self):
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
                )
            },
            timeout=20.0,
            follow_redirects=True,
        )

    async def scan_all(self) -> dict[str, Any]:
        results = []
        changes = []

        for url in settings.competitor_urls:
            try:
                scan = await self.scan_url(url)
                results.append(scan)
                if scan.get("changes"):
                    changes.extend(scan["changes"])
            except Exception as e:
                log.warning("competitor.scan_failed", url=url, error=str(e))
                results.append({"url": url, "error": str(e)})

        return {
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "competitors_scanned": len(settings.competitor_urls),
            "total_changes": len(changes),
            "results": results,
            "changes": changes,
        }

    async def scan_url(self, url: str) -> dict[str, Any]:
        r = await self._client.get(url)
        soup = BeautifulSoup(r.text, "html.parser")

        data = {
            "url": url,
            "title": soup.title.string if soup.title else "",
            "prices": self._extract_prices(soup),
            "promotions": self._extract_promotions(soup),
            "products": self._extract_product_names(soup),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }

        changes = await self._detect_changes(url, data)
        data["changes"] = changes

        # Cache current state
        r_client = await get_redis()
        cache_key = f"competitor:{hashlib.md5(url.encode()).hexdigest()}"
        await r_client.set(cache_key, json.dumps(data), ex=60 * 60 * 25)

        return data

    def _extract_prices(self, soup: BeautifulSoup) -> list[str]:
        prices = []
        for elem in soup.find_all(class_=lambda c: c and "price" in c.lower()):
            text = elem.get_text(strip=True)
            if text and any(c.isdigit() for c in text):
                prices.append(text[:50])
        return list(set(prices))[:20]

    def _extract_promotions(self, soup: BeautifulSoup) -> list[str]:
        promo_terms = ["sale", "off", "discount", "% off", "deal", "offer", "promo", "save"]
        promos = []
        for elem in soup.find_all(string=True):
            text = elem.strip().lower()
            if any(term in text for term in promo_terms) and len(text) < 100:
                promos.append(elem.strip()[:100])
        return list(set(promos))[:10]

    def _extract_product_names(self, soup: BeautifulSoup) -> list[str]:
        products = []
        for elem in soup.find_all(["h2", "h3"], class_=lambda c: c and "product" in str(c).lower()):
            text = elem.get_text(strip=True)
            if text:
                products.append(text[:80])
        return products[:20]

    async def _detect_changes(self, url: str, current: dict) -> list[dict]:
        r_client = await get_redis()
        cache_key = f"competitor:{hashlib.md5(url.encode()).hexdigest()}"
        prev_data = await r_client.get(cache_key)

        if not prev_data:
            return []

        prev = json.loads(prev_data)
        changes = []

        old_prices = set(prev.get("prices", []))
        new_prices = set(current.get("prices", []))
        if old_prices != new_prices:
            changes.append({
                "type": "price_change",
                "url": url,
                "added": list(new_prices - old_prices),
                "removed": list(old_prices - new_prices),
            })

        old_promos = set(prev.get("promotions", []))
        new_promos = set(current.get("promotions", []))
        added_promos = new_promos - old_promos
        if added_promos:
            changes.append({
                "type": "new_promotion",
                "url": url,
                "promotions": list(added_promos),
            })

        return changes
