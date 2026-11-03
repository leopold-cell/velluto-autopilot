"""Landing page copy + rendering. Pages are server-rendered strings, all dynamic text is HTML-escaped,
no third-party scripts. A visible 'in development' notice is mandatory: the product does not exist yet."""
import re
import secrets
from html import escape

from sqlalchemy.orm import Session

from .config import Settings
from .models import Experiment, Idea, Landing

NOTICE = "Dieses Produkt ist noch in Entwicklung. Du trägst dich für die Warteliste ein; es gibt noch keine App und keine Garantie auf einen Launch."


class LegalMissing(ValueError):
    pass


def slugify(text: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "idee"
    return f"{base}-{secrets.token_hex(3)}"


def legal_ready(cfg: Settings) -> bool:
    return all([cfg.legal_company.strip(), cfg.legal_address.strip(), cfg.legal_email.strip()])


def build_variants(idea: Idea) -> dict:
    card = idea.card or {}
    lc = card.get("landing_copy") or {}
    hooks = [h for h in card.get("hooks", []) if isinstance(h, str) and h.strip()]
    bullets = [b for b in (lc.get("bullets") or []) if isinstance(b, str)][:5]
    a = {"headline": lc.get("headline") or idea.title, "subline": lc.get("subline") or card.get("one_liner", ""), "bullets": bullets}
    b = {**a, "headline": hooks[0] if hooks else a["headline"]}
    if len(hooks) > 1:
        b["subline"] = hooks[1]
    return {"a": a, "b": b}


def create_landing(session: Session, cfg: Settings, exp: Experiment, *, preorder: bool) -> Landing:
    if not legal_ready(cfg):
        raise LegalMissing("LEGAL_COMPANY, LEGAL_ADDRESS and LEGAL_EMAIL must be set before a landing page can go live (Impressum/Datenschutz)")
    idea = session.get(Idea, exp.idea_id)
    lp = Landing(experiment_id=exp.id, slug=slugify(idea.title), variants=build_variants(idea), preorder_enabled=preorder,
                 deposit_eur=cfg.deposit_eur, price_eur=idea.price_eur)
    session.add(lp)
    session.commit()
    return lp


CSS = ("body{font-family:system-ui,sans-serif;max-width:640px;margin:0 auto;padding:24px 16px;line-height:1.5;color:#111}"
       ".n{background:#fff4d6;border:1px solid #e6c766;padding:10px 12px;border-radius:8px;font-size:14px}"
       "input{width:100%;padding:12px;margin:6px 0;font-size:16px;box-sizing:border-box}"
       "button{width:100%;padding:14px;font-size:16px;background:#111;color:#fff;border:0;border-radius:8px;cursor:pointer;margin-top:6px}"
       "button.s{background:#fff;color:#111;border:1px solid #111}footer{margin-top:32px;font-size:13px;color:#555}"
       ".h{position:absolute;left:-9999px}")


def _page(title: str, body: str) -> str:
    return (f"<!doctype html><html lang=de><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{escape(title)}</title><style>{CSS}</style></head><body>{body}</body></html>")


def render_landing(lp: Landing, variant: str, cfg: Settings, *, message: str = "") -> str:
    v = lp.variants.get(variant) or lp.variants["a"]
    bullets = "".join(f"<li>{escape(b)}</li>" for b in v.get("bullets", []))
    price = f"<p>Geplanter Preis: <b>{lp.price_eur:.2f} € / Monat</b> (Änderungen vorbehalten).</p>" if lp.price_eur else ""
    reserve = ""
    if lp.preorder_enabled and cfg.stripe_secret_key:
        reserve = (f"<form method=post action='/l/{escape(lp.slug)}/reserve'><input type=hidden name=v value='{escape(variant)}'>"
                   f"<input name=email type=email required placeholder='E-Mail für die Reservierung'>"
                   f"<button class=s>Platz reservieren: {lp.deposit_eur:.2f} € Anzahlung, bis Launch voll erstattbar</button></form>")
    msg = f"<p class=n>{escape(message)}</p>" if message else ""
    body = (f"<p class=n>{escape(NOTICE)}</p>{msg}<h1>{escape(v['headline'])}</h1><p>{escape(v.get('subline', ''))}</p><ul>{bullets}</ul>{price}"
            f"<form method=post action='/l/{escape(lp.slug)}/join'><input type=hidden name=v value='{escape(variant)}'>"
            f"<input class=h name=website tabindex=-1 autocomplete=off>"
            f"<input name=name placeholder='Vorname'><input name=email type=email required placeholder='E-Mail'>"
            f"<button>Auf die Warteliste</button></form>{reserve}"
            f"<footer>Wir senden dir eine Bestätigungs-E-Mail (Double-Opt-in). Abmeldung jederzeit per Link in jeder Mail. "
            f"<a href='/l/{escape(lp.slug)}/datenschutz'>Datenschutz</a> · <a href='/l/{escape(lp.slug)}/impressum'>Impressum</a></footer>")
    return _page(v["headline"], body)


def render_impressum(cfg: Settings) -> str:
    return _page("Impressum", f"<h1>Impressum</h1><p>{escape(cfg.legal_company)}<br>{escape(cfg.legal_address)}<br>{escape(cfg.legal_email)}</p>")


def render_datenschutz(cfg: Settings) -> str:
    body = (f"<h1>Datenschutz</h1><p>Verantwortlich: {escape(cfg.legal_company)}, {escape(cfg.legal_address)}, {escape(cfg.legal_email)}.</p>"
            "<p>Wir speichern deine E-Mail-Adresse und optional deinen Vornamen, um dich über den Launch zu informieren (Art. 6 Abs. 1 lit. a DSGVO, "
            "Einwilligung per Double-Opt-in). Besuche werden ohne Cookies und ohne Speicherung der IP-Adresse gezählt (täglich wechselnder Hash). "
            "Zahlungen laufen über Stripe. Widerruf und Löschung jederzeit per E-Mail oder Abmelde-Link.</p>"
            "<p><i>Hinweis: Dies ist eine Vorlage. Bitte vor dem Live-Gang rechtlich prüfen lassen.</i></p>")
    return _page("Datenschutz", body)
