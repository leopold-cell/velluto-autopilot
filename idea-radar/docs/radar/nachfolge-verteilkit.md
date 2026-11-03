# Verteilkit: Gesprächspartner für das KI-Interview gewinnen (nur kostenlose Kanäle)

Stand 2026-11-03. Das KI-Interview (`/i/<slug>`) führt die Gespräche, wertet sie aus und liefert den Go/Kill-Bericht (`GET /experiments/{id}/interview-report`). Offen bleibt: **Menschen auf den Link bringen.** Ohne Werbebudget lässt sich das nicht vollständig automatisieren; unten steht der kleinste manuelle Aufwand (einmalig ca. 2–3 Stunden, danach nur Freigaben).

**Realistische Erwartung (Annahme, nicht belegt):** Über kostenlose Kanäle sind 10 Inhaber-Interviews in 2–3 Wochen optimistisch; plane 4–6 Wochen oder rechne mit weniger. Ergebnisse unter 10 Interviews sind Hinweise, kein Beweis.

## Was nicht gemacht wird
- Keine Bots/Remote-Desktop-Zugriffe auf dein LinkedIn, keine automatischen Nachrichten oder Kontaktanfragen (Plattformbedingungen, Sperrrisiko, Sicherheitsrisiko für dein Konto).
- Kein E-Mail-Kaltversand (UWG § 7). Keine Fake-Accounts, keine getarnte Werbung.

## Kanäle (nach Wirkung)
1. **Partner-Rundmails (größter Hebel):** IHK/HWK-Nachfolgeberater, Steuerberater, Banken schicken die Einladung an *ihre* Kontakte (deren Beziehung, deren Einwilligung). Aufwand für dich: 5–10 persönliche Anfragen einmalig (Nachrichten B, C, D aus `nachfolge-checkliste.txt`) + Einladungstext unten.
2. **Eigene Beiträge** auf deinem LinkedIn (und X): 5 Entwürfe unten. Du kannst sie mit LinkedIns eigener Planungsfunktion terminieren (das ist erlaubt). Kein Anschreiben Einzelner.
3. **Podcast/Multiplikatoren:** Nachrichten D (z. B. Nachfolgeschmiede) mit Bitte um Erwähnung des Links oder einen Gastplatz.
4. **Öffentliche Antworten:** Wo Inhaber öffentlich Fragen zu Nachfolge stellen (LinkedIn-Kommentare, Foren), hilfreich antworten und den Link nur anbieten, wenn Regeln es erlauben.
5. **Anreiz ohne Geld:** Teilnehmer erhalten nach 20 Interviews einen kurzen anonymisierten Branchenbericht („Woran Nachfolgen vor dem Verkauf scheitern“) plus die Datenraum-Checkliste. Das nur versprechen, wenn wir es wirklich liefern.

## Einladungstext für Partner (zum Weiterleiten)
Betreff: Kurzes anonymes Interview zur Übergabe-Vorbereitung (15 Min., KI-geführt)

> Wir untersuchen, wo Inhaber bei der Vorbereitung von Übergabe oder Verkauf Hilfe vermissen (Unterlagen, Datenraum, Abhängigkeit vom Inhaber). Dafür gibt es ein 15-minütiges, anonymes Interview, das **eine KI** per Text führt; es wird kein Name abgefragt, die Antworten werden 90 Tage gespeichert und ausgewertet. Als Dank erhalten Teilnehmer den Branchenbericht und die Datenraum-Checkliste. Keine Verkaufsabsicht. Link: [LINK]/i/[slug]

## Beitragsentwürfe (eigenes Profil; ehrlich, kein Pitch; [LINK] ersetzen)
1. „Wer einen Betrieb verkaufen oder übergeben will, hört oft: Fangen Sie 2 Jahre früher an. Aber womit? Ich recherchiere gerade, woran Inhaber bei der Vorbereitung hängenbleiben (Unterlagen, Datenraum, Inhaberabhängigkeit). Wenn Sie 15 Minuten haben: anonymes, KI-geführtes Interview, Teilnehmer bekommen die Ergebnisse. [LINK]“
2. „Eine Frage an Inhaber 55+: Wie viele Wochen würde es dauern, alle Unterlagen für einen Käufer zusammenzustellen? Ich sammle echte Erfahrungen für eine Auswertung (anonym, 15 Min.). [LINK]“
3. „Berater und Steuerberater: In welchem Zustand kommen Mandanten bei der Nachfolge zu Ihnen? Ich möchte die typischen Lücken verstehen und teile die Ergebnisse gern. 15 Min., KI-geführt, anonym. [LINK]“
4. „Drei Dinge, die Käufer im Datenraum sofort vermissen (Erfahrungswerte aus Beratersicht, ungeprüft): aktuelle Verträge, saubere Kundenübersicht, Dokumentation von Prozessen. Was fehlt bei Ihnen? Umfrage/Interview: [LINK]“
5. „Zwischenstand meiner Recherche zur Nachfolge-Vorbereitung: [Ergebnis nach den ersten Interviews, nur anonymisiert]. Wer noch mitmachen möchte: [LINK]“

## So startest du (1x)
1. Backend deployen (siehe README), `LEGAL_*` und `ANTHROPIC_API_KEY` setzen.
2. Landingpage anlegen: `POST /experiments/{id}/landing`, danach `POST /experiments/{id}/interview` mit den Nachfolge-Fragen (aus `nachfolge-interviews.md`).
3. 5–10 Partneranfragen senden, Beiträge terminieren.
4. Bericht ansehen: `GET /experiments/{id}/interview-report`. Entscheidungsregeln stehen in `interviews.py::scorecard`.
