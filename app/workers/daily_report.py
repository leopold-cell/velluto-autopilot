"""
Daily report generator — runs at 08:30 Europe/Berlin.
Generates a WhatsApp summary + stores to DB for web dashboard.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog

from app.config import settings

log = structlog.get_logger()


async def generate_and_send() -> dict[str, Any]:
    from app.database import AsyncSessionLocal
    from app.modules.kpi.engine import KpiEngine
    from app.modules.token_optimizer.optimizer import TokenOptimizer
    from app.modules.whatsapp.client import WhatsAppClient

    async with AsyncSessionLocal() as db:
        kpi = KpiEngine(db)
        dashboard = await kpi.get_dashboard()
        trend = await kpi.get_trend(days=7)

    token_report = await TokenOptimizer().get_daily_report()
    report_text = _format_report(dashboard, trend, token_report)

    client = WhatsAppClient()
    await client.send_text(report_text)

    log.info("daily_report.sent", orders=dashboard["sales"]["orders_today"])
    return {"sent": True, "report_preview": report_text[:200]}


def _format_report(dashboard: dict, trend: list, tokens: dict) -> str:
    s = dashboard["sales"]
    m = dashboard["meta_ads"]
    seo = dashboard["seo"]
    cro = dashboard["cro"]
    email = dashboard["email"]

    # 7-day context
    orders_7d = sum(d["orders"] for d in trend)
    revenue_7d = sum(d["revenue_eur"] for d in trend)
    spend_7d = sum(d["spend_eur"] for d in trend)

    pacing_emoji = "✅" if s["pacing_pct"] >= 85 else "⚠️" if s["pacing_pct"] >= 60 else "🚨"
    roas_emoji = "✅" if m["roas"] >= 3.0 else "⚠️" if m["roas"] >= 1.5 else "🚨"

    date = datetime.now(timezone.utc).strftime("%a %d %b")

    lines = [
        f"📊 *Velluto Daily Report — {date}*",
        "",
        f"*Sales {pacing_emoji}*",
        f"  Today: {s['orders_today']}/{s['target']} orders ({s['pacing_pct']}%)",
        f"  Revenue: €{s['revenue_eur']:.0f} | AOV: €{s['aov_eur']:.0f}",
        f"  7-day: {orders_7d} orders / €{revenue_7d:.0f}",
        "",
        f"*Meta Ads {roas_emoji}*",
        f"  Spend: €{m['spend_eur']:.0f} | ROAS: {m['roas']:.2f}x",
        f"  CPA: €{m['cpa_eur']:.0f} | CTR: {m['ctr_pct']:.2f}%",
        f"  7-day spend: €{spend_7d:.0f}",
        "",
        f"*SEO*",
        f"  Organic clicks: {seo['organic_clicks']}",
        f"  Avg. position: {seo['avg_position']}",
        "",
        f"*CRO*",
        f"  Sessions: {cro['sessions']}",
        f"  Conv. rate: {cro['conversion_rate_pct']}%",
        f"  Cart abandonment: {cro['cart_abandonment_pct']}%",
        "",
        f"*Email*",
        f"  Revenue: €{email['revenue_eur']:.0f}",
        f"  Open rate: {email['open_rate_pct']}%",
        "",
        f"*AI Cost*",
        f"  Yesterday: ${tokens.get('total_cost_usd', 0):.3f}",
        f"  Cache savings: ${tokens.get('cache_savings_usd', 0):.3f}",
        "",
        f"Monthly target: {settings.monthly_sales_target} orders",
        f"Send `run` to trigger optimization cycle",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    asyncio.run(generate_and_send())
