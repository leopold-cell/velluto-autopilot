"""
Microsoft Clarity Insights Agent.

Fetches behavioral analytics from MS Clarity (heatmaps, rage clicks,
scroll depth, funnel drop-off, dead clicks) and uses Claude to produce:
  - Top conversion blockers with supporting data
  - Page-level UX issues
  - Prioritized CRO recommendations

Runs every 6 hours. Results stored in audit_logs and surfaced on dashboard.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import anthropic
import httpx
import structlog

from app.config import settings

log = structlog.get_logger()

BASE = "https://www.clarity.ms/api/v1"
PROJECT_ID = settings.clarity_project_id
TOKEN = settings.clarity_api_token


# ── Data fetching ─────────────────────────────────────────────────────────────

async def _get(client: httpx.AsyncClient, path: str, params: dict = {}) -> dict | list | None:
    if not TOKEN or not PROJECT_ID:
        return None
    try:
        r = await client.get(
            f"{BASE}/{path}",
            headers={"Authorization": f"Bearer {TOKEN}"},
            params=params,
            timeout=20,
        )
        if r.status_code in (401, 403):
            log.warning("clarity.auth_failed", path=path, status=r.status_code)
            return None
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning("clarity.fetch_failed", path=path, error=str(e))
        return None


async def fetch_clarity_data() -> dict[str, Any]:
    """Gather all available Clarity data for the last 7 days."""
    today = datetime.now(timezone.utc)
    start = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    end = today.strftime("%Y-%m-%d")

    async with httpx.AsyncClient(timeout=30) as client:
        # Run all fetches — each is fault-tolerant
        metrics_today = await _get(client, f"projects/{PROJECT_ID}/metrics", {
            "startDate": end, "endDate": end,
        })
        metrics_week = await _get(client, f"projects/{PROJECT_ID}/metrics", {
            "startDate": start, "endDate": end,
        })
        pages = await _get(client, f"projects/{PROJECT_ID}/pages", {
            "startDate": start, "endDate": end, "limit": 15,
        })
        rage_clicks = await _get(client, f"projects/{PROJECT_ID}/pages", {
            "startDate": start, "endDate": end,
            "sortBy": "rageClicks", "limit": 10,
        })
        dead_clicks = await _get(client, f"projects/{PROJECT_ID}/pages", {
            "startDate": start, "endDate": end,
            "sortBy": "deadClicks", "limit": 10,
        })
        scroll_depth = await _get(client, f"projects/{PROJECT_ID}/pages", {
            "startDate": start, "endDate": end,
            "sortBy": "scrollDepth", "limit": 10,
        })
        funnel = await _get(client, f"projects/{PROJECT_ID}/funnels")
        recordings_meta = await _get(client, f"projects/{PROJECT_ID}/recordings/count", {
            "startDate": start, "endDate": end,
        })
        # Clarity AI insights endpoint (newer Clarity feature)
        ai_insights = await _get(client, f"projects/{PROJECT_ID}/insights", {
            "startDate": start, "endDate": end,
        })

    return {
        "period": {"start": start, "end": end},
        "metrics_today": metrics_today,
        "metrics_week": metrics_week,
        "top_pages": pages,
        "rage_click_pages": rage_clicks,
        "dead_click_pages": dead_clicks,
        "scroll_depth_pages": scroll_depth,
        "funnel": funnel,
        "recordings_meta": recordings_meta,
        "ai_insights": ai_insights,
    }


def _summarise_raw(data: dict) -> str:
    """Convert raw Clarity API response into a compact text block for Claude."""
    lines = [f"## Microsoft Clarity Data — {data['period']['start']} to {data['period']['end']}\n"]

    def metric_block(label: str, d: dict | None):
        if not d:
            return
        lines.append(f"\n### {label}")
        for k, v in d.items():
            if isinstance(v, (int, float, str)):
                lines.append(f"  {k}: {v}")

    metric_block("Today's Metrics", data.get("metrics_today"))
    metric_block("7-Day Metrics", data.get("metrics_week"))

    def page_block(label: str, pages_data):
        if not pages_data:
            return
        raw = pages_data if isinstance(pages_data, list) else pages_data.get("pages", [])
        if not raw:
            return
        lines.append(f"\n### {label}")
        for p in raw[:8]:
            url = p.get("url", p.get("path", "?"))
            stats = {k: v for k, v in p.items()
                     if k not in ("url", "path") and isinstance(v, (int, float))}
            lines.append(f"  {url}: " + ", ".join(f"{k}={v}" for k, v in list(stats.items())[:6]))

    page_block("Top Pages", data.get("top_pages"))
    page_block("Rage Click Pages (frustration signals)", data.get("rage_click_pages"))
    page_block("Dead Click Pages (broken element signals)", data.get("dead_click_pages"))
    page_block("Scroll Depth Pages", data.get("scroll_depth_pages"))

    if data.get("funnel"):
        lines.append("\n### Funnel Analysis")
        funnel = data["funnel"]
        if isinstance(funnel, dict):
            for k, v in funnel.items():
                lines.append(f"  {k}: {v}")
        elif isinstance(funnel, list):
            for step in funnel:
                lines.append(f"  {step}")

    if data.get("recordings_meta"):
        lines.append(f"\n### Session Recordings: {data['recordings_meta']}")

    if data.get("ai_insights"):
        lines.append("\n### Clarity AI Insights (raw)")
        ai = data["ai_insights"]
        if isinstance(ai, list):
            for item in ai[:5]:
                lines.append(f"  - {item}")
        elif isinstance(ai, dict):
            for k, v in list(ai.items())[:8]:
                lines.append(f"  {k}: {v}")

    return "\n".join(lines)


# ── Analysis ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior CRO (Conversion Rate Optimization) analyst for Velluto, a premium Dutch road cycling eyewear brand.

Store: velluto-shop.com
Key products: StradaPro glasses (€149), VellutoVisione lens (€39.90), VellutoPuro lens (€19.90), accessories
Current conversion rate benchmark: ~2% for premium sporting goods DTC

You receive raw Microsoft Clarity behavioral analytics. Analyze it to identify:
1. The most significant conversion blockers (what stops users from buying)
2. Pages with UX friction (rage clicks = frustrated users clicking repeatedly, dead clicks = broken/confusing elements, low scroll depth = content not seen)
3. Funnel drop-off patterns
4. Specific, actionable fixes prioritized by impact

Return ONLY valid JSON — no markdown fences. Structure:

{
  "summary": "2-3 sentence executive summary of the biggest behavioral finding",
  "conversion_blockers": [
    {"issue": "...", "evidence": "...", "impact": "high|medium|low", "fix": "..."}
  ],
  "page_insights": [
    {"page": "...", "finding": "...", "metric": "...", "recommendation": "..."}
  ],
  "quick_wins": ["actionable fix in one sentence", ...],
  "top_metric": {"label": "...", "value": "...", "trend": "good|bad|neutral"},
  "health_score": 0-100
}

Be specific. Reference actual numbers from the data. If data is missing/empty, say so honestly."""


