<!-- gruppe: fehler; reihenfolge: 7; seiten: lauf; kurz: Ein Schritt steht lange oder der Lauf bricht ab -->
# Der Lauf hängt oder bricht ab

1. **Schritt Photometrie steht ohne Balken:** Die Pipeline fragt den Gaia-Katalog im Internet ab. Das kann einige Minuten dauern. Antwortet ein Server nicht, versucht sie automatisch andere (VizieR-Spiegel, ESA). In der Laufansicht kannst du die Quelle wechseln.
2. **Fehlermeldung „… fehlt, zuerst den vorherigen Schritt“:** Ein früherer Schritt ist nicht fertig geworden. Lauf neu starten; fertige Schritte werden übersprungen.
3. **„Light-Dateien verändert“:** Jemand hat die Original-Bilder geändert. Prüfen, dann neue Prüfsummen mit `transit inventory <Messordner>`.
4. **Kein Lebenszeichen mehr:** PC im Ruhezustand oder Fenster „Transit GUI“ geschlossen. Neu starten; der Lauf setzt beim ersten fehlenden Schritt fort.

Das vollständige Protokoll steht in `RESULT\<lauf>\run.log` (Link unter dem Live-Protokoll). [Zeig mir das Protokoll](#zeige:l-log)

Mehr im [Handbuch, Kapitel 10](handbuch#10-fortschritt-status-und-fortsetzen).
