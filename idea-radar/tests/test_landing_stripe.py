import hashlib
import hmac
import json
import time
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from idearadar.api import create_app
from idearadar.config import Settings
from idearadar.landing import build_variants, render_landing
from idearadar.mailer import LogMailer
from idearadar.models import Base, Idea, Landing, Preorder, Visit, WaitlistEntry
from idearadar.stripe_client import StripeError, create_checkout_session, verify_webhook

SECRET = "whsec_test"
CARD = {"landing_copy": {"headline": "Haus <b>im Griff</b>", "subline": "Wartung ohne Stress", "bullets": ["Handwerker", "Fristen"]},
        "hooks": ["Dein Zweitwohnsitz, ohne Anrufe", "Zweiter Hook", "c", "d", "e"], "one_liner": "x"}


def sign(payload: bytes, ts=None):
    ts = ts or int(time.time())
    return f"t={ts},v1=" + hmac.new(SECRET.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()


def setup(**over):
    cfg = Settings(admin_api_key="k", min_gap_seconds=0, legal_company="Muster GmbH", legal_address="Weg 1, 50667 Köln",
                   legal_email="hi@example.com", stripe_secret_key="sk_test_x", stripe_webhook_secret=SECRET, **over)
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    s = factory()
    s.add(Idea(day=date.today(), cluster_key="k", title="Zweitwohnsitz Copilot", score=70, price_eur=49, card=CARD))
    s.commit()
    mailer = LogMailer()

    def handler(request: httpx.Request):
        assert request.headers["authorization"] == "Bearer sk_test_x"
        body = request.content.decode()
        assert "line_items%5B0%5D%5Bprice_data%5D%5Bunit_amount%5D=900" in body
        return httpx.Response(200, json={"id": "cs_test_1", "url": "https://checkout.stripe.com/c/cs_test_1"})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    c = TestClient(create_app(cfg, factory, mailer, http), follow_redirects=False)
    h = {"X-API-Key": "k"}
    exp_id = c.post("/ideas/1/decision", headers=h, json={"decision": "approve"}).json()["experiment_id"]
    return cfg, factory, c, h, exp_id, mailer


def test_landing_requires_legal_data():
    cfg = Settings(admin_api_key="k")
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    s = factory()
    s.add(Idea(day=date.today(), cluster_key="k", title="t", score=1, card=CARD))
    s.commit()
    c = TestClient(create_app(cfg, factory))
    h = {"X-API-Key": "k"}
    c.post("/ideas/1/decision", headers=h, json={"decision": "approve"})
    r = c.post("/experiments/1/landing", headers=h)
    assert r.status_code == 409 and "Impressum" in r.json()["detail"]


def test_variants_and_escaping():
    idea = Idea(title="t", card=CARD, price_eur=49, day=date.today(), cluster_key="k", score=1)
    v = build_variants(idea)
    assert v["b"]["headline"] == "Dein Zweitwohnsitz, ohne Anrufe" and v["a"]["headline"].startswith("Haus")
    lp = Landing(slug="s", variants=v, preorder_enabled=False, deposit_eur=9, price_eur=49, experiment_id=1)
    html = render_landing(lp, "a", Settings())
    assert "<b>im Griff" not in html and "&lt;b&gt;im Griff" in html
    assert "noch in Entwicklung" in html  # mandatory notice


def test_full_funnel_double_opt_in_visits_and_unsubscribe():
    cfg, factory, c, h, exp_id, mailer = setup()
    slug = c.post(f"/experiments/{exp_id}/landing", headers=h).json()["slug"]
    assert c.get(f"/l/{slug}", headers={"user-agent": "Googlebot"}).status_code == 200
    assert c.get(f"/l/{slug}", headers={"user-agent": "Mozilla/5.0"}).status_code == 200
    assert c.get(f"/l/{slug}", headers={"user-agent": "Mozilla/5.0"}).status_code == 200  # same visitor: counted once
    s = factory()
    assert len(s.scalars(select(Visit)).all()) == 1
    form = {"Content-Type": "application/x-www-form-urlencoded"}
    r = c.post(f"/l/{slug}/join", content="email=Anna%40example.com&name=Anna&v=a&website=", headers=form)
    assert r.status_code == 303
    assert c.get(f"/experiments/{exp_id}/funnel", headers=h).json()["signups"] == 0  # not confirmed yet
    assert mailer.sent and "confirm/" in mailer.sent[0][2]
    token = mailer.sent[0][2].split("/l/confirm/")[1].split()[0]
    assert c.get(f"/l/confirm/{token}").status_code == 200
    assert c.get(f"/experiments/{exp_id}/funnel", headers=h).json()["signups"] == 1
    # honeypot and bad e-mail do not create entries
    c.post(f"/l/{slug}/join", content="email=bot%40example.com&website=spam", headers=form)
    assert c.post(f"/l/{slug}/join", content="email=nope", headers=form).headers["location"].endswith("m=bad&v=a")
    assert len(factory().scalars(select(WaitlistEntry)).all()) == 1
    # unsubscribe removes from the count and suppresses everywhere
    assert c.get(f"/l/unsubscribe/{token}").status_code == 200
    assert c.get(f"/experiments/{exp_id}/funnel", headers=h).json()["signups"] == 0
    c.post(f"/l/{slug}/join", content="email=anna%40example.com", headers=form)
    assert len(mailer.sent) == 1  # no new mail to a suppressed address
    assert "Muster GmbH" in c.get(f"/l/{slug}/impressum").text


def test_preorder_checkout_and_webhook():
    cfg, factory, c, h, exp_id, _ = setup()
    slug = c.post(f"/experiments/{exp_id}/landing?preorder=true", headers=h).json()["slug"]
    r = c.post(f"/l/{slug}/reserve", content="email=kunde%40example.com&v=b", headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 303 and r.headers["location"].startswith("https://checkout.stripe.com/")
    assert c.get(f"/experiments/{exp_id}/funnel", headers=h).json()["preorders"] == 0  # pending is not paid
    event = json.dumps({"type": "checkout.session.completed", "data": {"object": {"id": "cs_test_1", "payment_status": "paid"}}}).encode()
    assert c.post("/stripe/webhook", content=event, headers={"stripe-signature": "t=1,v1=bad"}).status_code == 400
    assert c.post("/stripe/webhook", content=event, headers={"stripe-signature": sign(event)}).status_code == 200
    f = c.get(f"/experiments/{exp_id}/funnel", headers=h).json()
    assert f["preorders"] == 1 and f["variants"]["b"]["preorders"] == 1
    assert c.get(f"/experiments/{exp_id}/evaluation", headers=h).json()["recommendation"] == "CONTINUE"
    assert factory().scalar(select(Preorder)).status == "paid"


def test_reserve_hidden_without_preorder_flag():
    cfg, factory, c, h, exp_id, _ = setup()
    slug = c.post(f"/experiments/{exp_id}/landing", headers=h).json()["slug"]
    assert c.post(f"/l/{slug}/reserve", content="email=a%40b.de", headers={"Content-Type": "application/x-www-form-urlencoded"}).status_code == 404
    assert "Platz reservieren" not in c.get(f"/l/{slug}").text


def test_stripe_signature_rules():
    payload = b'{"type":"x"}'
    assert verify_webhook(payload, sign(payload), SECRET)["type"] == "x"
    with pytest.raises(StripeError):
        verify_webhook(payload, sign(payload, ts=int(time.time()) - 3600), SECRET)  # replay
    with pytest.raises(StripeError):
        verify_webhook(payload + b" ", sign(payload), SECRET)  # tampered body
    with pytest.raises(StripeError):
        verify_webhook(payload, sign(payload), "")  # no secret configured
    with pytest.raises(StripeError):
        create_checkout_session("", amount_cents=100, product_name="p", success_url="s", cancel_url="c", email="a@b.de", experiment_id=1, variant="a")