async def analyse_clarity_data(raw_data: dict) -> dict:
    """Send Clarity data to Claude for behavioral analysis."""
    summary_text = _summarise_raw(raw_data)

    has_data = any([
        raw_data.get("metrics_today"),
        raw_data.get("metrics_week"),
        raw_data.get("rage_click_pages"),
        raw_data.get("top_pages"),
    ])

    if not has_data:
        return {
            "summary": "No Clarity API data available. Check that CLARITY_PROJECT_ID and CLARITY_API_TOKEN are set in .env and that the API token has read access.",
            "conversion_blockers": [],
            "page_insights": [],
            "quick_wins": ["Verify Clarity API credentials in .env", "Ensure Clarity project ID is correct"],
            "top_metric": {"label": "Status", "value": "No data", "trend": "neutral"},
            "health_score": 0,
            "no_data": True,
        }

    claude = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await claude.messages.create(
        model=settings.anthropic_model,
        max_tokens=2048,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": f"Analyze this Clarity data:\n\n{summary_text}"}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        log.error("clarity.agent.parse_failed", error=str(e))
        return {"summary": "Parse error", "raw_response": raw[:300]}


# ── Entry point ───────────────────────────────────────────────────────────────

async def run_clarity_analysis() -> dict[str, Any]:
    """Main entry point called by the scheduler."""
    log.info("clarity.agent.start")
    raw = await fetch_clarity_data()
    insights = await analyse_clarity_data(raw)

    from app.database import AsyncSessionLocal
    from app.models.audit import AuditLog

    async with AsyncSessionLocal() as db:
        audit = AuditLog(
            agent="clarity_agent",
            action="behavioral_analysis",
            status="success",
            result={
                "insights": insights,
                "raw_summary": {
                    "has_today_metrics": bool(raw.get("metrics_today")),
                    "has_week_metrics": bool(raw.get("metrics_week")),
                    "has_page_data": bool(raw.get("top_pages")),
                    "has_rage_clicks": bool(raw.get("rage_click_pages")),
                    "has_funnel": bool(raw.get("funnel")),
                },
            },
            created_at=datetime.now(timezone.utc),
        )
        db.add(audit)
        await db.commit()

    log.info("clarity.agent.done",
             health_score=insights.get("health_score"),
             blockers=len(insights.get("conversion_blockers", [])))
    return insights


async def get_latest_clarity_insights(db) -> dict | None:
    """Fetch the most recent Clarity analysis for the dashboard."""
    from sqlalchemy import select
    from app.models.audit import AuditLog

    row = await db.execute(
        select(AuditLog)
        .where(AuditLog.agent == "clarity_agent")
        .where(AuditLog.action == "behavioral_analysis")
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    entry = row.scalar_one_or_none()
    if not entry:
        return None
    return {
        "generated_at": entry.created_at.isoformat() if entry.created_at else None,
        "insights": (entry.result or {}).get("insights", {}),
    }
