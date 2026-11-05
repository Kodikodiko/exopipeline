<!-- gruppe: fehler; reihenfolge: 2; seiten: vergleich, lauf; kurz: In der Lichtkurve fehlen Abschnitte -->
# Löcher in den Daten

Eine Lücke in der Lichtkurve heißt: Für diese Zeit gibt es keine brauchbaren Messpunkte. Wie schlimm das ist, hängt davon ab, **wo** die Lücke liegt.

| Lücke liegt … | Folge |
| --- | --- |
| in der Baseline vor oder nach dem Transit | meist harmlos, solange auf beiden Seiten noch etwa 30 min übrig sind |
| am Ingress oder Egress | gefährlich: Die Kanten bestimmen Tc. O-C wird unsicher, eventuell zweites Tal im Tc-Profil |
| in der Transitmitte | die Tiefe wird unsicherer, Tc kaum |

## Woher Lücken kommen

1. **Keine Bilder:** Wolken, Meridian-Flip mit Pause, Autofokus, Absturz der Aufnahmesoftware. Im Protokoll der Aufnahme nachsehen.
2. **Bilder verworfen wegen Sättigung:** Liegt der Zielstern oder ein Vergleichsstern über dem Sättigungswert, fällt das ganze Bild weg. Häufig bei sehr gutem Seeing (schmale, hohe Sterne). Das Ergebnisblatt nennt die Zahl.
3. **Stern nicht messbar:** Ein Stern ist aus dem Bild gewandert oder von Wolken verdeckt.
4. **Airmass-Grenze:** Ist unter Erweitert eine Airmass-Grenze gesetzt, fallen tiefe Randpunkte weg.
5. **Ausreißer entfernt:** Mit „Ausreißer entfernen“ fallen einzelne Bilder weg. Siehe [Ausreißer und Sigma-Clipping](#hilfe:ausreisser).

## Was tun

- Lücke in der Baseline: nichts tun.
- Lücke am Ingress oder Egress: Reiter **Tc eindeutig?** prüfen. Ist die Ampel grün, ist das Ergebnis brauchbar. Sonst im ExoClock-Kommentar erwähnen, z. B. „gap during egress due to clouds“.
- Viele Bilder wegen Sättigung verworfen: den betroffenen Vergleichsstern ausschließen (er sättigt), oder künftig kürzer belichten.
- Die Upload-Datei enthält nur die verwendeten Punkte. Die Zahl steht im Formular unter **Punkte**.

## Hintergrund

Tc wird vor allem von den steilen Kanten bestimmt. Grob gilt für den Fehler der Transitmitte (Carter et al. 2008):

```formel
σ_Tc ≈ (σ / Tiefe) · √(τ · Δt / 2)
```

σ ist das Rauschen eines Punkts, τ die Dauer von Ingress bzw. Egress und Δt der Abstand der Bilder. Fehlen Punkte genau in τ, fehlt der Teil der Daten, der Tc trägt. **So rechnet transit:** Bildauswahl in `transit/analysis.py` (`Night`): Sättigung über `[camera] saturation_adu`, nicht endliche Flüsse (`numpy.isfinite`), `[search] airmass_max`, `[search] exclude_frames`.
