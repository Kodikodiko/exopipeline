<!-- gruppe: workflow; reihenfolge: 6; seiten: vergleich, auswerten; kurz: Störende Sterne ausschließen oder das Ensemble selbst festlegen -->
# Vergleichssterne ausschließen oder von Hand wählen

Der Zielstern wird immer **relativ** zu mehreren Vergleichssternen gemessen, dem **Ensemble**. So fallen Wolkendunst und Airmass heraus, die alle Sterne gleich treffen. Ein schlechter Vergleichsstern (veränderlich, Doppelstern, Nachbar in der Apertur) verbiegt dagegen die ganze Lichtkurve.

Normalerweise sucht die Pipeline das Ensemble selbst. Es gibt zwei Wege, einzugreifen.

## Weg 1: Sterne für den nächsten Lauf ausschließen

1. Auf **Auswerten** im Kasten Neuer Lauf **Erweitert bearbeiten…** öffnen. [Zeig mir den Knopf](#zeige:erwbtn)
2. Gruppe **Vergleichssterne**: unten steht die Liste aller Kandidaten.
3. In der Spalte **an** den Haken bei störenden Sternen entfernen. Verdächtige Sterne sind schon abgewählt.
4. **Übernehmen** und den Lauf starten. Die Pipeline sucht das beste Ensemble nur unter den Sternen mit Haken.

## Weg 2: Das Ensemble von Hand festlegen

1. Auf **Vergleichen** in den Kennzahlen einen Lauf anklicken.
2. Im Ergebnisblatt den Reiter **Vergleichssterne** öffnen.
3. In der Spalte **wählen** die gewünschten Sterne anhaken. Vorbelegt ist das Ensemble des Laufs.
4. **Vorschau berechnen** (Sekunden): vergleicht deine Auswahl mit dem Ensemble des Laufs.
5. Zuerst OOT-RMS und β vergleichen, dann O-C.
6. **Als neuen Lauf rechnen …** startet einen vollständigen Lauf mit genau diesen Sternen (Name endet auf `_hand`). Der alte Lauf bleibt.

## Gute und schlechte Gründe zum Abwählen

| Gut | Schlecht |
| --- | --- |
| **Ruhe** gelb oder rot: der Stern schwankt selbst | Sterne tauschen, bis O-C oder Tiefe zur Literatur passt |
| **Transitfenster** rot: er ändert sich genau während des Transits | Einen Stern abwählen, nur weil er dunkler ist |
| **Einzeltest** auffällig: allein gibt er eine ganz andere Tiefe | |
| **RUWE** über 1,4: vermutlich Doppelstern | |
| **Gaia** VARIABLE: bekannter Veränderlicher | |

Die Wahl wird im Ergebnisblatt und im ExoClock-Kommentar vermerkt („selected manually“).

## Hintergrund

```formel
F_rel(t) = F_Ziel(t) / Σ_i F_i(t)
```

Die Summe über viele Sterne mittelt deren Photonenrauschen und gemeinsame Störungen (Durchsicht, Extinktion) heraus. **Ruhe** ist die Streuung der 10-Minuten-Mittel eines Sterns gegen alle anderen, geteilt durch den Median aller Sterne. Der **Einzeltest** rechnet den Transit-Fit mit nur diesem einen Stern und vergleicht das Rp/R* mit dem Median. **So rechnet transit:** Gaia-Kandidaten über `astroquery` (VizieR oder ESA-Archiv), Veränderliche aus AAVSO VSX, Auswahl in `transit/analysis.py` (gierige Vor- und Rückwärtssuche nach OOT-RMS).
