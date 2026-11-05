<!-- gruppe: fehler; reihenfolge: 1; seiten: vergleich; kurz: Die gemessene Transitmitte weicht stark von der Vorhersage ab -->
# Mein O-C ist zu groß

**O-C** heißt „beobachtet minus berechnet“: um wie viele Minuten der Transit früher (negativ) oder später (positiv) kam als vorhergesagt. Ein großes O-C ist nicht automatisch ein Fehler. Es kann genau die Entdeckung sein, für die ExoClock Messungen sammelt. Gehe diese Fragen der Reihe nach durch.

1. **Ist das O-C größer als sein Fehler?** Ein O-C von 4 min mit Fehler ±3 min ist unauffällig. Erst ab etwa dem Dreifachen des Fehlers lohnt die Suche. Im O-C-Diagramm des Ergebnisblatts zeigt der graue Streifen, wie unsicher schon die Vorhersage ist.
2. **Ist Tc eindeutig?** Im Ergebnisblatt den Reiter **Tc eindeutig?** öffnen. Gibt es ein zweites Tal oder ist die Ampel gelb oder rot, könnte die Transitmitte auch woanders liegen. Ursache sind fast immer Lücken oder Wolken am Ingress oder Egress: weiter mit [Löcher in den Daten](#hilfe:luecken) und [Ausreißer](#hilfe:ausreisser).
3. **Stört ein Vergleichsstern?** Reiter **Vergleichssterne**, Spalte **Einzeltest**: Ist ein Stern des Ensembles gelb oder rot, gibt er allein ein ganz anderes Ergebnis. Weiter mit [Vergleichssterne wählen](#hilfe:vergleichssterne-waehlen).
4. **Liegt ein Meridian-Flip nahe am Ingress oder Egress?** Eine Stufe dort verschiebt die Kante und damit Tc. Weiter mit [Stufe in der Lichtkurve](#hilfe:stufe).
5. **Fehlt der Anfang oder das Ende des Transits?** Ohne Ingress oder Egress hängt Tc stark davon ab, wie die Airmass herausgerechnet wird. Ein solches Ergebnis ist unsicher und sollte so im Kommentar stehen.
6. **Stimmt die Uhr?** Die Zeit stammt aus DATE-OBS, also von der PC-Uhr während der Aufnahme. Geht sie eine Minute falsch, ist das O-C um eine Minute falsch. Die PC-Uhr sollte mit einem Zeitserver abgeglichen sein.
7. **Zeigen mehrere Nächte dasselbe?** Haben auch frühere Messungen dasselbe Vorzeichen, ist vermutlich die Vorhersage veraltet. Dann ist dein Ergebnis richtig und wertvoll. Nicht „wegkorrigieren“.

> Nicht so lange Einstellungen oder Sterne ändern, bis das O-C klein ist. Wähle den Lauf nach der Datenqualität (siehe [Den besten Lauf wählen](#hilfe:bester-lauf)).

## Hintergrund

```formel
O-C = Tc_gemessen − (T0 + E · P),     σ_Vorhersage = √(σ_T0² + E² · σ_P²)
```

T0 ist eine Referenz-Transitmitte, P die Periode und E die Zahl der Umläufe seither. Weil der Fehler der Periode mit E multipliziert wird, werden Vorhersagen mit den Jahren unsicherer; genau das korrigiert ExoClock mit neuen Messungen.

```formel
Δχ²(Tc) / β²   im Raster ±60 min, Schritt 1 min
```

Das Tc-Profil hält Tc fest, fittet den Rest neu und trägt die Güte auf. Ein zweites Tal, das weniger als 4 schlechter ist (`[fit] tc_zweites_tal`), heißt: Die Daten lassen zwei Lösungen zu. **So rechnet transit:** `transit/analysis.py` (`tc_profile`, `scipy.optimize.least_squares`); Tc und Fehler aus einer Metropolis-MCMC mit mehreren Ketten (16. und 84. Perzentil), Konvergenz per Gelman-Rubin R-hat; Zeiten in BJD_TDB mit `astropy.time`.
