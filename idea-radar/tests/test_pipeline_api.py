from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from idearadar.api import create_app
from idearadar.collectors.base import RawItemData
from idearadar.collectors.hackernews import parse_hits
from idearadar.collectors.youtube import parse_comments
from idearadar.config import Settings
from idearadar.experiment import evaluate
from idearadar.models import Base, Idea, Problem
from idearadar.pipeline import run_daily

TEXTS = [
    ("alice", "Ich leite eine GmbH mit 40 Mitarbeitern. Ferienimmobilie verwalten, Handwerker koordinieren und Wartung am Zweitwohnsitz kostet mich Nerven."),
    ("bob", "Wartung Ferienimmobilie Handwerker koordinieren am Zweitwohnsitz ist ein Albtraum, ich bezahle schon 200 Euro im Monat für eine Hausverwaltung."),
]


class FakeCollector:
    name = "fake"

    def fetch(self):
        return [RawItemData("fake", f"http://x/{i}", a, t) for i, (a, t) in enumerate(TEXTS)]


class ScriptedLLM:
    def complete_json(self, system, user, *, max_tokens=2000):
        if "extract concrete" in system.lower() or "You extract" in system:
            return {"problems": [
                {"item_id": 1, "summary": "Ferienimmobilie Wartung Handwerker koordinieren Zweitwohnsitz", "persona": "GF", "affluence": 0.9,
                 "affluence_quote": "GmbH mit 40 Mitarbeitern", "wtp": 0.0, "wtp_quote": ""},
                {"item_id": 2, "summary": "Wartung Ferienimmobilie Handwerker koordinieren Zweitwohnsitz Albtraum", "persona": "Eigentümer", "affluence": 0.5,
                 "affluence_quote": "Hausverwaltung", "wtp": 0.8, "wtp_quote": "bezahle schon 200 Euro im Monat"}]}
        return {"title": "Zweitwohnsitz-Copilot", "one_liner": "x", "offering": "ai_service", "price_eur": 49, "competition_gap": 0.6,
                "ai_automatable": 0.8, "build_days": 7, "reach": 0.7, "timing": 0.3, "hooks": ["a", "b", "c", "d", "e"]}


def make(cfg):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def test_pipeline_creates_pending_idea_and_dedupes():
    cfg = Settings(admin_api_key="k")
    factory = make(cfg)
    s = factory()
    ideas = run_daily(s, [FakeCollector()], ScriptedLLM(), cfg)
    assert len(ideas) == 1 and ideas[0].status == "pending" and ideas[0].score > 40
    assert s.scalar(select(Problem).where(Problem.wtp_evidence == "bezahle schon 200 Euro im Monat")) is not None
    assert run_daily(s, [FakeCollector()], ScriptedLLM(), cfg) == []  # same cluster is not proposed twice


def test_api_auth_and_approval_flow():
    cfg = Settings(admin_api_key="k", min_gap_seconds=0)
    factory = make(cfg)
    s = factory()
    s.add(Idea(day=date.today(), cluster_key="k", title="t", score=70, price_eur=49))
    s.commit()
    c = TestClient(create_app(cfg, factory))
    assert c.get("/ideas").status_code == 401
    h = {"X-API-Key": "k"}
    assert len(c.get("/ideas", headers=h).json()) == 1
    r = c.post("/ideas/1/decision", headers=h, json={"decision": "approve", "test_days": 10})
    assert r.json()["experiment_id"] == 1 and r.json()["test_days"] == 10
    assert c.post("/ideas/1/decision", headers=h, json={"decision": "approve"}).status_code == 409  # fail-safe: no double start
    msg = "Hi, ich baue gerade ein Tool für Hausverwaltung, wie löst du das heute eigentlich?"
    assert c.post("/experiments/1/outreach", headers=h, json={"channel": "x", "handle": "a", "body": msg}).json()["status"] == "dry_run"
    c.post("/killswitch", headers=h, json={"enabled": True})
    assert c.post("/experiments/1/outreach", headers=h, json={"channel": "x", "handle": "b", "body": msg}).json()["status"] == "blocked"
    c.post("/experiments/1/metrics", headers=h, json={"visitors": 200, "signups": 31, "preorders": 0, "spend_eur": 40})
    assert c.get("/experiments/1/evaluation", headers=h).json()["recommendation"] == "GO"


def test_api_refuses_without_configured_key():
    cfg = Settings(admin_api_key="")
    c = TestClient(create_app(cfg, make(cfg)))
    assert c.get("/ideas", headers={"X-API-Key": ""}).status_code == 503


def test_evaluate_rules():
    cfg = Settings()
    assert evaluate({"visitors": 300, "signups": 2, "preorders": 0, "spend_eur": 60}, 8, 14, 100, cfg)["recommendation"] == "KILL"
    assert evaluate({"visitors": 50, "signups": 1, "preorders": 0, "spend_eur": 80}, 8, 14, 100, cfg)["recommendation"] == "KILL"
    assert evaluate({"visitors": 300, "signups": 12, "preorders": 0, "spend_eur": 60}, 8, 14, 100, cfg)["recommendation"] == "CONTINUE"
    assert evaluate({"visitors": 300, "signups": 12, "preorders": 0, "spend_eur": 60}, 14, 14, 100, cfg)["recommendation"] == "EXTEND"
    assert evaluate({"visitors": 10, "signups": 0, "preorders": 3, "spend_eur": 0}, 1, 14, 100, cfg)["recommendation"] == "GO"


def test_parsers():
    hn = parse_hits({"hits": [{"objectID": "1", "comment_text": "I pay 300 a month for a tool that does not do what I need at all.", "author": "z", "created_at_i": 1700000000},
                              {"objectID": "2", "comment_text": "short"}]})
    assert len(hn) == 1 and hn[0].url.endswith("id=1") and hn[0].author_handle == "z"
    yt = parse_comments("vid", {"items": [{"snippet": {"topLevelComment": {"id": "c1", "snippet": {
        "textOriginal": "Ich suche seit Monaten ein Tool für die Verwaltung meiner Immobilien, nichts passt.", "authorDisplayName": "Max", "publishedAt": "2026-10-01T10:00:00Z"}}}}]})
    assert len(yt) == 1 and "lc=c1" in yt[0].url
