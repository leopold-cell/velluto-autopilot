import json
import re
from typing import Protocol

from sqlalchemy.orm import Session

from .config import Settings
from .db import utcnow
from .models import LLMSpend


class BudgetExceeded(RuntimeError):
    pass


class LLM(Protocol):
    def complete_json(self, system: str, user: str, *, max_tokens: int = 2000) -> dict | list: ...


def parse_json(text: str) -> dict | list:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    return json.loads(text)


class ClaudeLLM:
    """Anthropic wrapper with a hard daily USD cap persisted in the DB."""

    def __init__(self, session: Session, settings: Settings):
        import anthropic

        self.s, self.cfg = session, settings
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def _spent_today(self) -> float:
        row = self.s.get(LLMSpend, utcnow().date())
        return row.usd if row else 0.0

    def _add_spend(self, usd: float) -> None:
        today = utcnow().date()
        row = self.s.get(LLMSpend, today)
        if row is None:
            self.s.add(LLMSpend(day=today, usd=usd))
        else:
            row.usd += usd
        self.s.commit()

    def complete_json(self, system: str, user: str, *, max_tokens: int = 2000) -> dict | list:
        if self._spent_today() >= self.cfg.daily_llm_budget_usd:
            raise BudgetExceeded(f"daily LLM budget {self.cfg.daily_llm_budget_usd} USD reached")
        resp = self.client.messages.create(
            model=self.cfg.anthropic_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        usage = resp.usage
        self._add_spend(
            usage.input_tokens / 1e6 * self.cfg.llm_input_usd_per_mtok
            + usage.output_tokens / 1e6 * self.cfg.llm_output_usd_per_mtok
        )
        return parse_json(resp.content[0].text)
