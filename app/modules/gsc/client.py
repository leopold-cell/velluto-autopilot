"""Google Search Console API client."""

from __future__ import annotations

import asyncio
import json
import os
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
        credentials = self._load_credentials()
        self._service = build("searchconsole", "v1", credentials=credentials, cache_discovery=False)
        self.site_url = settings.gsc_site_url

    @staticmethod
    def _load_credentials() -> service_account.Credentials:
        """Build service-account credentials from either inline JSON or a file path.

        GOOGLE_SERVICE_ACCOUNT_JSON may hold the JSON key contents directly
        (the usual pattern when the secret is injected as an env var on hosts
        like Render/Railway/Fly/Cloud Run) or a path to a mounted key file.
        Supporting only the file path silently broke GSC whenever the secret
        was supplied inline.
        """
        raw = settings.google_service_account_json
        if not raw:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON not configured")

        stripped = raw.strip()
        if stripped.startswith("{"):
            try:
                info = json.loads(stripped)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON: {e}") from e
            return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)

        if not os.path.isfile(stripped):
            raise RuntimeError(
                f"GOOGLE_SERVICE_ACCOUNT_JSON points to a missing file: {stripped}"
            )
        return service_account.Credentials.from_service_account_file(stripped, scopes=SCOPES)

    def _date(self, days_ago: int) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d")

    async def _query(self, request: dict) -> dict:
        # googleapiclient is synchronous; run the blocking HTTP call in a worker
        # thread so it doesn't stall the asyncio event loop (and every other
        # in-flight request) while waiting on the Search Console API.
        def _execute() -> dict:
            return (
                self._service.searchanalytics()
                .query(siteUrl=self.site_url, body=request)
                .execute()
            )

        return await asyncio.to_thread(_execute)

    async def get_today_summary(self) -> dict[str, Any]:
        today = self._date(1)
        try:
            data = await self._query({
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
            data = await self._query({
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
            data = await self._query({
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
