"""Automated AI interviews: public chat page, transcript analysis with verified quotes, decision scorecard.
Hard rules: AI disclosure + explicit consent before the first message, no name collected, turn and length caps,
90-day retention, no sales pitch before the final pilot question."""
import json
import re
import secrets
from datetime import timedelta
from html import escape

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .db import utcnow
from .extract import verify_quote
from .landing import CSS, _page, pilot_terms
from .llm import BudgetExceeded
from .models import Interview, Landing

MAX_TURNS = 14
MAX_CHARS = 2000
DEFAULT_QUESTIONS = [
    "Welche Rolle haben Sie (Inhaber/in, Berater/in, anderes) und worum geht es bei Ihnen aktuell beim Thema?",
    "Wie weit sind Sie damit (Idee, Gespräche, Zeitplan)?",
    "Was haben Sie bisher konkret getan, und was hat Sie überrascht oder viel Zeit/Geld gekostet?",
    "Wer hilft Ihnen dabei, und wie zufrieden sind Sie?",
    "Was war bisher am schwersten oder nervigsten?",
    "Wovor haben Sie die größte Sorge?",
    "Was geben Sie heute dafür aus (Geld oder Stunden)?",
    "Wem müsste ein Angebot dafür empfohlen werden, damit Sie ihm vertrauen?",
]

SYSTEM = """Du bist ein höflicher KI-Interviewer für eine Marktforschung. Du bist eine KI und sagst das, wenn gefragt.
Regeln: genau EINE kurze Frage pro Nachricht, auf Deutsch, siezen. Frage nach vergangenem Verhalten und konkreten Beispielen, nicht nach Meinungen über Zukünftiges.
Nichts verkaufen, nicht bewerten, nicht beraten, keine Rechts- oder Steuerberatung. Keine sensiblen Daten erfragen (Gesundheit, Religion, Politik, Konto-/Passwortdaten); wenn jemand solche Angaben macht, bitte freundlich darum, sie wegzulassen.
Ablauf: stelle die Fragen aus der Liste nacheinander (passe sie dem Gesprächsverlauf an, wiederhole nichts, frage bei vagen Antworten einmal nach einem Beispiel nach). Stelle ganz zum Schluss die Pilot-Frage genau so: PILOTFRAGE. Danach bedanke dich, nenne die Option, sich auf die Warteliste einzutragen (der Link wird automatisch angezeigt), und beende mit done=true.
Beende spätestens nach 12 Fragen. Antworte NUR mit JSON: {"reply": "...", "done": false}.

FRAGENLISTE:
QUESTIONS
"""

ANALYSIS_SYSTEM = """Du wertest ein Interview aus. Antworte NUR mit JSON:
{"segment": "owner"|"advisor"|"other", "problem_confirmed": bool (die Person schildert das Problem als echt und aktuell),
"spent_money_or_time": bool (hat schon Geld oder viel Zeit dafür ausgegeben, belegt durch eigene Aussage), "pilot_interest": "yes"|"maybe"|"no"|"not_asked",
"stated_wtp_eur_per_month": number|null, "objections": [kurze Stichworte], "partner_signal": bool (Berater stellt Empfehlung/Partnerschaft konkret in Aussicht),
"quotes": [bis zu 3 WÖRTLICHE Zitate der Person, je 8-200 Zeichen, exakt aus ihren Nachrichten kopiert]}.
Setze Werte nur, wenn die Person es selbst gesagt hat; sonst false/null/not_asked."""


def build_system(lp: Landing, questions: list[str]) -> str:
    get, ask = pilot_terms(lp, next(iter(lp.variants.values())))
    pilot_q = (f"Angenommen, es gäbe {lp.pilot_months or 3} Monate lang kostenlos: {get}. Im Gegenzug bitten wir um: {ask}. "
               f"Würden Sie das nutzen, warum oder warum nicht, und was müsste dabei herauskommen, damit Sie danach dafür zahlen würden und wie viel?")
    qs = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(questions or DEFAULT_QUESTIONS))
    return SYSTEM.replace("PILOTFRAGE", f'"{pilot_q}"').replace("QUESTIONS", qs)


def _msgs(transcript: list[dict]) -> list[dict]:
    return [{"role": m["role"], "content": m["text"]} for m in transcript]


