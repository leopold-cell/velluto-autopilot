"""Tests for Shopify module tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
import respx
import httpx

from app.modules.shopify.tools import (
    shopify_get_orders,
    shopify_get_products,
    shopify_update_product_price,
    shopify_update_product_seo,
    shopify_create_discount,
)


MOCK_ORDERS = {
    "orders": [
        {"id": 1, "name": "#1001", "total_price": "149.00", "created_at": "2026-05-08T10:00:00Z", "financial_status": "paid"},
        {"id": 2, "name": "#1002", "total_price": "199.00", "created_at": "2026-05-08T11:00:00Z", "financial_status": "paid"},
    ]
}

MOCK_PRODUCTS = {
    "products": [
        {
            "id": 1,
            "title": "Velluto Pro Aero",
            "variants": [{"id": 11, "title": "Default", "price": "189.00", "inventory_quantity": 50}],
        }
    ]
}


@pytest.mark.asyncio
class TestShopifyOrders:
    @respx.mock
    async def test_get_orders_returns_count_and_revenue(self):
        respx.get(url__contains="/orders.json").mock(
            return_value=httpx.Response(200, json=MOCK_ORDERS)
        )
        result = await shopify_get_orders(days=1)
        assert result["order_count"] == 2
        assert result["revenue_eur"] == 348.0
        assert result["aov_eur"] == 174.0

    @respx.mock
    async def test_get_orders_empty_returns_zeros(self):
        respx.get(url__contains="/orders.json").mock(
            return_value=httpx.Response(200, json={"orders": []})
        )
        result = await shopify_get_orders(days=1)
        assert result["order_count"] == 0
        assert result["revenue_eur"] == 0
        assert result["aov_eur"] == 0


@pytest.mark.asyncio
class TestShopifyProducts:
    @respx.mock
    async def test_get_products_returns_structured_data(self):
        respx.get(url__contains="/products.json").mock(
            return_value=httpx.Response(200, json=MOCK_PRODUCTS)
        )
        result = await shopify_get_products()
        assert result["count"] == 1
        assert result["products"][0]["title"] == "Velluto Pro Aero"
        assert len(result["products"][0]["variants"]) == 1


@pytest.mark.asyncio
class TestShopifyPriceUpdate:
    async def test_dry_run_does_not_mutate(self):
        with patch("app.modules.shopify.tools.client") as mock_client:
            mock_client.get_product = AsyncMock(return_value={
                "variants": [{"id": "11", "price": "189.00"}]
            })
            result = await shopify_update_product_price(
                product_id="1", variant_id="11", new_price=199.0, reason="test", dry_run=True
            )
        assert result["dry_run"] is True
        assert result["current_price"] == "189.00"
        assert result["new_price"] == 199.0
        mock_client.update_variant_price.assert_not_called()

    @respx.mock
    async def test_live_update_calls_api(self):
        with patch("app.modules.shopify.tools.client") as mock_client:
            mock_client.get_product = AsyncMock(return_value={"variants": [{"id": "11", "price": "189.00"}]})
            mock_client.update_variant_price = AsyncMock(return_value={"id": "11", "price": "199.00"})

            result = await shopify_update_product_price(
                product_id="1", variant_id="11", new_price=199.0, reason="test", dry_run=False
            )
        assert result["updated"] is True
        mock_client.update_variant_price.assert_called_once()


@pytest.mark.asyncio
class TestShopifyDiscount:
    async def test_dry_run_returns_preview(self):
        result = await shopify_create_discount(
            code="CYCLE10", percent_off=10, reason="test", dry_run=True
        )
        assert result["dry_run"] is True
        assert result["would_create"]["code"] == "CYCLE10"
