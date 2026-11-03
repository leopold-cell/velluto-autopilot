from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class RawItemData:
    source: str
    url: str
    author_handle: str
    text: str
    published_at: datetime | None = None


class Collector(Protocol):
    name: str

    def fetch(self) -> list[RawItemData]: ...
