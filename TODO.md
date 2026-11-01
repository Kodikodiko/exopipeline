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

## Später: Automatische Wolken-Erkennung
Geschätzter Aufwand: 1 Sitzung.
- Je Frame den Gesamtfluss der Vergleichssterne mit dem gleitenden Median vergleichen; Einbruch über einer Schwelle (z. B. `[fit] wolken_schwelle = 0.3` = 30 %) → Frame als „Wolke“ markieren.
- Markierte Frames im Ergebnisblatt farbig zeigen und im Bericht/`summary.md` als Zeitbereiche nennen (z. B. „Wolken 22:41–22:58 UT, 14 Frames“).
- Optional automatisch aus dem Fit nehmen (eigene Option, Standard aus), analog zu `ausreisser.json`.
- Anlass: KPS-1b (2026-06-05), dort mussten die Wolken-Frames von Hand entfernt werden.

## Später: ExoClock-Kommentar vervollständigen
Geschätzter Aufwand: ½ Sitzung.
- `transit kommentar` nennt Datenlücken bisher nur mit Dauer; Uhrzeit (UT) ergänzen.
- Entfernte Ausreißer (Anzahl, Sigma-Schwelle aus `ausreisser.json`) und Wolken-Frames erwähnen.
- Farbkamera-Hinweis (`BAYERPAT` im Header, Debayer/Binning) automatisch einfügen.
- 300-Zeichen-Grenze einhalten: Reihenfolge nach Wichtigkeit, Rest kürzen.

## Später: Stacken/Binning für kurze Belichtungen
Geschätzter Aufwand: 1–2 Sitzungen.
- Anlass: KELT-7b mit 2 s Belichtung, sehr viele Frames und viel Rauschen je Frame.
- Option `[photometry] stack_n = N`: je N aufeinanderfolgende Frames zeitlich zusammenfassen (Photometrie mitteln oder Frames nach Ausrichtung addieren); Zeitstempel = Mitte, Belichtung = Summe.
- Alternativ/zusätzlich 2×2-Software-Binning der Pixel (auch Voraussetzung für Farbkamera-Daten).
- Fehlerrechnung (Rauschmodell, OOT-RMS) und AIJ-Export auf die zusammengefassten Punkte anpassen.

## Später: Plausibilitäts-Warnungen
Geschätzter Aufwand: ½–1 Sitzung.
- Warnung in Konsole, GUI und Ergebnisblatt, wenn Ergebnisse unplausibel sind, z. B.:
  - Fehler von O−C über 10 min,
  - Tiefe (Rp/R*)² weicht stark von der Literatur ab (z. B. > 30 % oder > 3 σ),
  - Transitdauer deutlich anders als vorhergesagt, kaum Baseline vor/nach dem Transit.
- Schwellen in `[checks]` konfigurierbar; Warnungen auch im Logbuch vermerken.

## Später: Alter der Flats prüfen
Geschätzter Aufwand: ½ Sitzung.
- Beim Kalibrieren `DATE-OBS` des gewählten Master-Flats mit der Nacht der Lights vergleichen.
- Warnen, wenn älter als `[calib] flat_max_tage` (z. B. 30) – Staub und Kamerarotation ändern sich.
- Alter im Bericht/Ergebnisblatt nennen; gleiche Prüfung optional für Darks/Bias.

## Später: Automatische Regressionstests (HAT-P-42b)
Geschätzter Aufwand: 1–2 Sitzungen.
- Referenzdaten HAT-P-42b (reduziert, z. B. nur Ausschnitte um Ziel und Vergleichssterne) und erwartete Zahlen (Tc, O−C, Rp/R*, OOT-RMS) als Testfall ablegen; Rohdaten sind zu groß fürs Repo.
- `pytest`-Tests: komplette Kette `calibrate` … `fit` muss innerhalb kleiner Toleranzen die Referenz liefern; dazu schnelle Einzeltests (Modell, Zeitumrechnung, Ensemble-Wahl).
- Lauf per GitHub Actions bei jedem PR (Windows, später auch Linux).
- Dient auch als Abnahmetest für Linux-Version, englische Version und Stacken.

## Später: Live-Protokoll komplett scrollbar
Geschätzter Aufwand: ½ Sitzung.
- In der neuen GUI (`gui_neu.py`, Laufseite „Protokoll (live)“) soll der gesamte Verlauf des Laufs scrollbar sein, nicht nur die letzten Zeilen.
- Derzeit liefert `run_detail` in `gui.py` über `tail(…, n=14)` nur die letzten 14 Zeilen aus `gui_konsole.txt` bzw. `run.log`; das Feld `#l-log` zeigt nur diese.
- Umsetzung: ganzes Protokoll liefern (bei sehr langen Läufen ggf. inkrementell ab einer Zeilennummer nachladen statt jedes Mal komplett), `#l-log` mit fester Höhe und `overflow:auto`; automatisch nach unten mitscrollen nur, wenn man schon unten steht (vorhandene Logik in `gui_neu.py` beibehalten).
- Klassische GUI (`/klassisch`) unverändert lassen.

## Später: FITS bei Bedarf auch vom NAS lesen
Geschätzter Aufwand: ½ Sitzung.
- Schritte, die nachträglich einzelne Frames brauchen (z. B. das Feldbild im Ergebnisblatt, `feld.draw_page`), sollen die FITS auch finden, wenn die Messung archiviert ist und lokal gelöscht wurde (`transit archiv --loeschen`).
- Derzeit sucht `draw_page` nur in `SOLVED\` und `LIGHTS` des Messordners; fehlt die Datei dort, bricht es mit `StopIteration` ab.
- Umsetzung: gemeinsame Suchfunktion für Frames, die nacheinander lokal, dann den im Logbuch vermerkten Archivpfad und zuletzt `[paths] archiv_wurzel` prüft (wie `resolve(…, nas)` für Messordner). Nur die benötigte Datei lesen, nichts zurückkopieren.
- NAS nicht erreichbar → verständliche Meldung („NAS verbunden?“) statt Absturz; Ergebnisblatt notfalls ohne Feldbild erzeugen.
