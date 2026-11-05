<!-- gruppe: fehler; reihenfolge: 5; seiten: vergleich; kurz: Rp/R* oder Tiefe weicht von der Literatur ab (Drift) -->
# Der Transit ist zu flach oder zu tief

Die Tiefe des Transits gibt das Größenverhältnis von Planet zu Stern (Rp/R*). ExoClock vergleicht es mit dem Literaturwert; die Abweichung heißt **Drift**. Ab 3 σ (rot) lehnt ExoClock die Messung meist ab.

Mögliche Ursachen, häufigste zuerst:

1. **Ein Vergleichsstern verfälscht.** Spalte **Einzeltest** im Reiter Vergleichssterne. Siehe [Vergleichssterne wählen](#hilfe:vergleichssterne-waehlen).
2. **Nachbarstern in der Apertur.** Sein Licht „verdünnt“ den Transit, er wird flacher. Seite 2 des Ergebnisblatts zeigt Nachbarn.
3. **Filter.** Durch Randverdunkelung ist der Transit im Blauen etwas tiefer als im Roten. Mit Luminance-Filter kann die Tiefe leicht von einem R-Literaturwert abweichen.
4. **Quadratisches Detrending.** Es kann einen Teil der Tiefe als „Airmass-Krümmung“ deuten. Mit linearem Detrending vergleichen.
5. **Kurze Baseline oder Meridian-Flip.** Ohne genug Vergleichszeit ist die Tiefe schlecht bestimmt.
6. **Sättigung oder Nichtlinearität** des Zielsterns.

Das Ergebnisblatt prüft diese Punkte automatisch im Kasten **Plausibilität der Tiefe**.

> Wähle den Lauf nicht danach aus, welche Tiefe am besten zur Literatur passt. Das macht das Ergebnis zirkulär.

## Hintergrund

```formel
Tiefe ≈ (Rp / R*)²,     Drift = (Rp/R*_gemessen − Rp/R*_Literatur) / √(σ² + σ_Lit²)
```

Die genaue Tiefe hängt zusätzlich von der Randverdunkelung ab (Koeffizienten u1, u2) und von der Bahngeometrie (a/R*, Inklination), die für ExoClock aus der Literatur festgehalten wird. **So rechnet transit:** eigenes Transitmodell in `transit/model.py` (quadratische Randverdunkelung, gleichwertig zu Mandel & Agol 2002, nur `numpy`), Literaturwerte aus ExoClock und dem NASA Exoplanet Archive.
