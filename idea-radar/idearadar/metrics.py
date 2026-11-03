from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Experiment, Preorder, Visit, WaitlistEntry


def compute_metrics(session: Session, exp: Experiment) -> dict:
    """Live funnel numbers from the tables; spend comes from the manually entered metrics (ads are external)."""
    ext = exp.metrics or {}  # manually entered numbers from external pages/ads (e.g. a landing page hosted elsewhere)
    out = {"spend_eur": float(ext.get("spend_eur", 0.0)), "external": {k: int(ext.get(k, 0)) for k in ("visitors", "signups", "preorders")}, "variants": {}}
    total = {"visitors": 0, "signups": 0, "preorders": 0}
    for v in ("a", "b"):
        visitors = session.scalar(select(func.count()).select_from(Visit).where(Visit.experiment_id == exp.id, Visit.variant == v)) or 0
        signups = session.scalar(select(func.count()).select_from(WaitlistEntry).where(
            WaitlistEntry.experiment_id == exp.id, WaitlistEntry.variant == v, WaitlistEntry.confirmed.is_(True),
            WaitlistEntry.unsubscribed.is_(False))) or 0
        pre = session.scalar(select(func.count()).select_from(Preorder).where(
            Preorder.experiment_id == exp.id, Preorder.variant == v, Preorder.status == "paid")) or 0
        out["variants"][v] = {"visitors": visitors, "signups": signups, "preorders": pre,
                              "conversion": round(signups / visitors, 4) if visitors else 0.0}
        total["visitors"] += visitors
        total["signups"] += signups
        total["preorders"] += pre
    out.update({k: total[k] + out["external"][k] for k in total})
    out["conversion"] = round(out["signups"] / out["visitors"], 4) if out["visitors"] else 0.0
    return out
