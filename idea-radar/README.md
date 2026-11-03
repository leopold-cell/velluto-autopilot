# Idea Radar

Täglicher Problem-Radar für kaufkräftige Zielgruppen: sammelt öffentliche Beiträge, extrahiert wiederkehrende Probleme
(mit **verifizierten** Affluence-/Zahlungsbelegen), bewertet 3 SaaS-/KI-Dienstleistungs-Ideen pro Tag, wartet auf **deine Freigabe**
und startet danach einen Test (Standard 14 Tage) mit Go/Kill-Empfehlung. Gebaut als eigenständiges Projekt innerhalb von
`velluto-autopilot` (Ordner `idea-radar/`), damit es später ohne Änderungen in ein eigenes Repo verschoben werden kann.

## Status (ehrlich)

| Baustein | Stand |
|---|---|
| Collectors: Hacker News (Algolia), YouTube-Kommentare (offizielle API) | gebaut, Parser getestet; **live gegen die echten APIs noch nicht gelaufen** |
| Extraktion mit Zitat-Verifikation (erfundene Belege werden auf 0 gesetzt) | gebaut + getestet |
| Clustering (Token-Overlap, austauschbar gegen Embeddings), Scoring, Idea-Card, Deduplizierung | gebaut + getestet (LLM im Test gescriptet) |
| Freigabe per API (`/ideas`, `/ideas/{id}/decision`), Experiment-Start, Metriken, Go/Kill-Auswertung | gebaut + getestet |
| Guardrails: Kill-Switch, Dry-Run Standard, Caps, Mindestabstand, Sperrliste, Opt-out, Offenlegungspflicht, LinkedIn nur Assist-Queue, E-Mail nur Opt-in | gebaut + getestet |
| LLM-Budgetdeckel pro Tag | gebaut (nicht mit echter API getestet) |
| Landingpage (A/B, serverseitig gerendert, HTML-escaped, Pflichthinweis "in Entwicklung"), Besuchszählung ohne Cookies/IP, Double-Opt-in-Warteliste, Abmeldung + Sperrliste, Impressum/Datenschutz-Vorlage (Seite wird ohne `LEGAL_*` verweigert), Stripe-Checkout (erstattbare Anzahlung) + signierter Webhook | gebaut + getestet (Stripe/SendGrid nur mit Mock-Transport, **nicht gegen echte Konten**) |
| **Noch nicht gebaut** | echte Sender für X/Reddit (Queue-Status `queued` wird noch von niemandem abgeholt), Stripe-Rückerstattungs-Flow, Ads, Telegram/WhatsApp-Digest, Dashboard-UI, Web-Suche-/Reddit-/X-Collector, Proof-of-Demand- und „Neu möglich"-Collector |

## Start

```bash
cd idea-radar
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env     # ADMIN_API_KEY und ANTHROPIC_API_KEY setzen
pytest
python -m idearadar.scheduler --once      # einmal laufen lassen
uvicorn idearadar.api:create_app --factory --port 8100
```

Freigeben: `curl -H "X-API-Key: …" localhost:8100/ideas` → `POST /ideas/1/decision {"decision":"approve","price_eur":49}`.

## Sicherheitsprinzipien
- Alles ist **Dry-Run**, bis `DRY_RUN=false` **und** der Kanal in `LIVE_CHANNELS` steht.
- LinkedIn wird nie automatisiert; E-Mail nur an Double-Opt-in-Wartelistenmitglieder (UWG §7).
- Jede Nachricht muss offenlegen, dass du etwas baust; keine Garantien/Testimonials. Opt-out („Stopp") sperrt kanalübergreifend.
- Nicht enthalten und nicht geplant: Mehrfach-Accounts, Proxy-Rotation, Umgehung von Sperren, Scraping hinter Login.

## Dokumente
- `docs/deep-research-ai-abos-wohlhabende.md` – Marktrecherche und Produktideen
- `docs/validation-brunomind.md` – Desk-Validierung von brunomind.com mit den neuen Kriterien
- `docs/learnings-minini-bazzly-kinso.md` – Learnings aus Daniel Mininis Founder-Mode-Folge, Bazzly und Kinso und wie sie ins Radar einfließen
