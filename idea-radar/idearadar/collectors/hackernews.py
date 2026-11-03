"""Hacker News via the free Algolia API. Public data, no auth."""
from datetime import datetime, timezone

import httpx

from .base import RawItemData

API = "https://hn.algolia.com/api/v1/search_by_date"
DEFAULT_QUERIES = [
    "I pay for", "wish there was a tool", "is there a service for", "family office software",
    "managing my properties", "tax residency", "executive assistant AI", "succession planning",
]


def parse_hits(payload: dict) -> list[RawItemData]:
    items = []
    for h in payload.get("hits", []):
        text = h.get("comment_text") or h.get("story_text") or h.get("title") or ""
        if len(text) < 40:
            continue
        oid = h.get("objectID")
        ts = h.get("created_at_i")
        items.append(RawItemData(
            source="hackernews",
            url=f"https://news.ycombinator.com/item?id={oid}",
            author_handle=h.get("author") or "",
            text=text,
            published_at=datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None) if ts else None,
        ))
    return items


class HackerNewsCollector:
    name = "hackernews"

    def __init__(self, queries: list[str] | None = None, per_query: int = 20, client: httpx.Client | None = None):
        self.queries = queries or DEFAULT_QUERIES
        self.per_query = per_query
        self.client = client or httpx.Client(timeout=20, headers={"User-Agent": "idea-radar/0.1"})

    def fetch(self) -> list[RawItemData]:
        out: list[RawItemData] = []
        for q in self.queries:
            r = self.client.get(API, params={"query": q, "tags": "(comment,story)", "hitsPerPage": self.per_query})
            r.raise_for_status()
            out.extend(parse_hits(r.json()))
        return out
