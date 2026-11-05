<!-- gruppe: workflow; reihenfolge: 8; seiten: logbuch; kurz: Messordner sicher aufs NAS verschieben -->
# Messung archivieren und Logbuch

Das **Logbuch** listet alle ausgewerteten Nächte mit Status, O-C und Upload-Datei. Das O-C-Diagramm im Ergebnisblatt liest nur das Logbuch, darum bleiben ältere Messungen sichtbar, auch wenn ihre Bilder archiviert sind.

Archivieren geht auf der Kommandozeile:

1. `transit archiv <Messordner> --ziel <NAS-Pfad> --probe` zeigt, was kopiert würde.
2. `transit archiv <Messordner> --ziel <NAS-Pfad>` kopiert und prüft jede Datei mit einer Prüfsumme (SHA-256).
3. Mit `--loeschen` wird lokal gelöscht, aber nur, wenn alle Prüfsummen stimmen.

Lokal bleibt der Ordner `_pipeline` mit Programm, Cache und `logbuch.csv`. Mehr im [Handbuch, Kapitel 13](handbuch#13-archivieren-messordner-aufs-nas).
