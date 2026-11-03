from sqlalchemy.orm import Session

from .config import Settings
from .db import utcnow
from .models import Experiment, Idea


def decide(session: Session, cfg: Settings, idea_id: int, decision: str, *, price_eur: float | None = None,
           test_days: int | None = None, budget_eur: float = 100.0) -> Experiment | Idea:
    idea = session.get(Idea, idea_id)
    if idea is None:
        raise LookupError("idea not found")
    if idea.status != "pending":
        raise ValueError(f"idea is already {idea.status}")
    idea.decided_at = utcnow()
    if decision == "reject":
        idea.status = "rejected"
        session.commit()
        return idea
    if decision != "approve":
        raise ValueError("decision must be approve or reject")
    idea.status = "approved"
    if price_eur:
        idea.price_eur = price_eur
    exp = Experiment(idea_id=idea.id, test_days=test_days or cfg.default_test_days, budget_eur=budget_eur,
                     metrics={"visitors": 0, "signups": 0, "preorders": 0, "spend_eur": 0.0})
    session.add(exp)
    session.commit()
    return exp


def evaluate(metrics: dict, day_index: int, test_days: int, budget_eur: float, cfg: Settings) -> dict:
    """Go/kill recommendation. The human decides; this only recommends."""
    visitors, signups = metrics.get("visitors", 0), metrics.get("signups", 0)
    preorders, spend = metrics.get("preorders", 0), metrics.get("spend_eur", 0.0)
    conv = signups / visitors if visitors else 0.0
    base = {"conversion": round(conv, 4), "day": day_index}
    if signups >= cfg.go_signups or preorders >= cfg.go_preorders:
        return {**base, "recommendation": "GO", "reason": f"{signups} signups / {preorders} pre-orders reached the target"}
    if day_index >= cfg.explore_days:
        if visitors < 100 and spend >= budget_eur * 0.5:
            return {**base, "recommendation": "KILL", "reason": "could not reach 100 visitors with half the budget: distribution does not work"}
        if visitors >= 100 and conv < 0.015 and preorders == 0:
            return {**base, "recommendation": "KILL", "reason": "100+ visitors but conversion under 1.5% and no pre-order"}
    if day_index >= test_days:
        if conv >= 0.03:
            return {**base, "recommendation": "EXTEND", "reason": "conversion above 3% but targets not reached"}
        return {**base, "recommendation": "KILL", "reason": "test period over without reaching the target"}
    return {**base, "recommendation": "CONTINUE", "reason": "test running"}


def day_index(exp: Experiment) -> int:
    return (utcnow() - exp.starts_at).days
