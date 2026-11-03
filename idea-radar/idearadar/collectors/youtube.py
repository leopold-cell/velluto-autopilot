"""YouTube Data API v3: search (100 quota units) + top-level comments (~1 unit/page).
Only public comments via the official API. Daily quota is 10,000 units, so searches are capped."""
from datetime import datetime

import httpx

from .base import RawItemData

BASE = "https://www.googleapis.com/youtube/v3"
DEFAULT_QUERIES = ["family office problems", "managing multiple properties owner", "business owner succession tax", "expat tax residency mistakes"]


def parse_comments(video_id: str, payload: dict) -> list[RawItemData]:
    items = []
    for t in payload.get("items", []):
        top = t["snippet"]["topLevelComment"]["snippet"]
        text = top.get("textOriginal") or top.get("textDisplay") or ""
        if len(text) < 40:
            continue
        cid = t["snippet"]["topLevelComment"]["id"]
        published = top.get("publishedAt")
        items.append(RawItemData(
            source="youtube",
            url=f"https://www.youtube.com/watch?v={video_id}&lc={cid}",
            author_handle=top.get("authorDisplayName", ""),
            text=text,
            published_at=datetime.fromisoformat(published.replace("Z", "+00:00")).replace(tzinfo=None) if published else None,
        ))
    return items


class YouTubeCollector:
    name = "youtube"

    def __init__(self, api_key: str, queries: list[str] | None = None, max_searches: int = 20,
                 videos_per_query: int = 3, client: httpx.Client | None = None):
        self.key, self.queries = api_key, queries or DEFAULT_QUERIES
        self.max_searches, self.videos_per_query = max_searches, videos_per_query
        self.client = client or httpx.Client(timeout=20)

    def fetch(self) -> list[RawItemData]:
        if not self.key:
            return []
        out: list[RawItemData] = []
        for q in self.queries[: self.max_searches]:
            s = self.client.get(f"{BASE}/search", params={"part": "id", "q": q, "type": "video", "order": "date",
                                                          "maxResults": self.videos_per_query, "key": self.key})
            s.raise_for_status()
            for it in s.json().get("items", []):
                vid = it["id"]["videoId"]
                c = self.client.get(f"{BASE}/commentThreads", params={"part": "snippet", "videoId": vid, "maxResults": 50,
                                                                      "order": "relevance", "textFormat": "plainText", "key": self.key})
                if c.status_code == 403:  # comments disabled / quota
                    continue
                c.raise_for_status()
                out.extend(parse_comments(vid, c.json()))
        return out
