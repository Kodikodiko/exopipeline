<!-- gruppe: workflow; reihenfolge: 4; seiten: auswerten, lauf; kurz: Lauf starten, Fortschritt lesen, was jeder Schritt tut -->
# Einen Lauf starten und verfolgen

Ein **Lauf** ist eine vollständige Auswertung einer Messung mit bestimmten Einstellungen. Du kannst beliebig viele Läufe einer Nacht rechnen und am Ende den besten auswählen.

1. Messung links wählen (siehe [Daten laden](#hilfe:daten-laden)).
2. Im Kasten **Neuer Lauf** den **Planeten** prüfen. [Zeig mir das Feld](#zeige:f_planet)
3. **Filter** prüfen und **Kalibrierung** wählen; Standard ist „Bias + Flat“.
4. Den Haken für eine zweite Kalibrierung an lassen, dann kannst du später vergleichen.
5. **Erweitert** beim ersten Lauf nicht ändern.
6. **Lauf starten**. Die Seite wechselt zur Laufansicht. [Zeig mir den Knopf](#zeige:startbtn)

## Was in einem Lauf passiert

| Schritt | Was passiert | Dauer |
| --- | --- | --- |
| Inventur | FITS-Header lesen, Prüfsummen der Lights, Vorhersage von ExoClock holen, Planungswarnungen | Sekunden |
| Kalibrieren | passende Master suchen | Sekunden |
| Photometrie | Gaia-Sterne im Feld suchen, Helligkeit aller Kandidaten in allen Bildern messen | Minuten |
| Vergleichssterne | variable Sterne aussortieren, das ruhigste Ensemble suchen | Minuten |
| Fit (MCMC) | Transitmodell anpassen, Fehler bestimmen, Prüfungen | Minuten |
| Export | ExoClock-Datei und Formularwerte schreiben | Sekunden |
| Ergebnisblatt | Grafiken, Vergleich mit der Literatur | Sekunden |

Die Seite kann geschlossen werden, der Lauf rechnet weiter. Bleibt ein Schritt lange stehen, siehe [Lauf hängt oder bricht ab](#hilfe:lauf-haengt).

Danach: [Den besten Lauf wählen](#hilfe:bester-lauf).
