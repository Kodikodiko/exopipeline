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
