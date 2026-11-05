<!-- gruppe: fehler; reihenfolge: 3; seiten: vergleich, auswerten; kurz: Einzelne Punkte springen weit weg: Sigma-Clipping -->
# Ausreißer und Sigma-Clipping

**Ausreißer** sind einzelne Messpunkte, die weit neben allen anderen liegen: ein Flugzeug, ein Windstoß, ein Wolkenfetzen, ein Satellit in der Apertur. Wenige Ausreißer können den Fit, vor allem Tc, deutlich verschieben.

**Sigma-Clipping** entfernt solche Punkte automatisch: Jeder Punkt, der weiter als eine Schwelle (in σ) vom Transit-Fit abweicht, fliegt raus; dann wird neu gefittet, bis nichts mehr herausfällt.

1. **Erweitert bearbeiten…** öffnen, Gruppe **Fit & Ausreißer**. [Zeig mir den Knopf](#zeige:erwbtn)
2. **Ausreißer entfernen** wählen: „wenige > 4 σ“ entfernt nur grobe Ausreißer, „normal > 3 σ“ ist der übliche Wert, „viele > 2,5 σ“ ist streng.
3. Lauf starten und mit dem Lauf ohne Clipping vergleichen.
4. In den Kennzahlen zeigt die Spalte **Ausreißer**, wie viele Punkte entfernt wurden.

## Woran du siehst, ob es zu viel ist

- Mehr als etwa 5 % der Punkte entfernt: Dann ist das kein Ausreißer-Problem, sondern die ganze Nacht ist unruhig (Wolken, Seeing). Siehe [Lichtkurve verrauscht](#hilfe:rauschen).
- Die entfernten Punkte liegen alle am Ingress oder Egress: Vorsicht, dann formt das Clipping die Kante mit. Ergebnis mit und ohne Clipping vergleichen.
- Das O-C ändert sich um mehr als seinen Fehler: Das Ergebnis hängt an wenigen Punkten.

Die entfernten Bilder stehen in `ausreisser.json` und im ExoClock-Kommentar. Die Upload-Datei enthält sie nicht.

> Clipping nur, um ein schöneres O-C zu bekommen, ist keine gute Idee. Clipping ist für einzelne, klar erkennbare Störungen gedacht.

## Hintergrund

```formel
σ_robust = 1,4826 · Median(|r_i − Median(r)|),     Punkt i raus, wenn |r_i − Median(r)| > k · σ_robust
```

r sind die Residuen (Messung minus Modell). Der Median der absoluten Abweichungen (MAD) wird von Ausreißern kaum beeinflusst; der Faktor 1,4826 macht sie bei normalverteiltem Rauschen gleich der Standardabweichung. **So rechnet transit:** `clip_outliers` in `transit/cli.py` mit `numpy.median`, bis zu 5 Runden, Fit mit `scipy.optimize.least_squares`. Für den Himmelshintergrund nutzt die Photometrie dasselbe Prinzip über `astropy.stats.sigma_clipped_stats`.