def next_turn(llm, system: str, transcript: list[dict]) -> dict:
    """Asks the model for the next interviewer message. llm.complete_json takes a single user string, so the
    running transcript is passed as text."""
    convo = "\n".join(f"{'Interviewer' if m['role'] == 'assistant' else 'Teilnehmer'}: {m['text']}" for m in transcript)
    data = llm.complete_json(system, f"Bisheriges Gespräch:\n{convo or '(noch leer, beginne mit der ersten Frage)'}\n\nSchreibe jetzt die nächste Interviewer-Nachricht als JSON.", max_tokens=600)
    reply = str(data.get("reply", "")).strip() if isinstance(data, dict) else ""
    return {"reply": reply[:1500], "done": bool(isinstance(data, dict) and data.get("done"))}


def analyze(llm, transcript: list[dict]) -> dict:
    user_text = " ".join(m["text"] for m in transcript if m["role"] == "user")
    data = llm.complete_json(ANALYSIS_SYSTEM, "\n".join(f"{m['role']}: {m['text']}" for m in transcript), max_tokens=900)
    if not isinstance(data, dict):
        return {}
    quotes = [q for q in (data.get("quotes") or []) if isinstance(q, str) and verify_quote(q, user_text)][:3]  # drop invented quotes
    wtp = data.get("stated_wtp_eur_per_month")
    return {
        "segment": data.get("segment") if data.get("segment") in ("owner", "advisor", "other") else "other",
        "problem_confirmed": bool(data.get("problem_confirmed")), "spent_money_or_time": bool(data.get("spent_money_or_time")),
        "pilot_interest": data.get("pilot_interest") if data.get("pilot_interest") in ("yes", "maybe", "no") else "not_asked",
        "stated_wtp_eur_per_month": float(wtp) if isinstance(wtp, (int, float)) and wtp >= 0 else None,
        "objections": [str(o)[:80] for o in (data.get("objections") or [])][:6],
        "partner_signal": bool(data.get("partner_signal")), "quotes": quotes,
    }


def scorecard(session: Session, experiment_id: int, min_owners: int = 10, min_advisors: int = 5) -> dict:
    rows = session.scalars(select(Interview).where(Interview.experiment_id == experiment_id, Interview.status == "done")).all()
    an = [r.analysis for r in rows if r.analysis]
    owners = [a for a in an if a.get("segment") == "owner"]
    advisors = [a for a in an if a.get("segment") == "advisor"]
    c = {
        "owners": len(owners), "advisors": len(advisors),
        "problem_confirmed": sum(a["problem_confirmed"] for a in owners),
        "spent": sum(a["spent_money_or_time"] for a in owners),
        "pilot_yes": sum(a["pilot_interest"] == "yes" for a in owners),
        "partner_signals": sum(a["partner_signal"] for a in advisors),
        "wtp_values": sorted(a["stated_wtp_eur_per_month"] for a in owners if a.get("stated_wtp_eur_per_month")),
    }
    # decision rule from docs/radar/nachfolge-interviews.md (scaled to the number of owners interviewed)
    enough = c["owners"] >= min_owners and c["advisors"] >= min_advisors
    share = lambda n: n / c["owners"] if c["owners"] else 0.0  # noqa: E731
    rules = {"problem_ge_60pct": share(c["problem_confirmed"]) >= 0.6, "spent_ge_30pct": share(c["spent"]) >= 0.3,
             "partners_ge_2": c["partner_signals"] >= 2, "pilot_yes_ge_50pct": share(c["pilot_yes"]) >= 0.5}
    if not enough:
        verdict = "CONTINUE"
    elif all(rules.values()):
        verdict = "GO"
    else:
        verdict = "KILL_OR_REWORK"
    return {"counts": c, "rules": rules, "enough_interviews": enough, "verdict": verdict}


def delete_old(session: Session, days: int = 90) -> int:
    old = session.scalars(select(Interview).where(Interview.created_at < utcnow() - timedelta(days=days))).all()
    for r in old:
        session.delete(r)
    session.commit()
    return len(old)


CHAT_JS = """
const t=document.body.dataset.token,log=document.getElementById('log'),f=document.getElementById('f'),i=document.getElementById('i');
function add(r,x){const p=document.createElement('p');p.textContent=(r==='a'?'KI: ':'Sie: ')+x;log.appendChild(p);window.scrollTo(0,document.body.scrollHeight)}
async function send(x){const r=await fetch('/i/t/'+t+'/message',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:x})});
const d=await r.json();if(!r.ok){add('a',d.detail||'Fehler');return}add('a',d.reply);if(d.done){f.style.display='none';document.getElementById('end').style.display='block'}}
f.onsubmit=async e=>{e.preventDefault();const x=i.value.trim();if(!x)return;i.value='';add('u',x);await send(x)};
send('');
"""


