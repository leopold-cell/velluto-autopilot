"""Shopify Admin REST API client (async wrapper)."""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings

log = structlog.get_logger()

BASE = f"https://{settings.shopify_shop_name}/admin/api/{settings.shopify_api_version}"
HEADERS = {
    "X-Shopify-Access-Token": settings.shopify_access_token,
    "Content-Type": "application/json",
}


class ShopifyClient:
    def __init__(self):
        self._client = httpx.AsyncClient(base_url=BASE, headers=HEADERS, timeout=30.0)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get(self, path: str, params: dict | None = None) -> Any:
        r = await self._client.get(path, params=params)
        r.raise_for_status()
        return r.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def post(self, path: str, body: dict) -> Any:
        r = await self._client.post(path, json=body)
        r.raise_for_status()
        return r.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def put(self, path: str, body: dict) -> Any:
        r = await self._client.put(path, json=body)
        r.raise_for_status()
        return r.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def delete(self, path: str) -> Any:
        r = await self._client.delete(path)
        r.raise_for_status()
        return r.json()

    # ── Orders ────────────────────────────────────────────────────────────────

    async def get_orders(
        self,
        status: str = "any",
        created_at_min: str | None = None,
        limit: int = 250,
    ) -> list[dict]:
        params: dict[str, Any] = {"status": status, "limit": limit}
        if created_at_min:
            params["created_at_min"] = created_at_min
        data = await self.get("/orders.json", params=params)
        return data.get("orders", [])

    async def get_order(self, order_id: str) -> dict:
        data = await self.get(f"/orders/{order_id}.json")
        return data.get("order", {})

    # ── Products ──────────────────────────────────────────────────────────────

    async def get_products(self, limit: int = 250) -> list[dict]:
        data = await self.get("/products.json", params={"limit": limit})
        return data.get("products", [])

    async def get_product(self, product_id: str) -> dict:
        data = await self.get(f"/products/{product_id}.json")
        return data.get("product", {})

    async def update_product(self, product_id: str, updates: dict) -> dict:
        data = await self.put(f"/products/{product_id}.json", {"product": updates})
        return data.get("product", {})

    async def update_variant_price(self, variant_id: str, price: str) -> dict:
        data = await self.put(
            f"/variants/{variant_id}.json",
            {"variant": {"id": variant_id, "price": price}},
        )
        return data.get("variant", {})

    # ── Discounts ─────────────────────────────────────────────────────────────

    async def create_price_rule(self, rule: dict) -> dict:
        data = await self.post("/price_rules.json", {"price_rule": rule})
        return data.get("price_rule", {})

    async def create_discount_code(self, price_rule_id: str, code: str) -> dict:
        data = await self.post(
            f"/price_rules/{price_rule_id}/discount_codes.json",
            {"discount_code": {"code": code}},
        )
        return data.get("discount_code", {})

    # ── Metafields / SEO ──────────────────────────────────────────────────────

    async def update_product_metafields(self, product_id: str, fields: list[dict]) -> list[dict]:
        results = []
        for field in fields:
            data = await self.post(f"/products/{product_id}/metafields.json", {"metafield": field})
            results.append(data.get("metafield", {}))
        return results

    # ── Store analytics ───────────────────────────────────────────────────────

    async def get_report(self, since_date: str) -> dict:
        """Aggregate order stats since a date."""
        orders = await self.get_orders(status="any", created_at_min=since_date)
        total_revenue = sum(float(o.get("total_price", 0)) for o in orders)
        return {
            "order_count": len(orders),
            "revenue_eur": total_revenue,
            "aov": total_revenue / len(orders) if orders else 0,
        }
