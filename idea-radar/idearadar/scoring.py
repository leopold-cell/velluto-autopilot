"""Idea scoring. All features are normalised to 0..1 by the caller; payers_needed is absolute."""
from dataclasses import dataclass

WEIGHTS = {
    "recurrence": 0.20,      # distinct authors / days the problem shows up
    "affluence": 0.18,       # verified affluence evidence
    "wtp": 0.17,             # existing spend / competitor ad budget / price mentions
    "competition_gap": 0.10,
    "ai_automatable": 0.08,
    "buildable": 0.07,       # shippable in <= 2 weeks
    "reach": 0.12,           # can we reach this audience cheaply (community, keyword, partner)?
    "timing": 0.08,          # "newly possible" (law, model, platform change)
}


@dataclass
class ScoreResult:
    score: float
    breakdown: dict
    penalties: dict


def payers_needed(price_eur: float, target_monthly_profit_eur: float, margin: float = 0.7) -> int:
    if price_eur <= 0:
        return 10**9
    return int(-(-target_monthly_profit_eur // (price_eur * margin)))


def clamp(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def buildable_from_days(days: float) -> float:
    return clamp(1.0 - (days - 3) / 25.0) if days > 3 else 1.0


def score_idea(features: dict, price_eur: float, target_monthly_profit_eur: float, max_payers: int) -> ScoreResult:
    breakdown = {k: clamp(features.get(k, 0.0)) for k in WEIGHTS}
    raw = sum(WEIGHTS[k] * breakdown[k] for k in WEIGHTS) * 100
    penalties: dict = {}
    n = payers_needed(price_eur, target_monthly_profit_eur)
    breakdown["payers_needed"] = n
    if n > max_payers:
        penalties["too_many_payers_needed"] = 15.0
    if breakdown["reach"] < 0.2:
        penalties["no_clear_channel"] = 15.0
    if breakdown["affluence"] < 0.3:
        penalties["weak_affluence_evidence"] = 20.0
    return ScoreResult(max(0.0, round(raw - sum(penalties.values()), 2)), breakdown, penalties)
