# TODO – geplante Erweiterungen (nicht umgesetzt)

## Später: Linux-Version
Geschätzter Aufwand: 1–2 Sitzungen.
- Python-venv mit denselben Paketen wie unter Windows, dazu `python3-tk` (Ordnerdialog der GUI).
- Windows-Pfade (`C:\…`, `\\NAS\…`) in die Konfiguration verlagern; unter Linux die NAS per SMB/NFS mounten. Code auf `pathlib`/plattformneutrale Pfade prüfen (Backslashes in Texten, `os.path.normcase`, Laufwerksbuchstaben).
- Groß-/Kleinschreibung bei der Ordnererkennung ignorieren (`LIGHT`/`light`, `RESULT`/`result`) – Linux unterscheidet sie.
- Shell-Starter `transit` und `transit_gui` (`./transit …`) statt `transit.cmd` / `transit_gui.cmd`.
- Plate-Solver: ASTAP-Linux-Version, Pfad in `[paths] astap`; AstroImageJ-Startpfad für `transit aij --oeffnen`.
- Windows-Benachrichtigung (`--toast`) durch `notify-send` ersetzen oder abschalten.
- Parallelisierung prüfen (`spawn`/`fork`, Thread-Variablen, Kernzahl).
- Abnahmetest: HAT-P-42b muss identische Zahlen liefern (Tc, O−C, Rp/R*, OOT-RMS wie im Logbuch).

## Später: Englische Version
Geschätzter Aufwand: 2–3 Sitzungen (Handbuch allein etwa eine).
- Sprache wählbar in der Konfiguration, z. B. `[ui] sprache = "de"` / `"en"` (Standard `de`), dazu `--sprache` für einzelne Läufe; die GUI übernimmt die Einstellung.
- Texte zentral sammeln (z. B. `transit/texte.py` mit Wörterbuch je Sprache oder `gettext`), statt sie im Code zu verstreuen. Deutsche Texte bleiben die Vorlage, fehlende englische fallen auf Deutsch zurück.
- GUI (`gui.py`): Beschriftungen, Knöpfe, Hinweise, Fehlermeldungen und die eingebettete JavaScript-Seite.
- Logmeldungen und Fortschrittsanzeige (Konsole, `run.log`, `status.json`), CLI-Hilfe (`hilfe.py`, `--help`-Texte der Unterbefehle).
- Ergebnisblatt (`ergebnisblatt.py`: Achsen, Legenden, Tabellen, Fußzeile) und `summary.md` (`report.py`); Zahlenformat einheitlich mit Dezimalpunkt.
- `HANDBUCH.md` als `HANDBOOK.md` übersetzen, `README.md` mit englischem Abschnitt; Kommentare in `config.example.toml` zweisprachig oder eigene `config.example.en.toml`.
- Nicht übersetzen: Ordner- und Dateinamen (`RESULT`, `LIGHTS`, `ergebnisblatt.png`), Konfigurationsschlüssel, Spaltennamen in Logbuch und AIJ-Export – sonst brechen bestehende Läufe und Auswertungen.
- Abnahmetest: HAT-P-42b mit `sprache = "en"` liefert dieselben Zahlen wie auf Deutsch; Ergebnisblatt und GUI auf übersehene deutsche Texte durchsehen.