def build_router(cfg: Settings, factory, llm_factory) -> APIRouter:
    r = APIRouter()

    def landing(s, slug):
        lp = s.scalar(select(Landing).where(Landing.slug == slug))
        if lp is None:
            raise HTTPException(404)
        return lp

    @r.get("/i/{slug}", response_class=HTMLResponse)
    def intro(slug: str):
        with factory() as s:
            lp = landing(s, slug)
            body = (f"<h1>Kurzes Interview (ca. 15 Minuten)</h1><p class=n><b>Hinweis:</b> Das Interview führt eine <b>KI</b>, kein Mensch. "
                    f"Ihre Antworten werden gespeichert und ausgewertet, um zu verstehen, ob ein Hilfsangebot sinnvoll ist. Wir erfragen keinen Namen "
                    f"und bitten Sie, keine sensiblen Daten zu nennen. Speicherdauer 90 Tage, danach Löschung. Teilnahme freiwillig, Abbruch jederzeit.</p>"
                    f"<form method=post action='/i/{escape(slug)}/start'><label><input type=checkbox name=consent value=1 required style='width:auto'> "
                    f"Ich habe verstanden, dass ich mit einer KI spreche, und willige in die Speicherung und Auswertung meiner Antworten ein "
                    f"(<a href='/l/{escape(slug)}/datenschutz'>Datenschutz</a>).</label><button>Interview starten</button></form>"
                    f"<footer><a href='/l/{escape(slug)}/impressum'>Impressum</a></footer>")
            return _page("Interview", body)

    @r.post("/i/{slug}/start")
    async def start(slug: str, request: Request):
        from urllib.parse import parse_qs

        form = parse_qs((await request.body()).decode("utf-8", "ignore"))
        if form.get("consent", [""])[0] != "1":
            raise HTTPException(400, "consent required")
        with factory() as s:
            lp = landing(s, slug)
            token = secrets.token_urlsafe(24)
            s.add(Interview(experiment_id=lp.experiment_id, token=token))
            s.commit()
        page = (f"<!doctype html><html lang=de><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
                f"<title>Interview</title><style>{CSS}</style></head><body data-token='{escape(token)}'><p class=n>Sie sprechen mit einer KI. "
                f"Bitte keine sensiblen Daten angeben.</p><div id=log></div><form id=f><input id=i autocomplete=off maxlength={MAX_CHARS} "
                f"placeholder='Ihre Antwort'><button>Senden</button></form><div id=end style='display:none'><p class=n>Danke für Ihre Zeit! "
                f"Wenn Sie den kostenlosen Pilotplatz möchten: <a href='/l/{escape(slug)}'>zur Warteliste</a>.</p></div>"
                f"<script>{CHAT_JS}</script></body></html>")
        return HTMLResponse(page)

    @r.post("/i/t/{token}/message")
    async def message(token: str, request: Request):
        body = await request.json()
        text = str(body.get("text", "")).strip()[:MAX_CHARS]
        with factory() as s:
            iv = s.scalar(select(Interview).where(Interview.token == token))
            if iv is None:
                raise HTTPException(404)
            if iv.status == "done":
                raise HTTPException(409, "Das Interview ist beendet.")
            tr = list(iv.transcript or [])
            if text:
                tr.append({"role": "user", "text": text})
            if sum(m["role"] == "user" for m in tr) > MAX_TURNS:
                iv.status, iv.transcript = "done", tr
                s.commit()
                raise HTTPException(409, "Das Interview ist beendet.")
            lp = s.scalar(select(Landing).where(Landing.experiment_id == iv.experiment_id))
            try:
                llm = llm_factory(s)
                turn = next_turn(llm, build_system(lp, lp.interview_questions), tr)
            except BudgetExceeded:
                raise HTTPException(503, "Gerade nicht verfügbar. Bitte später erneut versuchen.")
            except Exception:
                raise HTTPException(503, "Gerade nicht verfügbar. Bitte später erneut versuchen.")
            if not turn["reply"]:
                raise HTTPException(503, "Gerade nicht verfügbar. Bitte später erneut versuchen.")
            tr.append({"role": "assistant", "text": turn["reply"]})
            iv.transcript = tr
            done = turn["done"] or sum(m["role"] == "user" for m in tr) >= MAX_TURNS
            if done:
                iv.status = "done"
                try:
                    iv.analysis = analyze(llm, tr)
                except Exception:
                    iv.analysis = {}
            s.commit()
            return JSONResponse({"reply": turn["reply"], "done": done})

    return r
