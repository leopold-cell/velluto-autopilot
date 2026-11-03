"""LLM extraction of recurring problems + affluence/WTP evidence, with hallucination guards."""
import re

from .llm import LLM

SYSTEM = """You extract concrete, recurring problems from public posts written by people who may be affluent
(business owners, executives, investors, property/boat/watch owners, family offices, expats with complex finances).
Return ONLY JSON: {"problems":[{"item_id":int,"summary":"one sentence problem","persona":"who has it",
"affluence":0..1,"affluence_quote":"exact substring copied from the post that signals wealth/seniority, or empty",
"wtp":0..1,"wtp_quote":"exact substring showing existing spend/price/hired help, or empty"}]}.
Rules: skip posts without a concrete problem. Never invent quotes: quotes must be copied verbatim from the post.
Affluence without a verbatim quote must be 0. No sensitive attributes (health, religion, politics) in summaries."""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def verify_quote(quote: str, text: str) -> bool:
    return bool(quote) and len(quote) >= 8 and _norm(quote) in _norm(text)


def extract_problems(llm: LLM, items: list[tuple[int, str]]) -> list[dict]:
    payload = "\n\n".join(f"[item_id={i}]\n{t[:1500]}" for i, t in items)
    data = llm.complete_json(SYSTEM, payload, max_tokens=3000)
    rows = data.get("problems", []) if isinstance(data, dict) else []
    texts = dict(items)
    out = []
    for r in rows:
        try:
            item_id = int(r["item_id"])
            summary = str(r["summary"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if item_id not in texts or not summary:
            continue
        text = texts[item_id]
        aff, wtp = float(r.get("affluence", 0) or 0), float(r.get("wtp", 0) or 0)
        aq, wq = str(r.get("affluence_quote", "") or ""), str(r.get("wtp_quote", "") or "")
        if not verify_quote(aq, text):
            aff, aq = 0.0, ""
        if not verify_quote(wq, text):
            wtp, wq = 0.0, ""
        out.append({
            "item_id": item_id, "summary": summary, "persona": str(r.get("persona", ""))[:250],
            "affluence": max(0.0, min(1.0, aff)), "affluence_evidence": aq,
            "wtp": max(0.0, min(1.0, wtp)), "wtp_evidence": wq,
        })
    return out
