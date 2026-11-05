<!-- gruppe: workflow; reihenfolge: 5; seiten: vergleich; kurz: Läufe nach Datenqualität vergleichen und einen gültig setzen -->
# Den besten Lauf wählen

Pro Planet und Nacht zählt genau ein Lauf, der **gültige**. Wähle ihn nach der **Qualität der Daten**, nicht danach, welches O-C oder welche Tiefe am besten zur Literatur passt. Sonst misst du, was du erwartest.

1. Auf der Seite **Vergleichen** stehen oben die **Kennzahlen** aller Läufe. [Zeig mir die Tabelle](#zeige:kz)
2. Zuerst **Prüfungen**: Läufe mit rotem Ergebnis aussortieren.
3. Dann **OOT-RMS**: die Streuung außerhalb des Transits. Kleiner ist besser.
4. Dann **β**: das „rote Rauschen“. Nahe 1 ist gut, über 1,5 deutet auf Störungen.
5. Erst zum Schluss **O-C** und **Drift** ansehen, als Kontrolle.
6. Einen Lauf anklicken, das Ergebnisblatt ansehen, rechts **gültig setzen**.

> Unterschiede im OOT-RMS unter etwa 0,2 ‰ sind meist Zufall. Dann den Lauf mit den einfacheren Einstellungen nehmen.

Ist kein Lauf gut? Dann passt eines der Fehlerbilder: [O-C zu groß](#hilfe:oc-zu-gross), [Lichtkurve verrauscht](#hilfe:rauschen), [Löcher in den Daten](#hilfe:luecken).

Danach: [Auf ExoClock hochladen](#hilfe:exoclock-upload).

## Hintergrund

```formel
OOT-RMS = Standardabweichung(Fluss außerhalb des Transits − Modell),   in ‰
```

Das OOT-RMS ist ein Maß, das nicht von der Transittiefe abhängt; darum ist es als Auswahlkriterium „blind“ gegenüber dem Ergebnis. **So rechnet transit:** `numpy.std` auf die Residuen vor dem Ingress und nach dem Egress, mit 10 min Abstand (`[search] oot_margin_min`).
