"""
Meta-Orchestrator — the overlooking agent.

Runs daily at 05:00. Analyzes the entire multi-agent system and produces:
  1. System health assessment across all modules
  2. New agent recommendations (copywriter, Meta ads library, Google Ads, etc.)
  3. Inter-agent communication optimizations
  4. Quality management improvements & new QA measures
  5. Daily QA scoring for each agent's output

Results are stored as AuditLog entries with agent='meta_orchestrator' and
are surfaced in the dashboard via GET /dashboard → meta_suggestions field.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import anthropic
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.audit import AuditLog
from app.models.kpi import KpiSnapshot

log = structlog.get_logger()

# ── Agent catalogue — known + planned ────────────────────────────────────────

CURRENT_AGENTS = {
    "orchestrator":    "Main cycle orchestrator — hourly KPI analysis, tool dispatch, risk gating",
    "shopify":         "Product, pricing, discount, SEO updates via Shopify Admin API",
    "meta_ads":        "Meta campaign budget management, pause/resume, creative rotation",
    "seo":             "Blog posts, meta tags, Google Search Console monitoring",
    "email_marketing": "Klaviyo flow triggers, campaign scheduling, segment management",
    "competitor":      "Weekly price & product change monitoring across competitors",
    "creative":        "Ad creative copy generation, A/B variant suggestions",
    "quality":         "Output QA checks, brand term validation, content scoring",
    "token_optimizer": "Claude API cost tracking, prompt caching, usage optimization",
    "translator":      "Shopify product + theme translation across 10 EU languages",
}

AGENT_EXPANSION_LIBRARY = {
    "copywriting_agent":         "Dedicated copywriter — product descriptions, ad copy, email subject lines, landing page text. Runs on content change triggers and weekly refresh cycles.",
    "meta_ads_library_agent":    "Monitors Meta Ad Library for competitor creatives, extracts winning hooks/formats/offers, feeds insights to creative agent. Weekly deep scan + daily new ad alerts.",
    "google_ads_agent":          "Google Ads campaign management — search, shopping, Performance Max. Bid strategy, negative keyword management, search term mining.",
    "google_analytics_agent":    "GA4 funnel analysis — drop-off detection, session quality scoring, conversion path optimization. Daily funnel report.",
    "whatsapp_crm_agent":        "WhatsApp broadcast campaigns, abandoned cart recovery flows, post-purchase follow-ups via WhatsApp Business API.",
    "review_agent":              "Proactive review request emails/WhatsApp, Trustpilot/Google review monitoring, response drafting, NPS tracking.",
    "influencer_agent":          "Cycling influencer discovery (Strava, Instagram), outreach templates, partnership tracking, affiliate link management.",
    "pricing_intelligence_agent":"Dynamic pricing based on competitor price changes, inventory levels, and demand signals. Suggest + execute price changes.",
    "inventory_agent":           "Shopify inventory monitoring, low-stock alerts, reorder point calculations, supplier lead time tracking.",
    "ab_test_agent":             "Systematic A/B tests on product pages, checkout flow, email subjects. Tracks statistical significance, auto-promotes winners.",
    "loyalty_agent":             "Customer lifetime value scoring, VIP segment identification, loyalty reward trigger management.",
    "qa_scoring_agent":          "Dedicated QA department head — scores every agent output (0-100), flags regressions, maintains quality benchmark database.",
}

SYSTEM_PROMPT = f"""You are the Meta-Orchestrator for Velluto Autopilot — the highest-level strategic AI that oversees and continuously improves the entire multi-agent growth system.

Current multi-agent system:
{json.dumps(CURRENT_AGENTS, indent=2)}

Planned/available agent expansions:
{json.dumps(AGENT_EXPANSION_LIBRARY, indent=2)}

Your daily analysis must produce a structured JSON report covering:

1. **system_health** — Overall system score (0-100) + per-agent scores + bottlenecks
2. **qa_improvements** — Specific new QA measures to introduce TODAY. Be concrete.
3. **agent_recommendations** — Which new agents to prioritize implementing next (ranked), with justification based on current KPI gaps
4. **communication_optimizations** — How agents should share data differently to increase output quality
5. **quality_scores** — Score each existing agent's output quality this week (0-100) with specific improvement actions
6. **weekly_priority** — The single most important system improvement for this week

