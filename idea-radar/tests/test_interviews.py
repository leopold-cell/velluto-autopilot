from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from idearadar.api import create_app
from idearadar.config import Settings
from idearadar.db import utcnow
from idearadar.interviews import analyze, delete_old, scorecard
from idearadar.llm import BudgetExceeded
from idearadar.models import Base, Idea, Interview

CARD = {"landing_copy": {"headline": "Verkaufsbereit", "subline": "x", "bullets": []}, "hooks": [], "one_liner": "x"}
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


class ScriptedLLM:
    def __init__(self, done_after=3, fail=None):
        self.calls, self.done_after, self.fail = 0, done_after, fail

    def complete_json(self, system, user, *, max_tokens=2000):
        if self.fail:
            raise self.fail
        if "wertest ein Interview" in system:
            return {"segment": "owner", "problem_confirmed": True, "spent_money_or_time": True, "pilot_interest": "yes",
                    "stated_wtp_eur_per_month": 150, "objections": ["Datenschutz"], "partner_signal": False,
                    "quotes": ["Der Datenraum kostet mich Wochen", "dieses Zitat hat niemand gesagt"]}
        assert "Pilot-Frage" in system or "PILOTFRAGE" not in system  # the placeholder must have been replaced
        self.calls += 1
        return {"reply": f"Frage {self.calls}", "done": self.calls >= self.done_after}


def setup(llm=None, **over):
    cfg = Settings(admin_api_key="k", legal_company="Muster GmbH", legal_address="Weg 1", legal_email="a@b.de", **over)
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    s = factory()
    s.add(Idea(day=date.today(), cluster_key="k", title="Nachfolge", score=60, price_eur=199, card=CARD))
    s.commit()
    llm = llm or ScriptedLLM()
    c = TestClient(create_app(cfg, factory, llm_factory=lambda sess: llm), follow_redirects=False)
    h = {"X-API-Key": "k"}
    exp = c.post("/ideas/1/decision", headers=h, json={"decision": "approve"}).json()["experiment_id"]
    slug = c.post(f"/experiments/{exp}/landing", headers=h).json()["slug"]
    return cfg, factory, c, h, exp, slug


def test_requires_consent_and_discloses_ai():
    cfg, factory, c, h, exp, slug = setup()
    page = c.get(f"/i/{slug}").text
    assert "eine <b>KI</b>" in page and "Speicherdauer 90 Tage" in page
    assert c.post(f"/i/{slug}/start", content="", headers=FORM).status_code == 400
    assert factory().scalar(select(Interview)) is None  # nothing is stored without consent


def test_interview_flow_and_analysis_with_verified_quotes():
    cfg, factory, c, h, exp, slug = setup(llm=ScriptedLLM(done_after=2))
    html = c.post(f"/i/{slug}/start", content="consent=1", headers=FORM).text
    token = html.split("data-token='")[1].split("'")[0]
    assert "Sie sprechen mit einer KI" in html
    r1 = c.post(f"/i/t/{token}/message", json={"text": ""}).json()  # first call opens the interview
    assert r1 == {"reply": "Frage 1", "done": False}
    r2 = c.post(f"/i/t/{token}/message", json={"text": "Der Datenraum kostet mich Wochen und ich zahle 200 Euro im Monat."}).json()
    assert r2["done"] is True
    assert c.post(f"/i/t/{token}/message", json={"text": "noch was"}).status_code == 409
    iv = factory().scalar(select(Interview))
    assert iv.status == "done" and iv.analysis["quotes"] == ["Der Datenraum kostet mich Wochen"]  # invented quote dropped
    assert c.get(f"/experiments/{exp}/interview-report").status_code == 401


def test_llm_failure_is_a_clean_503():
    cfg, factory, c, h, exp, slug = setup(llm=ScriptedLLM(fail=BudgetExceeded("cap")))
    token = c.post(f"/i/{slug}/start", content="consent=1", headers=FORM).text.split("data-token='")[1].split("'")[0]
    assert c.post(f"/i/t/{token}/message", json={"text": ""}).status_code == 503


def test_scorecard_verdicts_and_retention():
    cfg, factory, c, h, exp, slug = setup()
    s = factory()

    def add(segment, problem=True, spent=True, pilot="yes", partner=False, n=1):
        for _ in range(n):
            s.add(Interview(experiment_id=exp, token=f"t{s.query(Interview).count()}", status="done", analysis={
                "segment": segment, "problem_confirmed": problem, "spent_money_or_time": spent, "pilot_interest": pilot,
                "partner_signal": partner, "stated_wtp_eur_per_month": 150}))
            s.commit()

    add("owner", n=4)
    assert scorecard(s, exp)["verdict"] == "CONTINUE"  # not enough interviews yet
    add("owner", n=6)
    add("advisor", partner=True, n=5)
    assert scorecard(s, exp)["verdict"] == "GO"
    s2 = factory()
    for iv in s2.scalars(select(Interview).where(Interview.analysis["segment"].as_string() == "owner")):
        iv.analysis = {**iv.analysis, "pilot_interest": "no", "spent_money_or_time": False}
    s2.commit()
    res = scorecard(factory(), exp)
    assert res["verdict"] == "KILL_OR_REWORK" and not res["rules"]["pilot_yes_ge_50pct"]
    old = s.scalar(select(Interview))
    old.created_at = utcnow() - timedelta(days=100)
    s.commit()
    assert delete_old(s, 90) == 1


def test_interview_setup_needs_landing_and_stores_questions():
    cfg, factory, c, h, exp, slug = setup()
    r = c.post(f"/experiments/{exp}/interview", headers=h, json={"questions": ["Frage A?", "  ", "Frage B?"]})
    assert r.json()["url"].endswith(f"/i/{slug}")
    from idearadar.models import Landing
    assert factory().scalar(select(Landing)).interview_questions == ["Frage A?", "Frage B?"]
