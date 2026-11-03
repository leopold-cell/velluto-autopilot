# Validierung: brunomind.com (Bruno – „pocket CBT coach")

Stand 2026-11-03. Basis: die öffentlich lesbare Seite (Startseite, /about, /privacy, /terms – Text, kein Quellcode/Analytics) und Web-Recherche. Zahlen deiner Warteliste (Besucher, Anmeldungen, Quellen, Ausgaben) kenne ich nicht, deshalb ist das **Desk-Validation, kein Nachfrage-Beweis**. Meine Score-Eingaben sind Schätzungen.

## Kurzurteil
**Noch nicht validiert – und so, wie die Seite heute aussieht, würde ich keinen bezahlten Traffic darauf schicken.** Das Problem ist real und häufig, aber (1) die Zahlungsbereitschaft ist bei 2,99 $/Monat nicht tragfähig, (2) der Markt zeigt Konsolidierung und strenge KI-Therapie-Regeln, (3) die Seite enthält mehrere Aussagen, die rechtlich/glaubwürdigkeitsmäßig riskant sind.

## Score mit dem Radar-Schema (Schätzwerte)
| Faktor | Wert | Begründung |
|---|---|---|
| Wiederkehr | 0,9 | Angst/Grübeln ist massenhaft, ständig diskutiert |
| Affluence | 0,1 | Zielgruppe ist Endkunde „nicht krank genug für Therapie" – **nicht** die Wohlhabenden-Zielgruppe des Radars |
| Zahlungsbereitschaft | 0,4 | Therapie 200 $/h ist Anker; aber Wettbewerber verlangen ~50–100 $/Jahr und scheitern trotzdem |
| Wettbewerbslücke | 0,1 | sehr voll (siehe unten) |
| KI-Automatisierbar | 0,9 · Baubar 0,8 | |
| Reichweite | 0,6 | Hook-Test auf TikTok/Instagram plausibel (Hypothese, nicht belegt); Reddit-Angst-Subs verbieten meist Werbung |
| Timing | 0,2 | nichts „Neues" ermöglicht – eher regulatorischer Gegenwind |

Ergebnis: **14 Punkte bei 2,99 $** (Strafen: zu viele Zahler nötig, Affluence schwach), **29 Punkte bei 5,99 $+**, **56 Punkte** wenn man Affluence ausblendet (reine Endkunden-Sicht). Für den Radar ist das ein „nicht freigeben"; als eigenständiges Consumer-Projekt ein „nur mit Preis- und Rechtskorrektur testen".
Zahler für 5.000 $/Monat Gewinn (70 % Marge, Annahme): **2.389** bei 2,99 $ · **1.193** bei 5,99 $ · **716** bei 9,99 $.

