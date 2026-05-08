"""Google Search Console API client."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.config import settings

log = structlog.get_logger()

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


class GSCClient:
    def __init__(self):
        if not settings.google_service_account_json:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON not configured")

        credentials = service_account.Credentials.from_service_account_file(
            settings.google_service_account_json, scopes=SCOPES
        )
        self._service = build("searchconsole", "v1", credentials=credentials, cache_discovery=False)
        self.site_url = settings.gsc_site_url

    def _date(self, days_ago: int) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d")

    def _query(self, request: dict) -> dict:
        return (
            self._service.searchanalytics()
            .query(siteUrl=self.site_url, body=request)
            .execute()
        )

    async def get_today_summary(self) -> dict[str, Any]:
        today = self._date(1)
        try:
            data = self._query({
                "startDate": today,
                "endDate": today,
                "dimensions": [],
            })
            rows = data.get("rows", [{}])
            row = rows[0] if rows else {}
            return {
                "clicks": int(row.get("clicks", 0)),
                "impressions": int(row.get("impressions", 0)),
                "avg_position": round(float(row.get("position", 0)), 1),
                "ctr": round(float(row.get("ctr", 0)) * 100, 2),
            }
        except Exception as e:
            log.warning("gsc.today_summary_failed", error=str(e))
            return {"clicks": 0, "impressions": 0, "avg_position": 0.0, "ctr": 0.0}

    async def get_opportunities(self) -> dict[str, Any]:
        """Find keywords ranking 11-30 with high impressions — page 2-3 opportunities."""
        end = self._date(1)
        start = self._date(28)
        try:
            data = self._query({
                "startDate": start,
                "endDate": end,
                "dimensions": ["query"],
                "rowLimit": 500,
            })
            rows = data.get("rows", [])
            opportunities = [
                {
                    "query": r["keys"][0],
                    "position": round(r.get("position", 0), 1),
                    "impressions": r.get("impressions", 0),
                    "clicks": r.get("clicks", 0),
                    "ctr_pct": round(r.get("ctr", 0) * 100, 2),
                }
                for r in rows
                if 10 < r.get("position", 0) <= 30 and r.get("impressions", 0) > 100
            ]
            opportunities.sort(key=lambda x: x["impressions"], reverse=True)
            return {"opportunities": opportunities[:20], "total_found": len(opportunities)}
        except Exception as e:
            log.warning("gsc.opportunities_failed", error=str(e))
            return {"opportunities": [], "error": str(e)}

    async def get_top_pages(self, days: int = 28) -> list[dict]:
        end = self._date(1)
        start = self._date(days)
        try:
            data = self._query({
                "startDate": start,
                "endDate": end,
                "dimensions": ["page"],
                "rowLimit": 20,
            })
            return [
                {
                    "page": r["keys"][0],
                    "clicks": r.get("clicks", 0),
                    "impressions": r.get("impressions", 0),
                    "position": round(r.get("position", 0), 1),
                }
                for r in data.get("rows", [])
            ]
        except Exception as e:
            log.warning("gsc.top_pages_failed", error=str(e))
            return []