Be specific, data-driven, and actionable. Reference actual KPI numbers.
Return ONLY valid JSON — no markdown fences."""


async def _gather_analysis_context(db: AsyncSession) -> str:
    now = datetime.now(timezone.utc)
    today = now.date()

    # 14-day KPI snapshots
    kpi_rows = await db.execute(
        select(KpiSnapshot)
        .where(KpiSnapshot.snapshot_date >= today - timedelta(days=14))
        .order_by(KpiSnapshot.snapshot_date.asc())
    )
    snaps = kpi_rows.scalars().all()

    # Agent activity last 7 days — count + distinct actions per agent
    agent_stats_rows = await db.execute(
        select(
            AuditLog.agent,
            func.count(AuditLog.id).label("total"),
            func.sum(
                func.cast(AuditLog.status == "success", type_=func.Integer if hasattr(func, "Integer") else None)
            ).label("successes"),
        )
        .where(AuditLog.created_at >= now - timedelta(days=7))
        .group_by(AuditLog.agent)
    )
    agent_stats = agent_stats_rows.all()

    # Recent audit logs
    recent_rows = await db.execute(
        select(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(30)
    )
    recent_logs = recent_rows.scalars().all()

    lines = [f"Analysis date: {today}\n"]

    lines.append("## 14-Day KPI Trend")
    for s in snaps:
        lines.append(f"  {s.snapshot_date}: rev=€{s.revenue_eur or 0:.0f}, "
                     f"orders={s.orders_count or 0}, spend=€{s.ad_spend_eur or 0:.0f}, "
                     f"roas={s.ad_roas or 0:.2f}x, sessions={s.shopify_sessions or 0}, "
                     f"cvr={s.conversion_rate or 0:.2f}%")

    lines.append("\n## Agent Activity (last 7 days)")
    for row in agent_stats:
        lines.append(f"  {row.agent or 'unknown'}: {row.total} actions")

    lines.append("\n## Recent Agent Actions (last 30)")
    for entry in recent_logs:
        ts = entry.created_at.strftime("%m-%d %H:%M") if entry.created_at else "?"
        result_preview = str(entry.result or "")[:100]
        lines.append(f"  [{ts}] {entry.agent}: {entry.action} → {result_preview}")

    return "\n".join(lines)


async def run_meta_orchestration() -> dict[str, Any]:
    log.info("meta_orchestrator.start")

    async with AsyncSessionLocal() as db:
        context = await _gather_analysis_context(db)

        claude = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await claude.messages.create(
            model=settings.anthropic_model,
            max_tokens=4096,
            system=[{
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{
                "role": "user",
                "content": f"Analyze the following system data and return your structured improvement report:\n\n{context}",
            }],
        )

        raw = response.content[0].text.strip()
        # Strip markdown fences if present
        import re
        raw = re.sub(r"^```json\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        try:
            report: dict = json.loads(raw)
        except json.JSONDecodeError as e:
            log.error("meta_orchestrator.parse_failed", error=str(e))
            report = {"error": "Parse failed", "raw": raw[:500]}

        # Store result in audit log
        audit = AuditLog(
            agent="meta_orchestrator",
            action="daily_system_analysis",
            status="success",
            result=report,
            created_at=datetime.now(timezone.utc),
        )
        db.add(audit)
        await db.commit()

        log.info("meta_orchestrator.done",
                 health=report.get("system_health", {}).get("score"),
                 qa_improvements=len(report.get("qa_improvements", [])),
                 agent_recs=len(report.get("agent_recommendations", [])))

        return report


async def get_latest_meta_report(db: AsyncSession) -> dict | None:
    """Fetch the most recent meta-orchestration report for the dashboard."""
    row = await db.execute(
        select(AuditLog)
        .where(AuditLog.agent == "meta_orchestrator")
        .where(AuditLog.action == "daily_system_analysis")
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    entry = row.scalar_one_or_none()
    if not entry:
        return None
    return {
        "generated_at": entry.created_at.isoformat() if entry.created_at else None,
        "report": entry.result,
    }