## Marktbefunde (Quellen unten)
- **Youper** hat den Dienst zum 30.09.2026 eingestellt; **Woebot** hat die Consumer-App 06/2025 abgeschaltet (nur noch Enterprise); **Wysa** überlebt (Preise laut Blogs 10–20 $/Monat bzw. ~75–100 $/Jahr, unzuverlässig). Das ist ein Warnsignal für das Verbraucher-Modell, nicht für die Nachfrage nach dem Thema.
- Es existiert bereits eine App namens **„Bruno – AI Companion for Wellness"** im App Store (3-Tage-Test, 8,99 $ / 49,99 $ pro Jahr) → Namens-/Verwechslungsrisiko, Marken- und ASO-Check nötig.
- **Regulierung:** Illinois (Verbot KI-Therapie, bis 10.000 $ Strafe), Nevada (bis 15.000 $), Utah (Offenlegungspflicht + Safe Harbor); 2026 zusätzlich Colorado, Maine, Tennessee; Pennsylvania ging per Lizenzrecht gegen einen Chatbot vor. Geltungsbereich teils unklar (Illinois: Dienste, die „mentale Gesundheit verbessern"). Texte wie „exact protocol therapists use", „real CBT", „CBT coach" liegen nah an Therapie-Claims.
- **Retention:** Eine ältere Panel-Studie (2019, kostenlose Apps) fand 30-Tage-Retention im Median von ~3 %. Für Abo-Apps nicht direkt übertragbar, aber Retention ist das Kernrisiko; Lifetime-Preis 2,99 $ verschärft das.

## Probleme auf der Seite (faktisch, aus dem gelesenen Text)
1. **Datenschutz/AGB sind Platzhalter**, aber die Seite verspricht „end-to-end verschlüsselt, nicht mal wir können es lesen" und „nie zum KI-Training genutzt". Wenn ein KI-Modell serverseitig antwortet, ist „Ende-zu-Ende / wir können nicht lesen" fast sicher unzutreffend → irreführend, Gesundheitsdaten (DSGVO Art. 9) betroffen.
2. **Kein Impressum**, keine Firma/Adresse, keine Gründer, keine Social-Links, keine Testimonials → Vertrauens- und Rechtslücke (DE/EU: Impressumspflicht).
3. **Widersprüche:** „Free for life" vs. „6 Monate gratis, dann 2,99 $ für immer"; „Not a chatbot" vs. Chat-Coach.
4. **Unbelegte Aussagen:** „Navy SEALs", „2.000-Studien-Toolkit", „same CBT therapists charge $200/hr for", Knappheit „nur 1.000 Plätze"/„100 Mitglieder" (nicht prüfbar) → Irreführungsrisiko (UWG/FTC).
5. **Stale:** Countdown/Launch „15. September 2026" liegt in der Vergangenheit (heute 3. November).
6. Merch-Verlosung für Warteliste: Datenerhebung/Gewinnspielbedingungen fehlen.

## Empfohlener Test (7 Tage Exploration, danach 7 Tage Entscheid)
1. **Seite zuerst reparieren** (1 Tag): echte Datenschutz/AGB, Impressum, widersprüchliche/unbelegte Aussagen raus oder belegen, Launch-Datum korrigieren, „Coach, kein Therapeut"-Positionierung ohne Therapie-Claims, Krisenhinweise je Land, Geofencing/Hinweis für Staaten mit KI-Therapie-Verboten prüfen (Rechtsrat).
2. **Preis testen statt 2,99 $ Lifetime:** A/B 5,99 $ vs. 9,99 $/Monat bzw. 49 $/Jahr (Bazzly: ein höherer Einzelpreis erhöhte Umsatz). Zahlungsbereitschaft **echt** messen: erstattbare Vorbestellung (z. B. 9–15 € Anzahlung oder 29 $ Early-Bird-Jahr) über den neuen Stripe-Flow.
3. **Hook-Test (Minini):** 5 ehrliche Hooks/Tag über 5 Tage (Text/Kurzvideo „Konzept – Warteliste"), Messung: Views, Kommentare mit Kaufabsicht, Klicks auf die Warteliste; keine gefälschten Screens/Testimonials.
4. **Go/Kill** (Radar-Regeln): nach 7 Tagen < 100 Besucher bei halbem Budget → Kill; ≥ 100 Besucher und < 1,5 % Anmeldung ohne Vorbestellung → Kill; ≥ 30 bestätigte Anmeldungen **oder** ≥ 3 bezahlte Vorbestellungen → Go. Besser für B2C-Mental-Health: ≥ 3 % Anmeldung **und** ≥ 5 Vorbestellungen.
5. **Fokus-Alternative prüfen:** Das Thema in eine Zielgruppe mit Zahlungsbereitschaft drehen (z. B. Führungskräfte/Gründer mit Stress/Burnout-Prävention, Firmenkunden/EAP, Praxen als Co-Pilot für Therapeuten – „Zwischen den Sitzungen"). B2B-Preise (5–15 €/Sitz) und weniger Therapie-Regulierungsdruck als reines D2C.

## Was ich von dir brauche, um es wirklich zu validieren
Besucher, Anmeldungen, Quellen, Ausgaben und ob die App schon live ist (Zahlen in `POST /experiments/{id}/metrics` eintragen; sie zählen zusätzlich zu den neuen Landing-Metriken).

## Quellen
- [Best AI Therapy Apps 2026 – Choosing Therapy](https://www.choosingtherapy.com/best-ai-therapy-apps/)
- [Wysa vs Woebot 2026](https://ai-health-apps.com/compare/wysa-vs-woebot/)
- [Why Woebot Shut Down – ilty](https://ilty.co/blog/why-woebot-shut-down)
- [Best Woebot Alternatives 2026 (Youper-Shutdown-Hinweis)](https://ilty.co/best/woebot-alternatives-2026)
- [Bruno – AI Companion for Wellness (App Store)](https://apps.apple.com/ca/app/bruno/id6760506584)
- [State laws restricting AI mental health care – Qz](https://qz.com/state-laws-restricting-ai-mental-health-care-guide-072826)
- [Three more states ban AI chatbot therapy – LexisNexis](https://www.lexisnexis.com/community/amp-insights/112/three-more-states-ban-ai-chatbot-therapy)
- [New state laws regulating AI in mental healthcare – Baker Botts (Okt 2026)](https://www.bakerbotts.com/thought-leadership/publications/2026/october/new-state-laws-regulating-ai-use-for-mental-healthcare)
- [Illinois bans AI therapy – Gizmodo](https://gizmodo.com/illinois-bans-ai-from-providing-therapy-2000639042)
- [Retention bei Mental-Health-Apps – Baumel et al., JMIR 2019](https://pmc.ncbi.nlm.nih.gov/articles/PMC6785720)
