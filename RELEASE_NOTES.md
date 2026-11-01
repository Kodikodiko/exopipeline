# Release Notes

## v1.1 (Entwurf, 2026-11-01)

Änderungen seit **ExoPipeline v1.0** (Tag `release`, 30.10.2026, enthält bereits `transit plan` aus PR #1).
Umfasst PR #2 bis #17.

### Auswertung und Fit

- **Farbkameras (Bayer/OSC):** Bilder mit `BAYERPAT` im Header werden nach der Kalibrierung zu 2×2-Superpixeln zusammengefasst (`[camera] farbkamera = auto|ja|nein`). KPS-1b (ATR2600C): OOT-RMS 4,4 statt 11,5 ppt, O−C −0,4 ± 2,2 min statt +41 ± 181 min. Handbuch Kapitel 21. (#3)
- **Ausreißer entfernen:** iteratives Sigma-Clipping auf den Fit-Residuen, `[fit] ausreisser_sigma` (0 = aus), in der GUI unter Erweitert als 4 / 3 / 2,5 σ. Entfernte Frames stehen in `ausreisser.json` und `summary.md`, Export und AIJ-Datei enthalten sie nicht. (#3)
- **Freier Fit:** Grenzen für a/R* kommen aus dem Literaturwert statt fest 3…25. Planeten mit großem a/R* (K2-115b, 32) brechen nicht mehr mit „x0 is infeasible“ ab. (#6)
- **Ist Tc eindeutig?** Tc-Profil (Fit bei festem Tc, Suche nach einem zweiten Tal) und Kontrollfit mit festem Rp/R*. Ergebnis als Ampel in `fit.json`, `summary.md`, Ergebnisblatt, `tc_profil.png` und der Prüfliste der GUI. (#15)
- **Gaia DR3 über VizieR** statt nur über das ESA-Archiv (`[gaia] quelle`, `timeout_s`). Fällt ein Dienst aus, werden automatisch der VizieR-Spiegel in Harvard und das ESA-Archiv versucht (15 s Verbindungs-Timeout). Ein Gaia-Feld aus einem anderen Lauf derselben Messung wird wiederverwendet. (#3)

### Vergleichssterne

- **Bekannte Veränderliche verwerfen:** Kandidaten mit Gaia-Flag `VARIABLE` oder VSX-Eintrag (5″) fallen raus, der Grund steht in `candidates_rejected.csv`. Ohne Netz gibt es eine Warnung, der Lauf geht weiter. (#8)
- **Lichtkurve je Stern:** jeder Kandidat gegen die Summe der übrigen, Airmass und Flip detrendet. Bei Ruhe > 3 und β > 1,5 gilt er als variabel und kommt nicht in den Pool. Neues Bild `vergleichssterne_lc.png` mit Gaia-DR3-Kennung und G-Helligkeit je Stern. (#8)
- **Reviewer-Methode:** Einzelstern-Test (Transit-Fit mit jedem Vergleichsstern allein, Abweichung von Rp/R*), optional `[search] einzel_tiefe_sigma` zum Ausschließen auffälliger Sterne und `[search] tiefen_gewicht` bei der Ensemble-Wahl. Standard bleibt das bisherige Verhalten. (#15)
- **Vergleichssterne per Haken wählen:** im Reiter Vergleichssterne die Spalte „wählen“ abhaken, mit **Vorschau** (schneller Fit ohne MCMC, `vorschau.png`) prüfen und **als neuen Lauf rechnen** (`gui_<zeit>_<modus>_hand`, Einstellungen vom Quell-Lauf). Auf der Kommandozeile: `[search] ensemble = [...]` und `transit vorschau`. Kommentar und Ergebnisblatt vermerken die Wahl von Hand. (#16)

### Bedienoberfläche (GUI)

- **Neue Browser-Oberfläche:** Bereiche Planen / Auswerten / Logbuch / Hilfe, Messungsliste mit Suche und Filtern, Schrittleiste Daten → Lauf → Vergleichen → Hochladen, Hinweise aus dem Header (Farbkamera, Filter, Lights am NAS), optionaler zweiter Lauf mit der anderen Kalibrierung, „Erweitert“ als Seitenleiste mit markierten Änderungen. Die bisherige Oberfläche bleibt unter `/klassisch` bzw. `transit gui --klassisch`. (#5)
- **Laufansicht:** alle Schritte mit Dauer und Restzeit, Stoppuhr für die Gaia-Abfrage, Lebenszeichen, Browser-Benachrichtigung. Das Live-Protokoll zeigt den ganzen Verlauf und ist scrollbar. (#5, #9)
- **Vergleichen:** Kennzahlen nebeneinander, Prüfliste, „gültig“ setzen mit Rückgängig, ExoClock-Felder einzeln kopierbar, Haken „hochgeladen“. (#5)
- **Läufe verstecken:** einzelne Läufe in „Läufe dieser Nacht“ und „Vergleich“ ausblenden. Es wird nichts gelöscht, nur eine Markierungsdatei `versteckt.json` angelegt. (#16)
- **Spalte Lauf sortierbar**, der neueste Lauf steht standardmäßig oben. (#15)
- **Hilfe ⓘ** an allen Spaltenköpfen (Vergleichssterne, Läufe, Logbuch, Beobachtungsvorschlag) und über Bereichen des Ergebnisblatts und der Feldseite. Der Text erscheint erst nach Klick. (#9, #12, #13)
- **Transit-Skizze:** Sternfarbe aus Teff, Planet mit gemessenem Rp/R* auf dem gemessenen b (freier Fit, ±1 σ), Literaturwerte gestrichelt. Auch ein schwach bestimmtes b wird gezeigt. (#9, #13)
- **Schneller:** Ansicht eines Laufs wird einmal aufgebaut, Tabs werden nur umgeschaltet. Vergleichssterne laden im Hintergrund und ohne Netzabfrage (nur Cache und `gaia_field.csv`). Fehlgeschlagene Gaia-Abfragen werden 6 h nicht wiederholt. (#8)
- Startdatei `transit_gui_klassisch.cmd` entfernt, die klassische Oberfläche ist über `/klassisch` erreichbar. (#10)

### Daten am NAS

- **Lights vom NAS:** Liegt lokal nur `RESULT`, liest ein neuer Lauf die Lights (und `SOLVED`) aus der Kopie am NAS und schreibt die Ergebnisse lokal. Ein Basis-Lauf wird auch aus der NAS-Kopie geholt. (#14, #15)
- **Veraltete NAS-Liste:** Die Suche nach den Lights liest die NAS-Liste bei Bedarf einmal neu ein und nutzt den Archivpfad aus dem Logbuch. Klare Meldung, wenn die Lights nirgends liegen. (#14)
- **Toleranter Namensabgleich:** Eine Kopie wird auch bei anderer Schreibweise gefunden (`HAT-42b` / `HAT42b`, Bindestriche, Groß/Klein, `HAT-P-` = `HAT-`), sofern die Nacht übereinstimmt. (#16)
- **Einzelne FITS vom NAS**, z. B. für das Feldbild im Ergebnisblatt. (#9)
- **Kalibrier-Master** aus `calib.json` werden im aktuellen Light-Ordner wiedergefunden, wenn die Messung verschoben wurde. (#15)

### Export und ExoClock

- **ExoClock-Kommentar vollständiger:** Sigma-Clipping wird immer genannt, verworfene Vergleichssterne mit Grund (Vorfilter, Einzeltest, von Hand), ein gelbes oder rotes Tc-Profil und „selected manually“ bei Wahl per Haken. (#16)

### Installation

- **Portables Windows-Paket:** `packaging/build_windows.py` baut ein ZIP mit Python 3.12, allen Paketen und `transit`. Die Startdateien legen beim ersten Start `config.local.toml` an. Der Workflow „Windows-Paket“ hängt das ZIP an jedes veröffentlichte GitHub-Release an. Ohne tkinter fällt die Ordnerauswahl auf PowerShell zurück. (#2)

### Fehlerbehebungen

- VSX-Abgleich: Der Lauf bricht nicht mehr an maskierten Ganzzahl-Spalten ab (`V`-Flag als uint8, „Cannot convert fill_value nan to dtype uint8“). (#11)
- Gaia-Details: VizieR-Abfrage mit Helligkeitsgrenze, vorher kamen alle Sterne bis G 21 und die Abfrage lief in den Read-Timeout. (#8)
- Reiter Vergleichssterne hängt nicht mehr, wenn die Lights eines Laufs fehlen (archivierte Messung). (#10)
- Hinweis statt leerer Fläche, wenn ein Lauf älter ist als die Ruhe-Prüfung und kein Kurvenbild hat. (#9)

### Bekannt / offen

- Die ausführliche Dokumentation zur Wahl per Haken (Handbuch, `transit hilfe`, ⓘ-Texte) folgt.
- Geplante Punkte aus dem externen Review (Flip-Prior-Gewichtung, Wolken-Erkennung, β über Zeitfenster, echte Belichtungszeit im Modell) stehen in `TODO.md`. (#17)
