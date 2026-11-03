"""Daily pipeline: collect -> extract -> cluster -> idea cards -> score -> pending ideas."""
import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .cluster import cluster, jaccard, tokens
from .collectors.base import Collector
from .config import Settings
from .db import utcnow
from .extract import extract_problems
from .llm import LLM, BudgetExceeded
from .models import Idea, Problem, RawItem
from .scoring import buildable_from_days, clamp, score_idea

log = logging.getLogger("idearadar.pipeline")

CARD_SYSTEM = """You turn a cluster of recurring problems of affluent people into ONE lean product idea.
Return ONLY JSON with keys: title, one_liner, offering ("saas"|"ai_service"), price_eur (monthly, a single price),
existing_solutions (list of {name, price}), competition_gap 0..1, ai_automatable 0..1, build_days (number),
reach 0..1 (can we reach these people cheaply via a findable community, keyword niche or partners?),
reach_channels (list), timing 0..1 (is this newly possible because of a law, model or platform change? explain in timing_note),
timing_note, hooks (exactly 5 short hook texts that describe the concept honestly as a coming product, no fake numbers or testimonials),
landing_copy {headline, subline, bullets}, pilot_offer {you_get (a No-Brainer for the first pilot customers, e.g. months free without payment data, concrete result they get), we_ask (small commitment in return: feedback calls, permission for an anonymised case study), risk_reversal (why saying yes costs nothing)}, risks (list), kill_criteria (string).
Be sceptical: if there is no clear buyer who already spends money, say so in risks and score low."""


def collect(session: Session, collectors: list[Collector]) -> int:
    new = 0
    for c in collectors:
        try:
            items = c.fetch()
        except Exception as e:  # one failing source must not stop the run
            log.warning("collector %s failed: %s", getattr(c, "name", c), e)
            continue
        for it in items:
            if session.scalar(select(RawItem.id).where(RawItem.url == it.url)):
                continue
            session.add(RawItem(source=it.source, url=it.url, author_handle=it.author_handle, text=it.text, published_at=it.published_at))
            new += 1
        session.commit()
    return new


def extract_new(session: Session, llm: LLM, batch: int = 15) -> int:
    pending = session.scalars(select(RawItem).where(RawItem.processed.is_(False)).order_by(RawItem.id)).all()
    made = 0
    for i in range(0, len(pending), batch):
        chunk = pending[i : i + batch]
        try:
            rows = extract_problems(llm, [(r.id, r.text) for r in chunk])
        except BudgetExceeded:
            raise
        except Exception as e:
            log.warning("extraction failed: %s", e)
            continue
        for r in rows:
            session.add(Problem(raw_item_id=r["item_id"], summary=r["summary"], persona=r["persona"], affluence=r["affluence"],
                                affluence_evidence=r["affluence_evidence"], wtp=r["wtp"], wtp_evidence=r["wtp_evidence"]))
            made += 1
        for r in chunk:
            r.processed = True
        session.commit()
    return made


def _cluster_key(summaries: list[str]) -> str:
    counts: dict[str, int] = {}
    for s in summaries:
        for t in tokens(s):
            counts[t] = counts.get(t, 0) + 1
    return " ".join(sorted(sorted(counts, key=lambda t: (-counts[t], t))[:6]))


def build_candidates(session: Session, window_days: int = 21) -> list[dict]:
    since = utcnow() - timedelta(days=window_days)
    probs = session.scalars(select(Problem).where(Problem.created_at >= since)).all()
    by_id = {p.id: p for p in probs}
    raw = {r.id: r for r in session.scalars(select(RawItem).where(RawItem.id.in_([p.raw_item_id for p in probs]))).all()} if probs else {}
    out = []
    for ids in cluster([(p.id, p.summary) for p in probs]):
        ps = [by_id[i] for i in ids]
        authors = {raw[p.raw_item_id].author_handle for p in ps if p.raw_item_id in raw and raw[p.raw_item_id].author_handle}
        if len(authors) < 2:  # recurrence needs at least two distinct people
            continue
        out.append({
            "problems": ps, "authors": len(authors), "key": _cluster_key([p.summary for p in ps]),
            "affluence": sum(p.affluence for p in ps) / len(ps), "wtp": max(p.wtp for p in ps),
            "urls": [raw[p.raw_item_id].url for p in ps if p.raw_item_id in raw][:5],
        })
    out.sort(key=lambda c: (c["authors"] * (0.3 + c["affluence"])), reverse=True)
    return out


def _is_duplicate(session: Session, key: str, days: int = 30) -> bool:
    since = utcnow() - timedelta(days=days)
    for (k,) in session.execute(select(Idea.cluster_key).where(Idea.created_at >= since)).all():
        if jaccard(set(k.split()), set(key.split())) >= 0.5:
            return True
    return False


def make_ideas(session: Session, llm: LLM, cfg: Settings, today: date | None = None) -> list[Idea]:
    today = today or utcnow().date()
    ideas: list[Idea] = []
    for cand in build_candidates(session)[: cfg.ideas_per_day * 4]:
        if _is_duplicate(session, cand["key"]):
            continue
        brief = "\n".join(f"- {p.summary} (persona: {p.persona}; affluence evidence: {p.affluence_evidence!r}; spend evidence: {p.wtp_evidence!r})"
                          for p in cand["problems"][:12])
        try:
            card = llm.complete_json(CARD_SYSTEM, f"Problem cluster ({cand['authors']} distinct authors):\n{brief}", max_tokens=2000)
        except BudgetExceeded:
            break
        except Exception as e:
            log.warning("card generation failed: %s", e)
            continue
        if not isinstance(card, dict) or not card.get("title"):
            continue
        price = float(card.get("price_eur") or 0)
        features = {
            "recurrence": clamp(cand["authors"] / 6), "affluence": cand["affluence"], "wtp": cand["wtp"],
            "competition_gap": card.get("competition_gap", 0), "ai_automatable": card.get("ai_automatable", 0),
            "buildable": buildable_from_days(float(card.get("build_days") or 14)),
            "reach": card.get("reach", 0), "timing": card.get("timing", 0),
        }
        res = score_idea(features, price, cfg.target_monthly_profit_eur, cfg.max_payers_needed)
        card["evidence_urls"] = cand["urls"]
        card["penalties"] = res.penalties
        ideas.append(Idea(day=today, cluster_key=cand["key"], title=str(card["title"])[:250], score=res.score,
                          breakdown=res.breakdown, card=card, price_eur=price))
    ideas.sort(key=lambda i: i.score, reverse=True)
    top = ideas[: cfg.ideas_per_day]
    session.add_all(top)
    session.commit()
    return top


def run_daily(session: Session, collectors: list[Collector], llm: LLM, cfg: Settings) -> list[Idea]:
    n = collect(session, collectors)
    log.info("collected %d new items", n)
    try:
        extract_new(session, llm)
        return make_ideas(session, llm, cfg)
    except BudgetExceeded as e:
        log.warning("stopped: %s", e)
        return []
