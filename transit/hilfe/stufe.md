<!-- gruppe: fehler; reihenfolge: 6; seiten: vergleich; kurz: Plötzlicher Sprung im Fluss, meist durch den Meridian-Flip -->
# Stufe in der Lichtkurve (Meridian-Flip)

Beim **Meridian-Flip** dreht die Montierung das Teleskop auf die andere Seite. Danach liegt das Sternfeld um 180° gedreht auf dem Sensor, und jeder Stern fällt auf andere Pixel. Kleine Reste im Flat ergeben dann einen Sprung im relativen Fluss, typisch einige Promille.

Die Pipeline misst diesen Sprung an allen Vergleichssternen und rechnet ihn heraus.

1. Unter **Erweitert**, Fit & Ausreißer, **Meridian-Flip** auf Standard („Prior aus Vergleichssternen“) lassen.
2. Liegt der Flip **im Transit**, ist er schwer vom Transit zu trennen. Dann warnt schon die Inventur. Das Ergebnis vorsichtig bewerten.
3. Bei auffälligem Sprung hilft das **Symmetrie-Gewicht** 1: Es bevorzugt Vergleichssterne rund um das Ziel, deren Flat-Fehler sich ausgleichen.
4. Für künftige Nächte: Flip vor die Baseline legen oder über den Meridian hinaus nachführen. Siehe [Eine Beobachtungsnacht planen](#hilfe:planen).

## Hintergrund

```formel
F(t) = Transit(t) · (c0 + c1 · X(t) + s · [t > t_Flip])
```

X ist die Airmass, s die Stufe. Beim Prior wird s aus den Vergleichssternen in einer Ebene über die Bildposition vorhergesagt und als Gauß-Prior in den Fit gegeben; „frei“ fittet s ohne Vorwissen, was im Transit mit der Tiefe verwechselt werden kann. **So rechnet transit:** `transit/analysis.py`, Bildseite aus dem FITS-Schlüssel PIERSIDE, Fit mit `scipy.optimize.least_squares`.
