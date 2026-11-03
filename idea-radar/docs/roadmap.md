# Standard-Roadmap für jede Idee (fester Ablauf)

Jede freigegebene Idee durchläuft dieselben Stufen. **Stufe 3 (No-Brainer-Pilotangebot) ist Pflicht** und Gate für die Landingpage.

| # | Stufe | Ergebnis / Gate | Dauer |
|---|---|---|---|
| 0 | Radar + Freigabe | 3 Idea-Cards/Tag, Leopold gibt frei | täglich |
| 1 | Evidenz | ≥ 20 echte öffentliche Beiträge (wörtliche Zitate, Links) | 2–3 Tage |
| 2 | Gespräche | 10 Zielkunden + 5 Berater/Partner; Entscheidungsregel der Idee (siehe `radar/nachfolge-interviews.md`) | 1–2 Wochen |
| 3 | **No-Brainer-Pilotangebot** | Angebot geschrieben, rechtlich geprüft, Kapazität für Pilot-Betreuung geklärt | 1–2 Tage |
| 4 | Landingpage + Warteliste + Pilotplätze (+ erstattbare Reservierung) | Seite live, Impressum/Datenschutz vorhanden | 2–3 Tage |
| 5 | Pilot durchführen | 5–10 Pilotkunden, 3 Monate, händisch/KI-gestützt (Concierge), wöchentliche Nutzung messen | 3 Monate |
| 6 | Umwandlung in Zahlung | Gründerpreis, Stripe-Abo; Pilot→zahlend ≥ 30 % | Ende Pilot |
| 7 | Go / Kill / Pivot | Entscheidung mit Zahlen | nach Stufe 6 |

## Das No-Brainer-Pilotangebot (Pflichtbaustein)

Ziel: Für den ersten Kunden muss „Ja“ sagen leichter sein als „Nein“ sagen, ohne dass das Angebot unehrlich wird.

**Bestandteile (alle fünf müssen in der Idea-Card stehen):**
1. **Du bekommst:** ein konkretes Ergebnis, kostenlos für `PILOT_MONTHS` (Standard 3 Monate), **ohne Zahlungsdaten** und ohne automatische Verlängerung.
2. **Begrenzt, aber echt:** `PILOT_SPOTS` Plätze (Standard 10) an die ersten **bestätigten** Anmeldungen. Der Zähler auf der Seite wird aus der Datenbank berechnet, nie erfunden.
3. **Wir bitten dich um:** eine kleine, klare Gegenleistung: z. B. 15-Min-Gespräch alle 2 Wochen, ehrliches Feedback, Erlaubnis für eine **anonymisierte** Fallstudie. Das sichert Aussagekraft, denn rein kostenlose Nutzer geben schwächere Signale als Verpflichtete.
4. **Danach:** Gründerpreis (Standard −30 % für 12 Monate), nur wenn der Pilot bleiben will; Kündigung jederzeit. **Keine Lifetime-Deals** (Folgekosten ohne Umsatz).
5. **Risikoumkehr:** Was passiert, wenn es nichts bringt? (z. B. „Wenn du nach 4 Wochen keinen konkreten Nutzen siehst, sagst du es und wir hören auf; es kostet dich nichts.“)

**Regeln:** keine erfundene Knappheit, keine Fake-Testimonials; Pilot-Zusagen nur, wenn wir ihn wirklich betreuen können; Pilot-Daten nur nach Datenschutzvorgaben.

**Messgrößen (Stufe 5/6):** Aktivierung (erste Nutzung < 7 Tage), wöchentliche Nutzung ≥ 60 %, Pilot→zahlend ≥ 30 %, mindestens 3 Fallstudien mit Freigabe, genannte Zahlungsbereitschaft vs. tatsächliche Zahlung.

**Umsetzung im Code:** `Settings.pilot_spots/pilot_months/pilot_discount_pct`, `Landing.pilot_*`, Pilotblock auf der Seite (`landing.py`), Pilot-Zuteilung bei Bestätigung (`web.py`), `pilots` im Funnel (`metrics.py`), `pilot_offer` in der Idea-Card (`pipeline.py`).

## Pilotangebot Idee A (Nachfolge-Readiness) – Entwurf
- **Du bekommst:** 3 Monate kostenlos: Readiness-Check, Red-Flag-Liste, Datenraum-Index und monatliche Aufgabenliste; persönlich begleitet.
- **Plätze:** 10 Inhaber, kein Vertrag, keine Zahlungsdaten.
- **Wir bitten:** 15 Min alle 2 Wochen Feedback; anonymisierte Fallstudie nur nach deiner Freigabe.
- **Danach:** 199 € → Gründerpreis ca. 139 €/Monat für 12 Monate, nur wenn du bleiben willst.
- **Risikoumkehr:** Wenn nach 4 Wochen kein konkreter Nutzen sichtbar ist, hören wir auf; keine Kosten, kein Haken.
- **Achtung Kapazität:** 10 betreute Piloten kosten uns Zeit; vor Start Aufwand pro Pilot schätzen (Annahme: 2–3 Std./Monat).
