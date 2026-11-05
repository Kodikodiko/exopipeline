<!-- gruppe: fehler; reihenfolge: 4; seiten: vergleich; kurz: OOT-RMS hoch oder β deutlich über 1 -->
# Die Lichtkurve ist verrauscht

Zwei Zahlen beschreiben das Rauschen: **OOT-RMS** (wie stark die Punkte außerhalb des Transits streuen) und **β** (ob die Streuung zufällig ist, β nahe 1, oder in Wellen kommt, β deutlich über 1). Wellen sind schlimmer als zufällige Streuung, weil sie wie ein Transit aussehen können.

Prüfe der Reihe nach:

1. **Wolken oder Dunst?** In den Residuen sieht man dann Bereiche mit starker Streuung. Gegen kurze Störungen hilft [Sigma-Clipping](#hilfe:ausreisser).
2. **Farbkamera?** Bei Bayer-Bildern müssen 2×2-Superpixel gemessen werden. Unter Erweitert, Kamera & Gaia: Farbkamera „automatisch“ oder „ja“.
3. **Apertur zu klein oder zu groß?** Bei wechselndem Seeing hilft die mitwachsende Apertur (Erweitert, Apertur, Modus „beides“).
4. **Schlechte Vergleichssterne?** Im Reiter Vergleichssterne die Spalten **Ruhe** und **Einzeltest** prüfen. Siehe [Vergleichssterne wählen](#hilfe:vergleichssterne-waehlen).
5. **Tiefer Stand am Anfang oder Ende?** Dort ist die Luft unruhiger. Eine Airmass-Grenze (z. B. 2,0) schneidet diese Punkte ab; die Baseline sollte dabei nicht unter 30 min fallen.
6. **Kalibrierung?** Den Lauf mit der zweiten Kalibrierung vergleichen. Ein schlechtes Flat erzeugt Wellen, wenn der Stern wandert.

Wie viel Rauschen normal ist, hängt von Stern und Teleskop ab. Vergleiche mit deinen eigenen Nächten im Logbuch.

## Hintergrund

```formel
β = Median über n von [ σ_n / ( σ_1 / √n · √(M / (M − 1)) ) ],   n = 5 … 20 Punkte pro Mittel
```

Bei rein zufälligem Rauschen sinkt die Streuung σ_n von Mittelwerten aus n Punkten mit 1/√n; bleibt sie größer, sind die Fehler zeitlich korreliert („rotes Rauschen“, Winn et al. 2008). Die Fehlerbalken werden mit β vergrößert. **So rechnet transit:** `beta_factor` in `transit/analysis.py` mit `numpy`; Photometrie mit `photutils` (`CircularAperture`, Himmelsring), Hintergrund mit `astropy.stats.sigma_clipped_stats`.
