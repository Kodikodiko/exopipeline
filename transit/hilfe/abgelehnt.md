<!-- gruppe: fehler; reihenfolge: 9; seiten: vergleich; kurz: Typische Gründe, warum ExoClock eine Messung zurückgibt -->
# ExoClock lehnt die Beobachtung ab

ExoClock prüft jede Einsendung. Häufige Gründe für eine Ablehnung und was du tun kannst:

| Grund | Was tun |
| --- | --- |
| O-C weit außerhalb | [O-C zu groß](#hilfe:oc-zu-gross) durchgehen, vor allem Tc-Profil und Einzeltest |
| Rp/R* passt nicht (Drift über 3 σ) | [Transit zu flach oder zu tief](#hilfe:tiefe) |
| starke Streuung am Ingress oder Egress | [Löcher](#hilfe:luecken), [Ausreißer](#hilfe:ausreisser), [Vergleichssterne](#hilfe:vergleichssterne-waehlen) |
| Transit nicht vollständig | ohne Baseline auf einer Seite ist die Messung schwer verwertbar |
| falsche Formularangaben | Time stamp „Exposure start“, Time format JD_UTC, Filter |

Der Reviewer geht oft so vor: Vergleichssterne einzeln ansehen, den schlechtesten weglassen, neu rechnen. Genau das macht [Weg 2 unter Vergleichssterne wählen](#hilfe:vergleichssterne-waehlen).

> Eine abgelehnte Nacht nur dann neu einreichen, wenn du einen klaren Fehler gefunden hast, nicht mit anders gewählten Sternen, bis es passt.
