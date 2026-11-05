<!-- gruppe: workflow; reihenfolge: 1; seiten: planen; kurz: Welcher Transit lohnt sich heute Nacht? -->
# Eine Beobachtungsnacht planen

Die Seite **Planen** sucht aus der ExoClock-Datenbank alle Transits der nächsten Nächte, die du mit deinem Teleskop von deinem Standort aus ganz sehen kannst, und sortiert sie nach Nutzen.

1. Oben **Planen** öffnen. [Zeig mir das Feld](#zeige:pl_n)
2. **Nächte** und **pro Nacht** wählen, z. B. 3 Nächte mit je 10 Vorschlägen.
3. **Wetter** an lassen, damit bewölkte Nächte nach hinten rutschen.
4. **Berechnen** drücken. Nach einigen Sekunden erscheint pro Nacht eine Tabelle.
5. Von oben nach unten lesen: **Score** (Gesamtnutzen), **Prio** (wie dringend ExoClock die Messung braucht), **SNR** (wie deutlich der Transit mit deinem Gerät zu sehen sein wird), **Beobachten** (von wann bis wann aufnehmen) und **Hinweise**.
6. Einen Vorschlag mit grünem Wetter, SNR deutlich über 3 und ohne rote Hinweise wählen.

> Ein guter Transit liegt in der Mitte der Nacht, steht hoch (X max unter 2) und hat vor und nach dem Transit je etwa eine Stunde „Baseline“, also Messzeit ohne Transit.

## Worauf die Vorschläge achten

- **Ganzer Transit in der Dunkelheit**, mit Unsicherheit der Vorhersage, über der Mindesthöhe.
- **Baseline** vor und nach dem Transit: Ohne sie lässt sich die Tiefe nicht messen, weil der Vergleich fehlt.
- **Meridian-Flip**: Liegt er im Transit, entsteht leicht eine Stufe in der Lichtkurve. Siehe [Stufe in der Lichtkurve](#hilfe:stufe).
- **Mond**: Ein heller Mond nahe am Ziel hebt den Himmelshintergrund und das Rauschen.
- **Tiefe gegen Rauschen**: Flache Transits an schwachen Sternen sind mit kleinen Teleskopen nicht zu sehen und werden weggelassen.

Danach: [Aufnahme: worauf achten](#hilfe:aufnehmen).

## Hintergrund

Das erwartete Signal-Rausch-Verhältnis vergleicht die Transittiefe mit dem Rauschen eines 10-Minuten-Mittels.

```formel
SNR = Tiefe / σ_10min,   σ² = σ_Photonen² + σ_Himmel² + σ_Szintillation² + Rauschboden²
```

Die Szintillation (Flackern durch Luftunruhe) folgt der Näherung nach Young (1967, hier mal 1,5): Sie wächst mit der Airmass hoch 1,75 und fällt mit dem Teleskopdurchmesser hoch −2/3, darum sind tiefe Ziele für kleine Teleskope besonders verrauscht.

**So rechnet transit:** `transit/plan.py`. Sonnen-, Mond- und Zielhöhe mit `astropy.coordinates` (`AltAz`, `get_body`), Zeiten mit `astropy.time`, Ephemeriden aus dem ExoClock-Cache, Wetter von Open-Meteo über `urllib`. Score = Priorität × Genauigkeit × (1 − Bewölkung) × Abzüge.
