"""Public routes for landing pages (no API key): visit counting, double-opt-in waitlist, Stripe pre-order, webhook."""
import hashlib
import re
import secrets
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from .config import Settings
from .db import utcnow
from .guardrails import Guardrails
from .landing import render_datenschutz, render_impressum, render_landing
from .mailer import LogMailer, Mailer
from .models import Landing, Preorder, WaitlistEntry
from .stripe_client import StripeError, create_checkout_session, verify_webhook

BOT = re.compile(r"bot|crawl|spider|preview|facebookexternalhit|slurp|headless", re.I)
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


def _form(body: bytes) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(body.decode("utf-8", "ignore"), keep_blank_values=True).items()}


def build_router(cfg: Settings, factory, mailer: Mailer | None = None, http_client=None) -> APIRouter:
    r = APIRouter()
    mail = mailer or LogMailer()

    def visitor_hash(request: Request) -> str:
        ip = request.client.host if request.client else ""
        ua = request.headers.get("user-agent", "")
        return hashlib.sha256(f"{cfg.hash_secret}|{utcnow().date()}|{ip}|{ua}".encode()).hexdigest()

    def variant_for(h: str) -> str:
        return "a" if int(h[:2], 16) % 2 == 0 else "b"

    def get_landing(s, slug: str) -> Landing:
        lp = s.scalar(select(Landing).where(Landing.slug == slug))
        if lp is None:
            raise HTTPException(404)
        return lp

    @r.get("/l/{slug}", response_class=HTMLResponse)
    def show(slug: str, request: Request, v: str = ""):
        from .models import Visit

        with factory() as s:
            lp = get_landing(s, slug)
            h = visitor_hash(request)
            variant = v if v in ("a", "b") else variant_for(h)
            if not BOT.search(request.headers.get("user-agent", "")):
                try:
                    s.add(Visit(experiment_id=lp.experiment_id, variant=variant, day=utcnow().date(), visitor_hash=h))
                    s.commit()
                except IntegrityError:
                    s.rollback()
            msg = {"ok": "Fast geschafft: bitte bestätige deine E-Mail-Adresse über den Link, den wir dir geschickt haben.",
                   "bad": "Bitte gib eine gültige E-Mail-Adresse an.", "paid": "Danke! Deine Reservierung ist eingegangen."}.get(
                request.query_params.get("m", ""), "")
            taken = s.scalar(select(func.count()).select_from(WaitlistEntry).where(
                WaitlistEntry.experiment_id == lp.experiment_id, WaitlistEntry.confirmed.is_(True), WaitlistEntry.unsubscribed.is_(False))) or 0
            return render_landing(lp, variant, cfg, message=msg, spots_taken=taken)

    @r.post("/l/{slug}/join")
    async def join(slug: str, request: Request):
        f = _form(await request.body())
        with factory() as s:
            lp = get_landing(s, slug)
            email, variant = f.get("email", "").strip().lower(), f.get("v", "a")
            if f.get("website"):  # honeypot
                return RedirectResponse(f"/l/{slug}?m=ok", 303)
            if not EMAIL.match(email) or len(email) > 254:
                return RedirectResponse(f"/l/{slug}?m=bad&v={variant if variant in 'ab' else 'a'}", 303)
            if Guardrails(s, cfg)._suppressed("*", email) or Guardrails(s, cfg)._suppressed("email", email):
                return RedirectResponse(f"/l/{slug}?m=ok", 303)  # do not reveal suppression state
            token = secrets.token_urlsafe(24)
            s.add(WaitlistEntry(experiment_id=lp.experiment_id, email=email, name=f.get("name", "")[:100],
                                variant=variant if variant in ("a", "b") else "a", token=token))
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                return RedirectResponse(f"/l/{slug}?m=ok", 303)
            mail.send(email, "Bitte bestätige deine Anmeldung",
                      f"Hallo {f.get('name', '')},\n\nbitte bestätige deine Anmeldung zur Warteliste:\n{cfg.public_base_url}/l/confirm/{token}\n\n"
                      f"Wenn du das nicht warst, ignoriere diese Mail. Abmelden: {cfg.public_base_url}/l/unsubscribe/{token}\n\n{cfg.legal_company}")
        return RedirectResponse(f"/l/{slug}?m=ok", 303)

    @r.get("/l/confirm/{token}", response_class=HTMLResponse)
    def confirm(token: str):
        with factory() as s:
            e = s.scalar(select(WaitlistEntry).where(WaitlistEntry.token == token))
            if e is None:
                raise HTTPException(404)
            if not e.confirmed:
                e.confirmed, e.confirmed_at = True, utcnow()
                lp = s.scalar(select(Landing).where(Landing.experiment_id == e.experiment_id))
                taken = s.scalar(select(func.count()).select_from(WaitlistEntry).where(
                    WaitlistEntry.experiment_id == e.experiment_id, WaitlistEntry.pilot.is_(True))) or 0
                if lp and lp.pilot_spots > taken:
                    e.pilot = True
                s.commit()
                if e.pilot and lp:
                    from .landing import pilot_terms
                    get, ask = pilot_terms(lp, next(iter(lp.variants.values())))
                    mail.send(e.email, "Du bist Pilotkunde",
                              f"Willkommen im Pilotprogramm: {get}.\nWir bitten dich um: {ask}.\n"
                              f"Wir melden uns persönlich zum Start. Es gibt keine automatische Abbuchung; "
                              f"danach {lp.pilot_discount_pct} % Gründerrabatt für 12 Monate, wenn du bleiben willst.\n"
                              f"Abmelden: {cfg.public_base_url}/l/unsubscribe/{e.token}\n\n{cfg.legal_company}")
            return "<!doctype html><meta charset=utf-8><p style='font-family:system-ui;max-width:560px;margin:40px auto'>Danke, du bist auf der Warteliste.</p>"

    @r.get("/l/unsubscribe/{token}", response_class=HTMLResponse)
    def unsubscribe(token: str):
        with factory() as s:
            e = s.scalar(select(WaitlistEntry).where(WaitlistEntry.token == token))
            if e is None:
                raise HTTPException(404)
            e.unsubscribed = True
            s.commit()
            Guardrails(s, cfg).suppress("*", e.email, "unsubscribed from waitlist")
            return "<!doctype html><meta charset=utf-8><p style='font-family:system-ui;max-width:560px;margin:40px auto'>Du wurdest abgemeldet.</p>"

    @r.post("/l/{slug}/reserve")
    async def reserve(slug: str, request: Request):
        f = _form(await request.body())
        email = f.get("email", "").strip().lower()
        with factory() as s:
            lp = get_landing(s, slug)
            if not lp.preorder_enabled or not cfg.stripe_secret_key:
                raise HTTPException(404)
            if not EMAIL.match(email):
                return RedirectResponse(f"/l/{slug}?m=bad", 303)
            variant = f.get("v", "a") if f.get("v") in ("a", "b") else "a"
            amount = int(round(lp.deposit_eur * 100))
            try:
                sess = create_checkout_session(
                    cfg.stripe_secret_key, amount_cents=amount, product_name="Reservierung (voll erstattbar bis Launch)",
                    success_url=f"{cfg.public_base_url}/l/{slug}?m=paid", cancel_url=f"{cfg.public_base_url}/l/{slug}",
                    email=email, experiment_id=lp.experiment_id, variant=variant, client=http_client)
            except StripeError:
                raise HTTPException(502, "payment provider unavailable")
            s.add(Preorder(experiment_id=lp.experiment_id, email=email, variant=variant, stripe_session_id=sess["id"], amount_cents=amount))
            s.commit()
            return RedirectResponse(sess["url"], 303)

    @r.post("/stripe/webhook")
    async def webhook(request: Request):
        payload = await request.body()
        try:
            event = verify_webhook(payload, request.headers.get("stripe-signature", ""), cfg.stripe_webhook_secret)
        except StripeError:
            raise HTTPException(400, "invalid signature")
        if event.get("type") == "checkout.session.completed":
            obj = event["data"]["object"]
            if obj.get("payment_status") == "paid":
                with factory() as s:
                    p = s.scalar(select(Preorder).where(Preorder.stripe_session_id == obj["id"]))
                    if p and p.status != "paid":
                        p.status, p.paid_at = "paid", utcnow()
                        s.commit()
        return {"received": True}

    @r.get("/l/{slug}/impressum", response_class=HTMLResponse)
    def impressum(slug: str):
        with factory() as s:
            get_landing(s, slug)
        return render_impressum(cfg)

    @r.get("/l/{slug}/datenschutz", response_class=HTMLResponse)
    def datenschutz(slug: str):
        with factory() as s:
            get_landing(s, slug)
        return render_datenschutz(cfg)

    return r
