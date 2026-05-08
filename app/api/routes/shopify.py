from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.modules.shopify.tools import shopify_get_orders, shopify_get_products

router = APIRouter()


@router.get("/orders")
async def get_orders(days: int = 1, status: str = "any"):
    return await shopify_get_orders(days=days, status=status)


@router.get("/products")
async def get_products():
    return await shopify_get_products()


class WebhookOrderBody(BaseModel):
    id: int
    email: str | None = None
    total_price: str | None = None
    financial_status: str | None = None


@router.post("/webhooks/order-created")
async def webhook_order_created(body: WebhookOrderBody, db: AsyncSession = Depends(get_db)):
    """Shopify order/created webhook — triggers post-purchase email flow."""
    if body.email:
        from app.modules.email_marketing.flows import trigger_flow
        await trigger_flow(
            flow_name="post_purchase",
            customer_email=body.email,
            customer_context={
                "order_value": body.total_price,
                "order_id": body.id,
            },
        )
    return {"received": True}


@router.post("/webhooks/cart-abandoned")
async def webhook_cart_abandoned(body: dict, db: AsyncSession = Depends(get_db)):
    """Cart abandonment webhook — triggers abandoned cart flow."""
    email = body.get("email")
    if email:
        from app.modules.email_marketing.flows import trigger_flow
        await trigger_flow(
            flow_name="abandoned_cart",
            customer_email=email,
            customer_context={
                "cart_value": body.get("total_price"),
                "last_product": body.get("line_items", [{}])[0].get("title"),
            },
        )
    return {"received": True}
