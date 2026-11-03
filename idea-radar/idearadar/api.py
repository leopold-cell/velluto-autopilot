import hmac
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from .config import Settings, get_settings
from .db import make_session_factory
from .experiment import day_index, decide, evaluate
from .guardrails import Guardrails
from .models import Experiment, Idea, OutreachMessage
from .outreach import handle_reply, queue_outreach


class DecisionIn(BaseModel):
    decision: Literal["approve", "reject"]
    price_eur: float | None = Field(default=None, gt=0)
    test_days: int | None = Field(default=None, ge=3, le=60)
    budget_eur: float = Field(default=100.0, ge=0, le=2000)


class MetricsIn(BaseModel):
    visitors: int = Field(ge=0)
    signups: int = Field(ge=0)
    preorders: int = Field(default=0, ge=0)
    spend_eur: float = Field(default=0.0, ge=0)


class OutreachIn(BaseModel):
    channel: str
    handle: str
    body: str
    opted_in: bool = False


class ReplyIn(BaseModel):
    channel: str
    handle: str
    text: str


class KillIn(BaseModel):
    enabled: bool


def create_app(settings: Settings | None = None, session_factory=None) -> FastAPI:
    cfg = settings or get_settings()
    factory = session_factory or make_session_factory(cfg.database_url)
    app = FastAPI(title="Idea Radar")

    def auth(x_api_key: str = Header(default="")):
        if not cfg.admin_api_key:
            raise HTTPException(503, "ADMIN_API_KEY is not configured")
        if not hmac.compare_digest(x_api_key, cfg.admin_api_key):
            raise HTTPException(401, "invalid api key")

    def db():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/ideas", dependencies=[Depends(auth)])
    def ideas(status: str = "pending", s=Depends(db)):
        rows = s.scalars(select(Idea).where(Idea.status == status).order_by(Idea.score.desc())).all()
        return [{"id": i.id, "day": str(i.day), "title": i.title, "score": i.score, "price_eur": i.price_eur,
                 "breakdown": i.breakdown, "card": i.card, "status": i.status} for i in rows]

    @app.post("/ideas/{idea_id}/decision", dependencies=[Depends(auth)])
    def decision(idea_id: int, body: DecisionIn, s=Depends(db)):
        try:
            res = decide(s, cfg, idea_id, body.decision, price_eur=body.price_eur, test_days=body.test_days, budget_eur=body.budget_eur)
        except LookupError:
            raise HTTPException(404, "idea not found")
        except ValueError as e:
            raise HTTPException(409, str(e))
        if isinstance(res, Experiment):
            return {"status": "approved", "experiment_id": res.id, "test_days": res.test_days}
        return {"status": "rejected"}

    @app.get("/experiments", dependencies=[Depends(auth)])
    def experiments(s=Depends(db)):
        return [{"id": e.id, "idea_id": e.idea_id, "status": e.status, "test_days": e.test_days, "metrics": e.metrics}
                for e in s.scalars(select(Experiment).order_by(Experiment.id.desc()))]

    @app.post("/experiments/{exp_id}/metrics", dependencies=[Depends(auth)])
    def metrics(exp_id: int, body: MetricsIn, s=Depends(db)):
        exp = s.get(Experiment, exp_id)
        if exp is None:
            raise HTTPException(404, "experiment not found")
        exp.metrics = body.model_dump()
        s.commit()
        return exp.metrics

    @app.get("/experiments/{exp_id}/evaluation", dependencies=[Depends(auth)])
    def evaluation(exp_id: int, s=Depends(db)):
        exp = s.get(Experiment, exp_id)
        if exp is None:
            raise HTTPException(404, "experiment not found")
        return evaluate(exp.metrics, day_index(exp), exp.test_days, exp.budget_eur, cfg)

    @app.post("/experiments/{exp_id}/outreach", dependencies=[Depends(auth)])
    def outreach(exp_id: int, body: OutreachIn, s=Depends(db)):
        if s.get(Experiment, exp_id) is None:
            raise HTTPException(404, "experiment not found")
        m = queue_outreach(s, cfg, exp_id, body.channel, body.handle, body.body, opted_in=body.opted_in)
        return {"id": m.id, "status": m.status, "reason": m.reason}

    @app.get("/outreach", dependencies=[Depends(auth)])
    def outreach_list(status: str = "assist", s=Depends(db)):
        rows = s.scalars(select(OutreachMessage).where(OutreachMessage.status == status).order_by(OutreachMessage.id))
        return [{"id": m.id, "channel": m.channel, "handle": m.target_handle, "body": m.body, "reason": m.reason} for m in rows]

    @app.post("/outreach/reply", dependencies=[Depends(auth)])
    def reply(body: ReplyIn, s=Depends(db)):
        return {"suppressed": handle_reply(s, cfg, body.channel, body.handle, body.text)}

    @app.post("/killswitch", dependencies=[Depends(auth)])
    def killswitch(body: KillIn, s=Depends(db)):
        Guardrails(s, cfg).set_kill_switch(body.enabled)
        return {"kill_switch": body.enabled}

    return app
