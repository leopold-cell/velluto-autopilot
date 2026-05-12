"""
Shopify tool definitions for the orchestrator.
Each tool is an async function + an Anthropic tool spec.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from app.modules.shopify.client import ShopifyClient

log = structlog.get_logger()

client = ShopifyClient()

# ── Tool specs (Anthropic tool_use schema) ────────────────────────────────────

TOOL_SPECS = [
    {
        "name": "shopify_get_orders",
        "description": "Get recent Shopify orders with totals. Use to understand sales velocity.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Look-back window in days", "default": 1},
                "status": {
                    "type": "string",
                    "enum": ["open", "closed", "cancelled", "any"],
                    "default": "any",
                },
            },
            "required": [],
        },
    },
    {
        "name": "shopify_get_products",
        "description": "Get all Shopify products with prices, variants and inventory levels.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "shopify_update_product_price",
        "description": "Update a product variant price. HIGH RISK — always requires approval.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
                "variant_id": {"type": "string"},
                "new_price": {"type": "number"},
                "reason": {"type": "string"},
            },
            "required": ["product_id", "variant_id", "new_price", "reason"],
        },
    },
    {
        "name": "shopify_update_product_seo",
        "description": "Update a product's SEO title and description. Low risk.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string"},
                "seo_title": {"type": "string"},
                "seo_description": {"type": "string"},
            },
            "required": ["product_id", "seo_title", "seo_description"],
        },
    },
    {
        "name": "shopify_create_discount",
        "description": (
            "Create a discount code. HIGH RISK — requires approval. "
            "Only use for targeted campaigns, never blanket."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "percent_off": {"type": "number"},
                "usage_limit": {"type": "integer"},
                "target_segment": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["code", "percent_off", "reason"],
        },
    },
]


# ── Executor functions ────────────────────────────────────────────────────────

B2B_TAGS = {"b2b_order", "b2b_sample"}


def _is_b2b(order: dict) -> bool:
    tags = {t.strip().lower() for t in order.get("tags", "").split(",")}
    return bool(tags & B2B_TAGS)


async def shopify_get_orders(days: int = 1, status: str = "any") -> dict[str, Any]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    all_orders = await client.get_orders(status=status, created_at_min=since)
    orders = [o for o in all_orders if not _is_b2b(o)]
    total_rev = sum(float(o.get("total_price", 0)) for o in orders)
    return {
        "order_count": len(orders),
        "revenue_eur": round(total_rev, 2),
        "aov_eur": round(total_rev / len(orders), 2) if orders else 0,
        "orders": [
            {
                "id": o["id"],
                "name": o.get("name"),
                "total_price": o.get("total_price"),
                "created_at": o.get("created_at"),
                "financial_status": o.get("financial_status"),
            }
            for o in orders[:20]
        ],
    }


async def shopify_get_products() -> dict[str, Any]:
    products = await client.get_products()
    return {
        "count": len(products),
        "products": [
            {
                "id": str(p["id"]),
                "title": p.get("title"),
                "variants": [
                    {
                        "id": str(v["id"]),
                        "title": v.get("title"),
                        "price": v.get("price"),
                        "inventory_quantity": v.get("inventory_quantity"),
                    }
                    for v in p.get("variants", [])
                ],
            }
            for p in products
        ],
    }


async def shopify_update_product_price(
    product_id: str,
    variant_id: str,
    new_price: float,
    reason: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    if dry_run:
        current = await client.get_product(product_id)
        variant = next(
            (v for v in current.get("variants", []) if str(v["id"]) == variant_id), None
        )
        return {
            "dry_run": True,
            "current_price": variant.get("price") if variant else "unknown",
            "new_price": new_price,
            "delta": new_price - float(variant.get("price", 0)) if variant else None,
        }

    result = await client.update_variant_price(variant_id, str(new_price))
    return {"updated": True, "variant_id": variant_id, "new_price": result.get("price")}


async def shopify_update_product_seo(
    product_id: str,
    seo_title: str,
    seo_description: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    if dry_run:
        return {"dry_run": True, "would_update": {"seo_title": seo_title, "seo_description": seo_description}}

    result = await client.update_product(
        product_id,
        {"metafields_global_title_tag": seo_title, "metafields_global_description_tag": seo_description},
    )
    return {"updated": True, "product_id": product_id}


async def shopify_create_discount(
    code: str,
    percent_off: float,
    reason: str,
    usage_limit: int = 1,
    target_segment: str = "general",
    dry_run: bool = False,
) -> dict[str, Any]:
    if dry_run:
        return {
            "dry_run": True,
            "would_create": {"code": code, "percent_off": percent_off, "usage_limit": usage_limit},
        }
    rule = await client.create_price_rule({
        "title": f"Autopilot: {reason}",
        "target_type": "line_item",
        "target_selection": "all",
        "allocation_method": "across",
        "value_type": "percentage",
        "value": f"-{percent_off}",
        "customer_selection": "all",
        "usage_limit": usage_limit,
        "starts_at": datetime.now(timezone.utc).isoformat(),
    })
    discount = await client.create_discount_code(str(rule["id"]), code)
    return {"created": True, "code": discount.get("code"), "price_rule_id": rule["id"]}


# ── Dispatch table ────────────────────────────────────────────────────────────

EXECUTORS = {
    "shopify_get_orders": shopify_get_orders,
    "shopify_get_products": shopify_get_products,
    "shopify_update_product_price": shopify_update_product_price,
    "shopify_update_product_seo": shopify_update_product_seo,
    "shopify_create_discount": shopify_create_discount,
}
