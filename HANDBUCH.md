# Handbuch `transit`: Exoplaneten-Transits aus Rohdaten auswerten

`transit` führt eine Beobachtungsnacht in einem nachvollziehbaren Ablauf von den Light-Frames bis zur ExoClock-Upload-Datei. Das Werkzeug liegt in `C:\Photometry\auto\_pipeline\` und ist bewusst von den Messordnern getrennt.

Hilfe gibt es jederzeit:
- `transit hilfe` zeigt die Themenliste.
- `transit hilfe <thema>` zeigt ein Thema (z. B. `flip`, `aij`, `exoclock`).
- `transit <befehl> --help` erklärt die Optionen eines Befehls.
- Dieses Handbuch.

---

## 1. Schnellstart

Die Beispiele sind für die Eingabeaufforderung (cmd). In PowerShell jeden Befehl mit `.\` beginnen (`.\transit run ..\toi-628b`) und die `& rem …`-Kommentare weglassen.

```bat
cd C:\Photometry\auto\_pipeline
transit inventory ..\toi-628b      & rem Header, Prüfsummen, Ephemeride, Warnungen, legt RESULT\transit.toml an
transit calibrate ..\toi-628b      & rem passende Bias/Flat/Dark-Master suchen
transit cube      ..\toi-628b      & rem Gaia-Vergleichssterne + Photometrie (ca. 1-2 min)
transit compsearch ..\toi-628b     & rem beste Vergleichsstern-Ensembles
transit fit       ..\toi-628b      & rem Transit-Fit, Robustheitstests, MCMC (166 Frames ca. 9 min, 1077 Frames ca. 2 h)
transit export    ..\toi-628b      & rem ExoClock-Datei, Formularwerte, AIJ-radec
transit report    ..\toi-628b      & rem Plots und summary.md
```

Alles auf einmal geht mit `transit run ..\toi-628b`. Die Ergebnisse liegen in `..\toi-628b\RESULT\pipeline\`.
`transit run` überspringt Schritte, die schon fertig sind, und macht beim ersten fehlenden oder veralteten Schritt weiter.

Wie weit ein Lauf ist, zeigt `transit status ..\toi-628b`, auch aus einem zweiten Fenster (Kapitel 10).

Voraussetzungen:
- Python 3.13 mit astropy, numpy, scipy, photutils, astroquery und matplotlib (alle schon installiert).
- ASTAP mit D50-Datenbank, nur für `solve`.
- Internet für die ExoClock-Ephemeride (wird 7 Tage zwischengespeichert) und für Gaia (einmal pro Messung, danach `gaia_field.csv`).

**PowerShell:** Programme aus dem aktuellen Ordner brauchen dort ein vorangestelltes `.\`, also `.\transit status ..\KELT-7b`. In der Eingabeaufforderung (cmd) geht es auch ohne. Wer `transit` überall ohne Pfad aufrufen will, nimmt `C:\Photometry\auto\_pipeline` in die PATH-Variable auf.

`transit.cmd` setzt den Pfad und ruft `python -m transit` auf. Aus einem anderen Ordner geht es mit dem vollen Pfad: `C:\Photometry\auto\_pipeline\transit.cmd …`

---

## 2. Ablauf einer Nacht

| Schritt | Befehl | liest | schreibt (in RESULT\pipeline) |
|---|---|---|---|
| 1 | `inventory` | Light-Header | `headers.csv`, `inventory.json`, `..\lights_checksums.json`, `..\transit.toml` (nur falls noch nicht vorhanden) |
| 2 | `solve` (optional) | Lights ohne WCS | Kopien in `<Messung>\SOLVED\` |
| 3 | `calibrate` | Kalibrier-Bibliothek | `calib.json`; mit `--write` kalibrierte FITS in `CALIBRATED\` |
| 4 | `cube` | Lights, `calib.json`, Gaia | `candidates.csv`, `gaia_field.csv`, `cube_<modus>.npz` |
| 5 | `compsearch` | Cube | `compsearch.json` |
| 6 | `fit` | Cube, `compsearch.json` | `fit.json`, `top50.csv` |
| 7 | `export` | `fit.json` | `<Planet>_<Datum>_exoclock_JDUTC.txt`, `…_detrended_BJDTDB.txt`, `…_best_ensemble.radec.txt`, `exoclock_formular.txt` |
| 8 | `report` | alles | `summary.md`, `lightcurve.png`, `tc_hist.png`, `linearity.png`, `flip_offset.png`, `ergebnisblatt.png/.pdf/.html`, `exoclock_paket\`; Zeile in `_pipeline\logbuch.csv` |

Jeder Aufruf ergänzt das Protokoll in `RESULT\pipeline\transit.log`. Daneben entstehen:
- `run.log`: jede Zeile mit Uhrzeit, Start und Ende jedes Schritts, mit `--verbose` auch Debug-Zeilen.
- `status.json`: aktueller Fortschritt, wird alle 10 s neu geschrieben.
- `run_state.json`: welche Schritte mit welchen Einstellungen fertig sind, für das Fortsetzen.

**Was in den Schritten passiert**

1. **inventory** liest alle Header und speichert Prüfsummen der Lights. Es holt die Ephemeride (zuerst ExoClock, sonst NASA Exoplanet Archive) und sagt Tc, Ingress und Egress für die Nacht voraus. Dazu prüft es die Planung: Abdeckung, Baseline, Airmass, Meridian-Flip, Kameratemperatur und Frames ohne WCS.
2. **solve** kopiert ungelöste Frames nach `SOLVED\` und löst sie dort mit `astap_cli -update`. Danach nutzen alle Schritte die gelöste Kopie.
3. **calibrate** durchsucht `calib.library` nach Mastern und wählt die passenden aus: gleiche Kamera, Gain, Offset und Bildgröße, Flat im gleichen Filter, Dark mit gleicher Belichtung, nächstes Datum. Passt die Dark-Temperatur nicht, schätzt es einen Skalierungsfaktor aus den Hot-Pixeln.
4. **cube** sucht Gaia-DR3-Vergleichssterne und lässt bekannte Veränderliche weg (Gaia-Flag VARIABLE, AAVSO VSX; optional zusätzlich die Sterne einer AIJ-`.apertures`-Datei). Dann misst es Bild für Bild: Zentroid, Aperturen mit allen Radien, Hintergrund im Ring (sigma-geclippter Median), Fehler (Photonen, Ausleserauschen, Himmel) und den Roh-Peak. Kalibriert wird im Speicher; es entstehen keine Zwischendateien.
5. **compsearch** wählt zuerst die Frames aus (Sättigung, Ausschlussliste). Dann folgen ein Vorfilter für Vergleichssterne (Streuung oder Trend über 3× Median), die Variabilitätsprüfung jedes Vergleichssterns (siehe „Vergleichssterne auf Variabilität prüfen“), die Messung des Flip-Versatzes und eine gierige Vorwärts-/Rückwärtssuche mit 3–12 Sternen je Radius. Bewertet wird nach der Streuung außerhalb des Transits.
6. **fit** fittet die Top-Kombinationen je mit fester (ExoClock) und freier Geometrie. Dazu kommen ein Jackknife über die Vergleichssterne, Tests (ohne Daten vor dem Ingress) und eine MCMC mit Beta-Faktor für rotes Rauschen.
7. **export** schreibt die Upload-Datei und alle Formularwerte.
8. **report** erstellt die Zusammenfassung und die Diagramme.

---

## 3. Ordnerstruktur

```
auto\
  _pipeline\                 Werkzeug (Code, config.local.toml, HANDBUCH.md, cache\)
  <messung>\
    LIGHTS\, LIGHT\, _work\, _orig\ oder orig\   Original-Lights: NUR LESEN (der erste vorhandene in dieser Reihenfolge zählt)
    SOLVED\                  gelöste Kopien (transit solve)
    CALIBRATED\              kalibrierte Kopien (transit calibrate --write)
    AIJ\                     für AstroImageJ-Projekte
    _reports\                (vorhandene AIJ-Ergebnisse, werden nur gelesen)
    RESULT\
      transit.toml           Einstellungen dieser Messung
      lights_checksums.json  Prüfsummen der Lights
      pipeline\              alle Ergebnisse (anderer Name mit --out)
        lauf.toml            optional: Einstellungen nur für diesen Lauf (überschreiben transit.toml)
```

**Schreibschutz der Lights**
- Jede Schreibfunktion prüft das Ziel und bricht ab, wenn es im Light-Ordner liegt.
- Vor und nach jedem Befehl werden die Prüfsummen verglichen: Größe plus SHA-256 der ersten und letzten 64 KiB. Mit `inventory --full` wird die volle SHA-256 gespeichert.
- Weicht etwas ab, bricht der Befehl mit „Light-Dateien verändert“ ab.

---

## 4. Alle Parameter

Die Standardwerte stehen in `_pipeline\config.local.toml` (beim ersten Einrichten aus `config.example.toml` kopieren; fehlt sie, gilt `config.example.toml`). Einzelne Werte lassen sich pro Messung in `RESULT\transit.toml` überschreiben (gleicher Abschnitt, gleicher Name).

### [target] (pro Messung)
| Name | Standard | Wirkung |
|---|---|---|
| name, planet | aus OBJECT | Planetenname für die Ephemeride (ExoClock-Schreibweise, z. B. `TOI-628b`) |
| ra, dec | ExoClock / OBJCTRA | Zielposition in Grad (J2000). Bestimmt Zielstern, Airmass und BJD. |

### [site]
| Name | Standard | Wirkung |
|---|---|---|
| lat, lon, elev | (eigener Standort) | Standort (Ost positiv). Leer bedeutet: aus SITELAT/SITELONG/SITEELEV. |

### [camera]
| Name | Standard | Wirkung |
|---|---|---|
| gain_e_per_adu | 0.25 | Elektronen pro ADU, für die Fehlerrechnung |
| readnoise_e | 1.2 | Ausleserauschen in e⁻ |
| saturation_adu | 60000 | Liegen Ziel oder ein Ensemble-Stern darüber, wird der Frame verworfen. Ein Vergleichsstern, der in mehr als 5 % der Frames darüber liegt, wird entfernt. |
| linearity_warn_adu | 45000 | nur ein Hinweis in inventory/report |
| farbkamera | "auto" | `auto`: Bilder mit `BAYERPAT` im Header (Farbkamera, z. B. ATR2600C) werden nach der Kalibrierung zu 2×2-Superpixeln summiert und erst dann gemessen. `ja` erzwingt das, `nein` misst wie eine Mono-Kamera. Siehe Kapitel 21. |

### [gaia]
| Name | Standard | Wirkung |
|---|---|---|
| quelle | "vizier" | Gaia DR3 über VizieR (CDS, Katalog `I/355/gaiadr3`) oder `"esa"` (ESA-Gaia-Archiv). Beide liefern dieselben Sterne und Spalten. |
| timeout_s | 60 | Wartezeit pro Abfrage (Verbindungsaufbau max. 15 s). Antwortet die gewählte Quelle nicht, versucht das Werkzeug automatisch die anderen: VizieR CDS → VizieR-Spiegel Harvard → ESA (bzw. umgekehrt bei `esa`). Erst wenn keine antwortet, bricht `cube` mit Meldung ab. |

### [photometry]
| Name | Standard | Wirkung |
|---|---|---|
| radii | 8…24 | gemessene Apertur-Radien in px (alle landen im Cube) |
| annulus | [25, 40] | Himmelsring innen/außen in px |
| centroid_box | 15 | Kantenlänge der Zentroid-Box in px (2D-Gauss, Ersatz: Schwerpunkt) |
| reference_radius | 16 | Radius für Vorfilter und Flip-Messung |

### [comps]
| Name | Standard | Wirkung |
|---|---|---|
| dmag_bright / dmag_faint | −0.5 / +2.0 | Helligkeitsfenster der Kandidaten relativ zum Ziel (Gaia G) |
| color_tol | 0.5 | erlaubte Abweichung in BP−RP |
| edge_px | 80 | Mindestabstand zum Rand, in allen Frames |
| neighbour_px / neighbour_dmag | 40 / 3 | kein Nachbar heller als G+3 innerhalb von 40 px |
| max_candidates | 30 | maximale Zahl der Gaia-Kandidaten (nach |ΔG| sortiert) |
| gaia_gmax | 16 | Grenzgröße der Gaia-Abfrage |
| aij_apertures | "" | AIJ-`.apertures`-Datei; deren Vergleichssterne kommen als C2… dazu |
| katalog_variable | true | Bekannte Veränderliche gar nicht erst als Kandidaten nehmen: Gaia-Flag VARIABLE und AAVSO VSX (Grund in `candidates_rejected.csv`) |
| vsx_radius_arcsec | 5 | Abstand für die Zuordnung eines VSX-Eintrags |
| exclude_stars | [] | Kandidaten, die nie verwendet werden, z. B. `["G06"]` (Gaia VARIABLE, siehe Ergebnisblatt Seite 2). Sie fehlen in Ensemble-Suche, Flip-Versatz, Fit, Export und Bericht. Am besten nur für einen Lauf in `RESULT\<lauf>\lauf.toml` setzen. |

### [search]
| Name | Standard | Wirkung |
|---|---|---|
| radii | [14, 16, 18, 20] | Radien für die Ensemble-Suche |
| n_min / n_max | 3 / 12 | Größe der Ensembles |
| top | 50 | Zahl der Kombinationen, die gefittet werden |
| oot_margin_min | 10 | „außerhalb des Transits“ heißt: vor Ingress bzw. nach Egress, mit diesem Abstand in Minuten |
| prefilter_sigma | 3 | Vergleichssterne mit Streuung oder Trend über n× Median fliegen raus |
| variab_check | true | Lichtkurve jedes Vergleichssterns gegen die übrigen prüfen und variable Sterne verwerfen (Bild `vergleichssterne_lc.png`) |
| variab_sigma | 3 | „variabel“, wenn die Streuung der `variab_bin_min`-Mittel über n× dem Median aller Kandidaten liegt … |
| variab_beta | 1.5 | … und das rote Rauschen (beta) über diesem Wert liegt |
| variab_bin_min | 10 | Mittelungsfenster in Minuten für die Kurzzeit-Variabilität |
| airmass_max | 0 | > 0: Frames über dieser Airmass werden weggelassen (Randpunkte mit starker Systematik, ExoClock-Tipp 6). Die Baseline vor dem Ingress sollte dabei nicht unter ca. 30 min fallen. |
| symmetry_weight | 0 | > 0: Die Ensemble-Suche bevorzugt Vergleichssterne, die rund um das Ziel verteilt sind: Bewertung = OOT-RMS × (1 + Gewicht × Asymmetrie). Hilft beim Meridian-Flip, weil sich das Flat-Restmuster um 180° dreht (ExoClock-Tipp 4). Asymmetrie 0 = ausgeglichen, 1 = alle auf einer Seite; sie steht auf dem Ergebnisblatt. |
| exclude_frames | [] | Dateinamen, die ausgeschlossen werden |
| aij_table | "" | AIJ-Messtabelle; nur deren Frames werden verwendet |

### [fit]
| Name | Standard | Wirkung |
|---|---|---|
| u1, u2 | 0.40, 0.25 | quadratische Randverdunklung (G-Stern, L-Band) |
| fix_geometry | true | a/R* und i aus ExoClock fest, für die MCMC |
| flip | "prior" | `prior`: Flip-Versatz aus den Vergleichssternen als Gauss-Prior; `free`: frei; `none`: ignorieren |
| flip_window_h | [−0.85, 0.85] | Fenster in Stunden um den Flip für die Versatzmessung |
| mcmc_steps | 30000 | Schritte der Metropolis-MCMC insgesamt, über alle Ketten (je Kette wird ein Viertel als Einlaufphase verworfen) |
| airmass_order | 1 | Detrending in der Airmass: 1 = linear, 2 = quadratisch (ExoClock-Tipp 5; per BIC auf dem Ergebnisblatt vergleichen, kleiner ist besser) |
| mcmc_chains | 0 | Zahl der unabhängigen Ketten; 0 = automatisch (seriell 1, parallel bis 16 mit je ≥ 2000 Schritten), Kapitel 11 |
| ausreisser_sigma | 0 | 0 = aus. Sonst werden Frames, deren Abweichung vom Transit-Fit (bestes Ensemble, feste Geometrie) mehr als so viele robuste Standardabweichungen (1,4826 × MAD) beträgt, entfernt; der Fit wird wiederholt, bis nichts mehr herausfällt. Liste in `summary.md` und `ausreisser.json`, Upload-Datei und AIJ-Export ohne diese Frames. GUI: „Erweitert“ → Ausreisser entfernen (wenige 4σ / normal 3σ / viele 2,5σ). KPS-1b mit 3σ: 5 Frames (Wolken, 11,6 h), Streuung 4,9 statt 6,4 ‰, O-C −2,6 ± 1,8 min. |

### [run]
| Name | Standard | Wirkung |
|---|---|---|
| workers | 0 | parallele Prozesse; 0 = Kerne − 2 (hier 30), 1 = seriell wie früher. Auf der Kommandozeile: `--workers N` bzw. `-j N` |
| cube_workers | 8 | Obergrenze für die Photometrie (`cube`): jeder Prozess hält Bias und Flat im Speicher (ca. 0,4 GB) |

### [calib]
| Name | Standard | Wirkung |
|---|---|---|
| library | C:\Photometry\calibration | wird rekursiv nach Mastern durchsucht |
| mode | "bf" | `raw`, `bf` (Bias+Flat) oder `bfd` (zusätzlich skalierter Dark) |
| master_dir | "" | einen bestimmten Master-Ordner erzwingen |
| flat, bias, dark | "" | Pfade zu bestimmten Mastern (gehen vor der automatischen Suche) |
| crop | [0, 0] | Versatz (x, y) des Light-Ausschnitts im Master, wenn die Kamera beschnittene Bilder liefert |

**Gebinnte Lights:** Sind die Lights 2×2 (oder 3×3 …) gebinnt und die Master ungebinnt, also genau das b-Fache der Light-Größe, werden die Master in b×b-Blöcken gemittelt (bei `crop = [0, 0]`). Für das normierte Flat ist das exakt. Bias und Dark hängen vom Binning-Modus der Kamera ab (Mittel oder Summe); bei der ATR2600M sind sie mit ~9 ADU bzw. ~0,2 ADU/120 s ohnehin vernachlässigbar, daher meist Modus `f` (nur Flat).

**Ohne FILTER im Header:** `[export] filter = "L"` setzt den Filter für ExoClock (L → Luminance, R → Cousins R, V → Johnson V …).

**Plate-Solving gebinnter Bilder:** ASTAP bekommt das Bildfeld aus Brennweite und gebinnter Pixelgröße (`FOCALLEN`, `XPIXSZ`, sonst `[camera] focal_mm`, `pixel_um` × `XBINNING`).

**Aperturradien bei Binning:** `[search] radii` ist in Pixeln. Bei 2×2 Binning halbiert sich die FWHM in Pixeln, deshalb kleinere Radien mitprüfen, z. B. `radii = [8, 10, 12, 14, 16, 18, 20]`. Die Wahl bleibt blind nach dem RMS außerhalb des Transits.

### [progress]
| Name | Standard | Wirkung |
|---|---|---|
| status_interval_s | 10 | so oft wird `status.json` geschrieben (Lebenszeichen) |
| hang_after_s | 120 | ist das Lebenszeichen älter, zeigt `transit status` „hängt? JA“ |
| toast | false | Windows-Benachrichtigung am Ende jedes Befehls (wie `--toast`) |

### [paths] und [planning]
| Name | Standard | Wirkung |
|---|---|---|
| astap | C:\Program Files\astap\astap_cli.exe | ASTAP-Kommandozeile für `solve` |
| flip_min_before_ingress_h | 1.0 | Ein Flip, der weniger als so viele Stunden vor dem Ingress liegt, ergibt eine CRIT-Warnung. |
| baseline_min_h | 1.0 | gewünschte Baseline vor und nach dem Transit |
| airmass_max_baseline | 2.0 | Warnung, wenn die Baseline nach Egress höher liegt; in `transit plan` Abzug, wenn das Beobachtungsfenster höher reicht |
| naechte | 3 | `transit plan`: so viele Nächte ab heute |
| alt_min | 10.0 | `transit plan`: Mindesthöhe in Grad (Horizont); Transit und mindestens die halbe Baseline müssen darüber liegen |
| sonne_max | -12.0 | `transit plan`: als dunkel gilt, wenn die Sonne tiefer steht |
| tiefe_snr_min | 3.0 | `transit plan`: Transittiefe mindestens so oft das erwartete Rauschen eines 10-min-Bins |
| rauschboden_ppt | 1.0 | `transit plan`: systematischer Rauschboden pro 10-min-Bin; an die eigenen OOT-RMS-Werte anpassen |
| himmel_mag | 20.0 | `transit plan`: Himmelshelligkeit in mag/arcsec² |
| tastgrad | 0.8 | `transit plan`: Anteil der Belichtungszeit an der Gesamtzeit |
| exoclock_oeffnung | true | `transit plan`: nur Planeten, deren ExoClock-Mindestöffnung ≤ `fit.aperture_cm` ist |
| prioritaeten | alle | `transit plan`: ExoClock-Prioritäten, die vorgeschlagen werden |
| mond_abstand_min | 30.0 | `transit plan`: Warnung, wenn der Mond (≥ 30 % beleuchtet) näher steht |
| wetter | true | `transit plan`: Bewölkungsvorhersage von Open-Meteo abrufen |
| bewoelkung_gut / bewoelkung_max | 20 / 60 | `transit plan`: Ampel grün bis / gelb bis (mittlere Bewölkung in %) |
| sensor_px | [6248, 4176] | Sensorgröße in Pixeln für das Gesichtsfeld |

---

## 5. Warnungen und Abhilfe

| Meldung | Bedeutung | Abhilfe |
|---|---|---|
| `[CRIT] Meridian-Flip … vor Ingress` | Flip im Transit oder kurz davor; der Flip-Versatz ist nur über den Prior bestimmt | Auswertung mit `fit.flip = "prior"`. Beim Beobachten den Flip vor die Baseline legen oder über den Meridian nachführen lassen. |
| `[WARN] Baseline … nur xx min` | zu wenig Daten außerhalb des Transits | längere Sequenz; Nächte wählen, in denen der Transit nahe der Kulmination liegt |
| `[WARN] Baseline nach Egress bei Airmass …` | Ziel steht zu tief, Extinktion und Farbeffekte | wie oben |
| `[WARN] Header-AIRMASS weicht ab` | NINA rechnet mit der Montierungsposition | nichts zu tun; das Werkzeug rechnet selbst |
| `[WARN] Kameratemperatur … nicht gehalten` | kein passender Dark | `calib.mode = "bf"`; künftig Solltemperatur so wählen, dass sie erreicht wird |
| `[WARN] Ziel-Peak > …` | Sättigung | kürzer belichten oder leicht defokussieren |
| `[WARN] Frames ohne WCS` | Plate-Solve fehlt | `transit solve` |
| `Light-Dateien verändert` | Lights wurden geändert (nicht von transit) | prüfen; danach mit `transit inventory` neue Prüfsummen anlegen |
| `… fehlt – zuerst den vorherigen Schritt` | Reihenfolge nicht eingehalten | Ablauf in Kapitel 2 |
| `transit status`: „hängt? JA (Prozess beendet)“ | Der Lauf wurde abgebrochen (Fenster geschlossen, Absturz, Neustart) | `transit run …` erneut starten; fertige Schritte werden übersprungen |
| `transit status`: „hängt? JA (kein Lebenszeichen seit …)“ | Der Prozess lebt, schreibt aber keinen Status mehr (Rechner im Ruhezustand, Prozess eingefroren) | im Task-Manager prüfen; notfalls beenden und neu starten |
| `transit status`: „steht?“ | Lebenszeichen ja, aber seit 15 min kein Fortschritt | meist ein sehr langsamer Einzelschritt; `run.log` ansehen |

---

## 6. AstroImageJ: richtige Header-Einstellungen

**CCD Data Processor → General FITS Header Settings** (mit NINA-Headern):
- **Target coordinate source:** „FITS header target RA/DEC (J2000)“ mit den Keywords `OBJCTRA` / `OBJCTDEC` (Stunden, sexagesimal). Nicht „target name“: `TOI-628b` (Planetenname) findet SIMBAD eventuell nicht.
- **Observatory location source:** „FITS header latitude/longitude“ mit `SITELAT` / `SITELONG`. Längen sind Ost positiv, also kein Vorzeichenwechsel.
- **Speicher-Keywords für Epoch-of-date-RA/Dec:** `RA_OBJ` / `DEC_OBJ`. Sonst überschreibt AIJ die J2000-Werte von NINA in `OBJCTRA`/`OBJCTDEC`.
- **Höhe:** AIJ liest keine Höhe aus dem Header. Im DP Coordinate Converter 640 m eintragen (wirkt sich praktisch nicht aus).
- **Zeit:** AIJ nimmt `DATE-OBS` + `EXPTIME`/2, also die Belichtungsmitte. Das ist korrekt.
- **Altitude-Keyword:** Der DP speichert `CENTALT`, Multi-Aperture liest `ALT_OBJ`; beides gleich setzen.
- **„Calculate headers“** muss im CCD Data Processor auf genau die Frames laufen, die gemessen werden. Sonst fehlen `JD_UTC`, `BJD_TDB` usw., und in der Messtabelle steht BJD_TDB = 0. Das war bei der TOI-628b-Messung der Fall.

**Schaltsekunden (DP Coordinate Converter):**
- „auto leap seconds“ einschalten.
- Letzter Tabelleneintrag: JD 2457754.5 (2017-01-01), TAI−UTC = 37 s. Seitdem gab es keine neue Schaltsekunde.
- astropy nutzt die IANA-Tabelle (gültig bis 2027-06). Die BJD_TDB des Werkzeugs und die von AIJ stimmen bei richtiger Einstellung auf unter 1 s überein.

**Ensemble in AIJ übernehmen:** Die Datei `…_best_ensemble.radec.txt` in Multi-Aperture laden („import RA/Dec“). Das Ziel steht zuerst, danach die Vergleichssterne.

---

## 7. ExoClock

- Das Werkzeug lädt **nichts** hoch.
- **Upload-Datei:** `<Planet>_<Datum>_<lauf>_exoclock_JDUTC.txt`, mit dem Lauf-Namen im Dateinamen, damit Varianten nicht verwechselt werden. Sie enthält JD_UTC des Belichtungsstarts, den relativen Fluss und seinen Fehler.
- **Hochzuladen ist immer die Datei direkt unter `RESULT\`:** `<Messordner>\RESULT\<Planet>_<Datum>_<lauf>_exoclock_JDUTC.txt`. Daneben liegt `<Planet>_<Datum>_exoclock_formular.txt` mit allen Formularwerten und dem Kommentartext. Pro Nacht gibt es dort genau eine Upload-Datei, nämlich die des gültigen Laufs. Wird ein anderer Lauf gültig, ersetzt das Werkzeug die Kopie in `RESULT\`; Dateien in den Laufordnern bleiben dabei unberührt.
- **Nur die gültige Messung hochladen.** Pro Planet und Nacht ist im Logbuch genau ein Lauf „gültig“, alle anderen sind „Varianten“ (Testläufe, andere Kalibrierung, ausgeschlossene Sterne …).
  - Das Upload-Paket `RESULT\<lauf>\exoclock_paket\` eines gültigen Laufs enthält die Upload-Datei und `exoclock_formular.txt` mit der ersten Zeile „DIESE DATEI HOCHLADEN: <voller Pfad>“, dazu Punktezahl sowie ersten und letzten Zeitpunkt. Nach dem Upload bei ExoClock Punktezahl und letzten Zeitpunkt vergleichen.
  - Bei Varianten tragen alle Upload- und Formulardateien im Paket das Präfix `NICHT_HOCHLADEN_`, und das Formular beginnt mit „NICHT HOCHLADEN“ und dem Namen des gültigen Laufs.
  - Gültigen Lauf wählen: `transit logbuch <Messordner> --gueltig <lauf>`. Das passt sofort die Upload-Pakete aller Läufe dieser Nacht an; die O-C-Grafik ändert sich beim nächsten `transit report`. `transit logbuch <Messordner>` allein zeigt die Einträge mit Status.
  - Der erste Lauf einer Nacht wird automatisch gültig, jeder weitere ist zunächst Variante.
  - Nicht airmass-detrendet, denn das macht ExoClock selbst.
  - Die Flip-Stufe ist korrigiert, weil ExoClock sie nicht modellieren kann.
- **Formular:**
  - Time format: JD_UTC
  - Time stamp: Exposure start
  - Flux format: Flux
  - Filter: genau der Menüeintrag, den das Formular nennt, z. B. „Luminance (B to R)“ für L, „R (Cousins)“ für R, „V (Johnson)“ für V, „Clear (UV to IR)“ ohne Filter
  - Belichtungszeit in Sekunden
- Alle Werte zum Kopieren stehen in `exoclock_formular.txt`.
- Diese Konvention stammt aus dem ExoClock-eigenen Export in HOPS. ExoClock empfiehlt JD_UTC (Kokori et al. 2021, Abschnitt 4.3).
- Upload: https://www.exoclock.space/upload/ (nach dem Login).

---

## 8. Was die Ergebnisse bedeuten

- **Tc (MCMC):** Median mit 16/84-%-Grenzen.
- **O-C:** Tc minus die ExoClock-Vorhersage.
- **Beta-Faktor über 1:** Es gibt rotes Rauschen; die Fehler werden entsprechend vergrößert.
- **Top-50-Verteilung und Jackknife:** zeigen, wie stark das Ergebnis von der Wahl der Vergleichssterne abhängt. Eine Streuung, die größer ist als der MCMC-Fehler, ist ein Warnsignal.
- **Geometrie frei vs. fest:** Bei Einzelnächten mit kurzer Baseline ist die freie Geometrie meist unbestimmt; dann die feste verwenden.

---

## 9. Bekannte Grenzen

**Behobener Fehler (24.10.2026):** Bis zur Version 2026.10.24 wurde Tc in den Kleinste-Quadrate-Fits als absolutes BJD gefittet. Die relative Schrittweitengrenze des Optimierers (1e-8 × |x|) entsprach so ca. 35 min, und er hörte oft nach 1–2 Schritten nahe dem Startwert auf. Das betraf:
- Top-50-Verteilung
- Jackknife
- Tests „ohne vor Ingress“
- Flip-Stufe in der Upload-Datei
- Startpunkt der MCMC

Die MCMC-Ergebnisse (Tc, Tiefe, Fehler) waren korrekt, weil die Ketten den Parameterraum selbst abtasten. Jetzt wird Tc als Abstand zur Vorhersage gefittet. Ältere Läufe neu rechnen: `transit run <Messung> --out <lauf> --from fit`.


- Der Fit verwendet nur die Detrend-Terme Konstante, Airmass und Flip. Weitere Terme (FWHM, x/y, Temperatur) brachten bei TOI-628b nach BIC nichts. x/y springen beim Flip und sind gefährlich.
- Die Dark-Skalierung ist ein Faktor pro Nacht; er schwankt mit der Temperatur.
- Die Ephemeride kommt aus dem Netz, mit 7 Tagen Zwischenspeicher in `_pipeline\cache\`.

---

## 10. Fortschritt, Status und Fortsetzen

**Fortschrittsbalken.** Lange Schritte zeigen in der Konsole einen Balken mit Prozent, Restzeit und Uhrzeit des voraussichtlichen Endes:
- `cube`: Frames
- `compsearch`: Ensemble-Bewertungen (geschätzt)
- `fit`: Fits der Top-Kombinationen, danach die MCMC-Schritte. Die Restzeit der Fits enthält schon die geschätzte MCMC-Dauer („inkl. MCMC“); gemessen wird sie vorher an einem Modell-Aufruf.
- `solve`, `calibrate --write`: Frames

Wird die Ausgabe in eine Datei umgeleitet, erscheint statt des Balkens alle 10 % (oder jede Minute) eine Zeile `.. Schritt: 40.0% …`.

**`transit status <Messordner>`** listet alle Läufe in `RESULT\` (pipeline, pipeline_flat, …):

```
Lauf           Zustand  Schritt                                %    fertig ca.     letztes Lebenszeichen  haengt?
pipeline       laeuft   fit: fit / Fits Top-Kombinationen      34%  12:08:10 CEST  24.10. 10:40 CEST      nein
pipeline_flat  fertig   fit: fit                               100% -              24.10. 12:11 CEST      -
```

- „fertig ca.“ ist Ortszeit (CEST im Sommer, CET im Winter).
- „haengt?“:
  - `nein`: Der Prozess lebt und schreibt seinen Status.
  - `JA (Prozess beendet)`: Der Lauf wurde abgebrochen.
  - `JA (kein Lebenszeichen seit …)`: Seit mehr als `progress.hang_after_s` (120 s) kam kein Status.
  - `steht?`: Seit 15 min kein Fortschritt, obwohl der Prozess lebt.
- `transit status … -v` zeigt zusätzlich die einzelnen Schritte mit Dauer.
- Läufe aus der Zeit vor dieser Funktion erscheinen als „kein Status“ mit der letzten Ergebnisdatei.

**`status.json`** (in `RESULT\<lauf>\`) enthält:
- Befehl, Zustand (`laeuft`, `fertig`, `fehler`), PID
- Schritt und Teilaufgabe, erledigt/gesamt, Prozent
- Restzeit `eta_s` und Ende `eta_local`
- Lebenszeichen `heartbeat`, Schrittliste mit Dauern, Ergebnis oder Fehler

Andere Programme können die Datei lesen; sie wird immer vollständig ersetzt, nie halb geschrieben.

**`run.log`** hat jede Ausgabezeile mit Datum und Uhrzeit sowie `===== Schritt …: Start / fertig (Dauer)`. Mit `--verbose` (`-v`) kommen Debug-Zeilen dazu, in die Konsole und in `run.log`:
- jedes Frame
- jede Fit-Kombination mit O-C
- MCMC-Akzeptanz alle 5000 Schritte
- geschätzte MCMC-Dauer

**Zusammenfassung am Ende.** Jeder Befehl schreibt zum Schluss einen Block mit:
- Dauer und Zustand jedes Schritts
- Ergebnis (Tc, O-C, Tiefe), falls `fit.json` neu ist
- allen neu geschriebenen Dateien

**Windows-Benachrichtigung.** Mit `--toast` (oder `[progress] toast = true`) erscheint am Ende eine Windows-Benachrichtigung mit Ergebnis oder Fehler. Sie läuft über das mitgelieferte Windows PowerShell 5.1, ohne Installation. Klappt sie nicht (z. B. Benachrichtigungen aus), läuft der Befehl trotzdem normal zu Ende; mit `--verbose` steht der Grund im Log.

**Fortsetzen mit `transit run`.** Für jeden Schritt prüft `run` nacheinander:
1. Sind die Ergebnisdateien da?

   | Schritt | Dateien |
   |---|---|
   | inventory | `inventory.json`, `headers.csv` |
   | calibrate | `calib.json` |
   | cube | `cube_<modus>.npz`, `candidates.csv` |
   | compsearch | `compsearch.json` |
   | fit | `fit.json`, `top50.csv` |
   | export | `exoclock_formular.txt` |
   | report | `summary.md` |

2. Sind sie nicht älter als die des vorherigen Schritts?
3. Laut `run_state.json` mit denselben Parametern (`--mode`, `--mcmc-steps`) und unveränderten Einstellungen gerechnet?

   | Schritt | Abschnitte |
   |---|---|
   | inventory | [target], [site], [planning] |
   | calibrate | [calib] |
   | cube | [camera], [photometry], [comps], [site] |
   | compsearch | [search] |
   | fit | [fit] |

Ist alles erfüllt, wird der Schritt übersprungen. Der erste nicht fertige Schritt und **alle danach** werden neu gerechnet. Auch einzeln aufgerufene Befehle (`transit fit …`) tragen sich in `run_state.json` ein. Ein abgebrochener `run` geht deshalb beim nächsten Start dort weiter, wo er stehen geblieben ist.
- `transit run … --from fit`: ab `fit` neu rechnen
- `transit run … --force`: alles neu rechnen
- `--new-stars` erzwingt `cube`, `--write` erzwingt `calibrate`

Grenze: Fortgesetzt wird schrittweise. Ein abgebrochener `cube` oder `fit` beginnt von vorn.


---

## 11. Geschwindigkeit und Parallelisierung

Rechner: Ryzen 9 9950X (16 Kerne, 32 Threads), 32 GB RAM, SSD. Standard sind `Kerne − 2` = 30 Prozesse, damit der PC bedienbar bleibt. Jeder Prozess bekommt genau einen BLAS-/OpenMP-Thread (`OMP_NUM_THREADS=1` usw.), damit sich nichts überbucht. Es gibt keine zusätzlichen Pakete; verwendet wird `concurrent.futures` aus der Standardbibliothek.

- `--workers N` (`-j N`) bei jedem Befehl, sonst gilt `[run] workers`.
- `--workers 1` rechnet seriell, genau wie früher.
- Laufen zwei Auswertungen gleichzeitig (z. B. raw und Flat), jeder `--workers 15` geben.

**Was parallel läuft**

- **cube:** Die Frames werden in kleinen Paketen auf höchstens `cube_workers` Prozesse verteilt; jeder Prozess lädt die Master einmal. Das Ergebnis ist bitgenau gleich wie seriell.
- **fit:** Jede Top-Kombination (feste und freie Geometrie) ist ein Auftrag, dazu die Jackknife-Fits und die vier Tests. Die Ergebnisse sind identisch zum seriellen Lauf.
- **MCMC:** Statt einer langen Kette laufen mehrere unabhängige Ketten parallel, bei 30000 Schritten 15 Ketten × 2000. Die Gesamtzahl der Proben bleibt gleich.
  - Kette 1 startet im besten Fit, die übrigen 3 Schrittweiten daneben.
  - Konvergenz: Gelman-Rubin-R-hat für Tc und Rp/R*. Es wird im Log und in `fit.json` (`mcmc.rhat`) angegeben. Ab 1.05 kommt eine Warnung; dann `--mcmc-steps` erhöhen.
  - Die MCMC-Zahlen weichen deshalb vom seriellen Lauf ab, aber nur innerhalb ihres eigenen Fehlers.
- **compsearch** bleibt seriell, weil es nur 1–2 s braucht.

**Schnelleres Transitmodell.** Das Modell summiert die Sternscheibe in 1000 Ringen. Gerechnet werden jetzt nur noch die Ringe, die der Planetenrand schneidet; die übrigen haben eine geschlossene Form. Das Ergebnis ist bis auf Rundungsfehler (1e-16) identisch, aber etwa 3× schneller. Die alte Fassung bleibt als `model.flux_z_full` zum Vergleich.

**Messung an TOI-628b (159 Frames, bf).** Ergebnisse parallel gegen seriell:
- Tc: 2461060.49680 +9.1/−8.1 min gegenüber 2461060.49649 +9.2/−8.1 min. Das sind 0,45 min Unterschied bei ±8,6 min Fehler.
- Tiefe: 5.21 gegenüber 5.15 ppt.
- Gleiches bestes Ensemble (r=16, C2 C4 G26).
- Top-50 und Jackknife: identisch.
- R-hat: 1.02.

| Schritt | seriell vorher | parallel + schnelles Modell |
|---|---|---|
| cube | 75 s | 20 s (8 Prozesse, Faktor 3,8; Grenze: Lesen der Frames) |
| fit inkl. MCMC 30000 | 515 s | 18 s (28 Prozesse, Faktor ≈ 29) |
| compsearch | 1 s | 1 s |

Bei HAT-P-33b (1077 Frames) dauerte der serielle Fit etwa 2 h. Wie lange der parallele Lauf braucht, zeigt `transit status`.

**Zurück zur alten Version.** `_pipeline\_backup_2026-10-24_seriell\` enthält Code, Handbuch und Konfiguration vor dieser Änderung.

---

## 12. Ergebnisblatt

`transit report` erzeugt am Ende das Ergebnisblatt in `RESULT\<lauf>\`:
- `ergebnisblatt.pdf` mit zwei Seiten (A3 hoch): Seite 1 Ergebnis, Seite 2 Feld und Vergleichssterne
- `ergebnisblatt.png` (Seite 1) und `ergebnisblatt_feld.png` (Seite 2)
- `ergebnisblatt.html` (eine Datei, Tabelle als Text zum Kopieren, Blatt als eingebettetes Bild)

Alle drei liegen zusätzlich mit Upload-Datei und `exoclock_formular.txt` in `RESULT\<lauf>\exoclock_paket\`.

**Inhalt**
1. **Lichtkurve:**
   - Einzelpunkte hellgrau, 10-min-Mittel dunkel mit Fehler (`[report] bin_min`), Modell rot, Residuen darunter
   - grau gestrichelt: Ingress/Egress der Vorhersage; rot: gemessene Kontakte 1–4
   - punktiert: Tc vorhergesagt, durchgezogen: Tc gemessen
2. **Dein Wert vs. Literatur**, mit Abweichung in σ (eigener und Literaturfehler quadratisch addiert) und Ampel: grün < 2σ, gelb 2–3σ, rot > 3σ, grau = schwach bestimmt oder ohne Fehler.
   - **Tc, O-C** gegen die Ephemeride.
   - **Tiefe in ppt und mmag:** das Modell-Minimum mit Randverdunklung, nicht Rp²; deshalb direkt mit `depth_r_mmag` von ExoClock vergleichbar. Der Literaturfehler ist aus dem Fehler von Rp/R* abgeleitet.
   - **Rp/R*, Rp in R_Jup und R_Erde:** Der Sternradius kommt aus dem NASA-Archiv.
   - **Rp/R*-Drift (ExoClock-Art):** (Rp/R* − Literatur) / √(σ² + σ_Lit²) mit dem ExoClock-Wert. ExoClock lehnt ab |Drift| ≥ 3 ab (rot) und nennt < 2 gut (grün), 2–3 akzeptabel (gelb). Die Drift steht auch in der Tiefen-Prüfung. Bei HAT-P-33b (Flat) passte sie mit −2,55 fast genau zu ExoClocks eigener Auswertung (−3,37 mit deren Fehler).
   - **Detrending, Ensemble-Asymmetrie, ausgeschlossene Sterne** stehen im Gütebereich.
   - **t14, t12 = t34:** aus a/R*, i (fest) und eigenem Rp/R*.
   - **a/R*, i, b und Sterndichte ρ*:** aus einem Fit mit freier Geometrie, Fehler aus der Kovarianz. Ab 10 % relativem Fehler bei a/R* steht „zur Info, schwach bestimmt“ (grau).
   - **Spektraltyp:** nur wenn ρ* auf 20 % bestimmt ist; grob, Hauptreihe angenommen.
   - **Güte:** OOT-RMS, χ²/dof (Fehler nur Photonen und Ausleserauschen, ohne Szintillation, daher meist > 1), BIC, β, Tc-Streuung der Top-50 gegen den MCMC-Fehler, Zahl der Ketten mit R-hat.
3. **Maßstabsskizze:** Stern auf dunklem Himmel, Farbe aus der Sterntemperatur (Teff aus ExoClock bzw. NASA), Randverdunklung mit den Koeffizienten des Fits. Der Planet ist eine schwarze Scheibe mit dem gemessenen Rp/R*; der Literaturwert ist als gestrichelter Umriss darüber gelegt. Die Bahn liegt beim gemessenen Stoßparameter b aus dem freien Geometrie-Fit (blaue Linie, Band = ± 1 σ), die Literatur-Bahn ist weiß gestrichelt. Ist b aus der Nacht nicht bestimmbar (freier Fit „schwach bestimmt“), sitzt der Planet auf der Bahn der Fit-Geometrie, und das steht unter der Skizze. Jupiter und Erde im selben Maßstab (R* aus der Literatur).
4. **O-C-Diagramm** aller eigenen Messungen dieses Planeten aus `_pipeline\logbuch.csv`. Jeder `report` trägt seinen Lauf ein und ersetzt einen früheren Eintrag desselben Laufs. Spalten: Planet, Nacht, Messordner, Lauf, Status (gueltig/variante), Modus, Epoche, Tc, Fehler, O-C, Tiefe, Rp/R*, Ensemble, Zeitpunkt. Der gültige Lauf legt außerdem seine Upload-Datei und das Formular als Kopie direkt in `RESULT\` ab; hochzuladen ist immer diese Datei (Kapitel 7). In der Grafik erscheinen nur gültige Messungen farbig; Varianten sind klein und hellgrau („nicht gewertet“), der aktuelle Lauf ist ein Stern (grau, wenn er eine Variante ist). Gültigen Lauf ändern: `transit logbuch <Messordner> --gueltig <lauf>` (Kapitel 7). Parallele Berichte schreiben das Logbuch nacheinander (Sperrdatei `logbuch.csv.lock`).

**Layout.** Die Höhe beider Seiten richtet sich nach dem Inhalt: Anzahl der Tabellenzeilen, Länge der Prüfliste, Seitenverhältnis des Feldbilds. Nichts überlappt, auch bei vielen Vergleichssternen oder Prüfungen; die Seiten können dafür länger als A3 werden.
5. **Feld und Vergleichssterne (Seite 2):**
   - **Feldbild:** das Frame mit dem besten Seeing innerhalb ± 0,5 h um die gemessene Transitmitte. Liegen die Frames nicht im Messordner (nur `RESULT\` lokal, Lights am NAS), wird das Frame aus der anderen Kopie der Messung gelesen: zuerst der Archivpfad aus dem Logbuch, dann ein Ordner gleichen Namens lokal oder am NAS (`[paths] archiv_wurzel`), jeweils `SOLVED\` vor den Lights. Es wird nur gelesen, nichts kopiert. Ist das NAS nicht verbunden, enthält Seite 2 eine Meldung statt des Bildes. Es ist verkleinert und asinh-gestretcht (Hintergrund dunkelgrau, Sterne nicht ausgebrannt). Über das WCS ist es so gedreht und gespiegelt, dass Norden oben und Osten links liegt, mit Kompass und 10′-Maßstab.
     - rot, beschriftet: der Zielstern („HAT-P-33 (b)“)
     - blau, Kreis = 2,5 × Apertur: die Vergleichssterne C1, C2 … passend zur Tabelle
     - grau gestrichelt: geeignete, aber nicht genutzte Kandidaten
     - grau „x“: verworfene Gaia-Sterne im Feld
   - **Tabelle der Vergleichssterne:**
     - Kennung, Gaia DR3 ID, RA/Dec, Abstand zum Ziel in Bogenminuten
     - G und ΔG, BP−RP und ΔFarbe, maximaler Roh-Peak
     - RUWE und Variabilitätsflag aus Gaia DR3
     - Nachbarn innerhalb 10″ aus dem Gaia-Feld (bis G = 16)
     - eigene Streuung im Vorfilter, Anteil am Ensemble-Fluss, Änderung des O-C ohne diesen Stern (Jackknife)
     - gelb: ein Hinweis, der beachtet werden sollte (RUWE > 1,4 = möglicher Doppelstern, Gaia VARIABLE, Nachbar < 10″)
   - **Begründung in Klartext** je Stern: Helligkeit und Farbe ähnlich dem Ziel, ruhig (Rang der Streuung), Teil des besten Ensembles, dazu Warnungen.
   - **Ausschlüsse:** die geeigneten, aber nicht genutzten Kandidaten, dann die verworfenen mit Grund: Vorfilter, Sättigung, Kriterien aus `candidates_rejected.csv`.
   - **Gaia-Daten:** RUWE und Variabilität kommen seit der VizieR-Umstellung gleich mit der Feldabfrage (`gaia_field.csv`); ältere Läufe fragen sie einmal nach (Quelle laut `[gaia] quelle`). Gespeichert in `RESULT\<lauf>\gaia_details.json`. Ohne Internet bleiben die Spalten leer; alles andere kommt aus `gaia_field.csv` und `candidates*.csv`.
6. **Planetenprofil (Literatur):** Periode, Masse, Radius, T_eq, Entdeckung, V-Helligkeit, R*, M*, Teff, Spektraltyp.
7. **Fußzeile:**
   - Beobachter, Teleskop und Kamera aus `[observer]` in `transit.toml`, sonst aus dem Header
   - Filter, Belichtung, Ort, Datum, Werkzeug-Version

**Quellen:**
- ExoClock-Datenbank (Cache 7 Tage)
- NASA Exoplanet Archive, Tabelle `pscomppars`, über astroquery (Cache 30 Tage in `_pipeline\cache\nasa_*.json`)

Beide stehen mit Datum auf dem Blatt. Ohne Internet und ohne Cache bleiben die NASA-Spalten leer.

**Ehrlichkeitsregel.** Das Ergebnisblatt zeigt nur an; nichts davon fließt in eine Auswahl zurück. Kein Schritt des Werkzeugs benutzt die Literatur-Tiefe, das Literatur-Rp/R* oder ein Literatur-Tc zur Auswahl von Frames, Sternen oder Ensembles. Offen gesagt, was die Literatur doch beeinflusst:
- Bei `fit.fix_geometry = true` sind a/R* und i aus ExoClock fest.
- Die vorhergesagten Ingress/Egress-Zeiten (± `oot_margin_min`) legen fest, welche Punkte als „außerhalb des Transits“ für die Ensemble-Bewertung zählen.

Beides steht auf dem Blatt und in `summary.md`.

**Prüfung der Tiefe.** Weicht die Tiefe mehr als 3σ von der Literatur ab, steht eine Warnung im Log und auf dem Blatt (rot). Geprüft wird immer, `[!]` markiert Auffälliges:

| Prüfung | Auffällig wenn |
|---|---|
| Blend | Gaia-Sterne innerhalb des Aperturradius tragen mehr als 2 % Fremdlicht bei (verdünnt die Tiefe um 1/(1+f)) |
| Nichtlinearität | Ziel-Peak über `camera.linearity_warn_adu` |
| Airmass-Kopplung | Korrelation Airmass-Term mit Transitform \|r\| > 0.5 (der Airmass-Term kann Tiefe „schlucken“) |
| Kurze Baseline | vor Ingress oder nach Egress weniger als `planning.baseline_min_h` |
| Meridian-Flip | Flip-Stufe kommt aus dem Prior; ein Fehler dort geht direkt in die Tiefe |


---

## 13. Archivieren (Messordner aufs NAS)

Nach der Einreichung kann ein Messordner (z. B. `auto\HAT-P-33b`) ins Archiv. `_pipeline` bleibt lokal.

**Was lokal bleiben muss**
- `_pipeline\` mit Code, `config.local.toml`, `HANDBUCH.md` und `cache\` (ExoClock-, NASA-Daten). Der Cache enthält keine Verweise auf Messordner.
- `_pipeline\logbuch.csv`: die O-C-Historie. Die O-C-Grafik jeder neuen Nacht liest **nur** das Logbuch, keine Dateien alter Nächte. Pro Lauf stehen dort:
  - Planet, Nacht, Lauf, Status (gueltig/variante), Modus, Epoche
  - Tc (BJD_TDB) mit Fehler, die damals benutzte Vorhersage (Tc_pred, Periode, Quelle) und O-C mit Fehler
  - Tiefe, Rp/R* mit Fehler, Drift
  - Apertur-Radius, Ensemble, Name der Upload-Datei
  - Archivpfad
  
  Mit Tc und Fehler lässt sich O-C auch gegen eine spätere, bessere Ephemeride neu rechnen.
- `calibration\` (Master), falls jemand eine archivierte Nacht neu rechnen will. `RESULT\transit.toml` kann absolute Pfade dorthin enthalten.

**Was nach dem Verschieben noch geht**
- `transit report` und `run` einer neuen Nacht: ja, das Logbuch reicht.
- Von Hand verschoben (ohne `transit archiv`)? `transit logbuch <alter Pfad> --archiv <neuer Pfad>` trägt den neuen Ort ein. Mit `--gueltig <lauf>` wird dort dann nur die Upload-Kopie in `RESULT\` geschrieben, sonst nichts im Archiv verändert.
- `transit logbuch <Messordner>`: zeigt die Einträge. Mit `--gueltig` werden Pakete nicht lokaler Läufe übersprungen, mit Hinweis.
- `transit status`: braucht den Messordner selbst; am Archivpfad aufrufen.
- Eine archivierte Nacht neu rechnen: Befehle direkt mit dem Archivpfad aufrufen. Das Logbuch erkennt die Läufe über die Spalte `archiv` wieder und legt keine Duplikate an.

**Befehl**
```bat
transit archiv ..\HAT-P-33b --ziel \NAS\astro\messungen --probe     & rem Trockenlauf: zeigt Dateien, Groesse, Platz am Ziel, Ablauf
transit archiv ..\HAT-P-33b --ziel \NAS\astro\messungen             & rem kopieren + pruefen, Original bleibt
transit archiv ..\HAT-P-33b --ziel \NAS\astro\messungen --loeschen  & rem wie oben, danach lokal loeschen (nur wenn alles stimmt)
```
Ablauf:
1. Die neueren Logbuch-Spalten aller Läufe werden aus `fit.json` nachgetragen. Das geht auch einzeln: `transit logbuch <Messordner> --nachtragen`.
2. Der ganze Messordner wird nach `<ziel>\<Ordnername>` kopiert. Vorhandene Dateien gleicher Größe werden nicht neu kopiert, ein abgebrochener Lauf setzt also fort.
3. Die SHA-256-Prüfsumme jeder Datei wird an Quelle und Ziel verglichen; `archiv_manifest.json` am Ziel listet alle Dateien mit Prüfsumme.
4. Der Archivpfad wird im Logbuch eingetragen.
5. Gelöscht wird nur mit `--loeschen` **und** nur, wenn alle Prüfsummen stimmen. Bei einer Abweichung bricht der Befehl ab, nichts wird gelöscht und das Logbuch bleibt unverändert.

Sicherungen:
- Nur Ordner mit `LIGHT`/`LIGHTS`/`_work` werden archiviert, nie `_pipeline`.
- Ein Ziel innerhalb der Messung wird abgelehnt.
- Reicht der Platz am Ziel nicht oder ist das NAS nicht erreichbar, bricht der Befehl vor dem Kopieren ab.

---

## 14. AstroImageJ-Export

Für den gültigen Lauf einer Nacht schreibt `transit report` automatisch einen Ordner `RESULT\<lauf>\aij\`. Für jeden anderen Lauf geht das mit `transit aij <Messordner> --lauf <lauf>`. Darin liegen:

| Datei | Inhalt |
|---|---|
| `<Planet>_<Datum>_<lauf>_Measurements.xls` | Messtabelle im AIJ-Format, tab-getrennt (siehe unten) |
| `<Planet>_<Datum>_<lauf>_Measurements.plotcfg` | Multi-Plot-Konfiguration mit demselben Namen, damit AIJ sie mit der Tabelle zusammen lädt |
| `oeffnen.ijm` | ImageJ-Makro: startet Multi-Plot und lädt Tabelle und Konfiguration |
| `LIESMICH.txt` | diese Anleitung in kurz |

**Messtabelle.** Sie hat die Spaltennamen, die AIJ selbst schreibt:
- `Label` (Dateiname), `J.D.-2400000`, `JD_UTC` (Belichtungsmitte), `BJD_TDB`, `AIRMASS` (berechnet), `CCD-TEMP`, `EXPTIME`, `FWHM_Mean`, `Source_Radius`, `Sky_Rad(min/max)`
- `rel_flux_T1` (Ziel / Summe der Vergleichssterne) und `rel_flux_C2…` (Vergleichsstern / Summe der anderen, wie in AIJ), jeweils mit `rel_flux_err_…`
- `tot_C_cnts`, `tot_C_err`
- je Stern `X(FITS)`, `Y(FITS)`, `RA`, `DEC`, `Source-Sky`, `Source_Error`, `Peak`, `Sky/Pixel`, `FWHM`
- `Meridian_Flip` (0 vor, 1 nach dem Flip, als Detrend-Spalte nutzbar)

Die Vergleichssterne sind genau das Ensemble des Laufs, in derselben Reihenfolge wie auf dem Ergebnisblatt.

**Plot-Konfiguration.** Vorlage ist deine eigene AIJ-Einstellung (`_pipeline\aij_vorlage.plotcfg`, kopiert aus HAT-42b). Darin ersetzt das Werkzeug:
- oben `rel_flux_T1` mit Transitfit, darunter bis zu 5 Vergleichssterne `rel_flux_C2…`, versetzt um −0,045, −0,050, −0,055 … (also bei 0,955, 0,950, …)
- rote Marker „Predicted Ingress/Egress“ aus der ExoClock-Ephemeride (umgerechnet auf JD_UTC)
- x-Achse `JD_UTC` (AIJ zieht den ganzen Tag ab)
- Detrending `AIRMASS`, bei einem Flip zusätzlich `Meridian_Flip`
- Periode, Titel (Planet, Nacht) und Untertitel (Lauf, Radius, Ensemble)

Willst du eine andere Vorlage: in AIJ eine Konfiguration speichern („Save plot configuration…“) und als `_pipeline\aij_vorlage.plotcfg` ablegen.

**Öffnen – automatisch**
```bat
transit aij ..\HAT-42b --oeffnen            & rem gueltiger Lauf; startet AstroImageJ und laedt beides
transit aij ..\HAT-42b --lauf pipeline_flat --neu --oeffnen
```
In PowerShell (im Ordner `_pipeline`): `.\transit aij ..\HAT-42b --oeffnen`.
Das Werkzeug startet `C:\Program Files\AstroImageJ\AstroImageJ.exe -macro oeffnen.ijm`. Das Makro ruft `IJ.runPlugIn("Astronomy.MultiPlot_")` und danach `MultiPlot_.openDataAndConfig(<Tabelle>)` auf. Getestet mit AIJ 6.0.11: Es erscheinen die Fenster „Multi-plot Main“, „Measurements in …“ und „Plot of Measurements in …“. Ohne vorher geöffnetes Multi-Plot wirft AIJ eine Exception, deshalb die Reihenfolge.

**Öffnen – von Hand**
1. AstroImageJ starten.
2. Multi-Plot öffnen (Diagramm-Symbol in der AIJ-Leiste) → Fenster „Multi-plot Main“.
3. Dort **File → „Open table and plot configuration from file…“** und die `.xls` wählen. AIJ lädt die gleichnamige `.plotcfg` dazu.
   - Alternativ erst „Open table from file…“, dann „Open plot configuration from file…“.
   - Oder das Makro starten: Plugins → Macros → Run… → `oeffnen.ijm`.

**Hinweise**
- AIJ übernimmt eine geladene Plot-Konfiguration in seine eigenen Einstellungen. Das ist normales AIJ-Verhalten.
- Die Tabelle ist eine Ansicht der transit-Messung. Ein Fit in AIJ ist eine eigene, unabhängige Auswertung; für ExoClock gilt die Upload-Datei direkt unter `RESULT\`.

---

## 15. Bedienoberfläche im Browser (`transit gui`)

**Am einfachsten:** im Explorer `_pipeline\transit_gui.cmd` doppelklicken. Ein Konsolenfenster „Transit GUI“ geht auf und der Browser zeigt die Oberfläche. Das Fenster offen lassen, solange du arbeitest; Schließen beendet die Oberfläche (laufende Auswertungen laufen weiter). Läuft sie schon, öffnet ein zweiter Doppelklick nur den Browser. Für den Desktop: Rechtsklick auf `transit_gui.cmd` → „Senden an“ → „Desktop (Verknüpfung erstellen)“.

Von der Kommandozeile (PowerShell: `.\transit gui`):
```bat
transit gui                 & rem startet http://127.0.0.1:8765/ und oeffnet den Browser
transit gui --port 8800     & rem anderer Port;  --kein-browser: nur den Server starten
```
Die Oberfläche läuft nur auf diesem Rechner (127.0.0.1) und braucht nichts außer Python. Jede Aktion ruft die normalen Befehle auf (`transit run`, `transit logbuch --gueltig`, `transit aij --oeffnen`); es gibt keine zweite Rechenlogik. Die Einstellungen eines Laufs schreibt sie in `RESULT\<lauf>\lauf.toml`, genau wie von Hand. Beenden: Strg+C im Konsolenfenster.

**Neue Oberfläche (Standard seit 2026-11) und klassische Oberfläche.** `transit gui` öffnet die neue Oberfläche unter `http://127.0.0.1:8765/`. Die bisherige Oberfläche bleibt unverändert erhalten und ist jederzeit erreichbar: unter `http://127.0.0.1:8765/klassisch`, mit `transit gui --klassisch` oder per Doppelklick auf `transit_gui_klassisch.cmd`. Beide benutzen dieselben Läufe und Dateien; man kann zwischen ihnen hin und her wechseln.

Die neue Oberfläche hat oben vier Bereiche (**Planen**, **Auswerten**, **Logbuch**, **Hilfe**) und rechts oben einen Hinweis, solange ein Lauf aktiv ist (Klick öffnet ihn).
- **Auswerten:** links die Messungen nach Monat, mit Suche (Enter sucht auch am NAS) und Filtern (Neu, Ohne gültig, Gültig). Rechts die Schrittleiste *Daten → Lauf starten → Vergleichen → Hochladen*, Hinweise aus dem Header (Farbkamera, unklarer Filter, Lights am NAS), das Formular **Neuer Lauf** und die **Läufe dieser Nacht**. Mit dem Haken „zusätzlich … starten“ wird nach dem ersten Lauf automatisch ein zweiter mit der anderen Kalibrierung (f ↔ bf) gerechnet; er übernimmt die Gaia-Abfrage. Laufnamen: `gui_<Datum>_<Zeit>_<Kalibrierung>`.
- **Erweitert** öffnet eine Seitenleiste mit fünf Gruppen (Kalibrierung, Kamera & Gaia, Vergleichssterne, Apertur, Fit & Ausreißer). Geänderte Felder sind blau markiert und stehen als Zusammenfassung im Formular; leere Felder zeigen den Standard als grauen Text. „als meine Vorgabe merken“ speichert die Werte im Browser.
- **Lauf (Details):** alle Schritte mit Dauer, der laufende Schritt mit Balken und Restzeit. Schritte ohne Prozentangabe (z. B. die Gaia-Abfrage) zeigen eine Stoppuhr und das Zeitlimit; „Jetzt auf VizieR/ESA wechseln“ stoppt die Abfrage, trägt `[gaia] quelle` in `lauf.toml` ein und setzt den Lauf fort. Darunter die letzten Zeilen der Konsole (live), das Lebenszeichen und auf Wunsch eine Browser-Benachrichtigung, wenn der Lauf fertig ist. Das **Protokoll (live)** enthält die ganze Ausgabe des Laufs und ist scrollbar (Höhe am unteren Rand ziehbar); es scrollt nur mit, solange man ganz unten steht.
- **Vergleichen:** Kennzahlen aller fertigen Läufe nebeneinander (niedrigstes OOT-RMS ist markiert), Ergebnisblatt (Lichtkurve, Feld, Vergleichssterne), Prüfliste (Planungs-Warnungen, Drift, R-hat) und **Als gültige Messung dieser Nacht setzen** (mit Rückgängig). Für den gültigen Lauf: jedes ExoClock-Feld mit Kopierknopf, der Kommentar zum Bearbeiten und der Haken **Bei ExoClock hochgeladen** (Datei `RESULT\<lauf>\hochgeladen.json`). **Hilfe im Ergebnisblatt:** Fährt die Maus über das Blatt, erscheinen kleine ⓘ-Symbole; Überfahren oder Anklicken eines Bereichs (Lichtkurve, Residuen, Skizze, Kopfzeile, O-C, Profil, jeder Spaltenkopf und jede Zeile der Tabelle, auf der Feld-Seite Bild und Spaltenköpfe) zeigt eine Erklärung. Die Lage der Bereiche schreibt `report` in `ergebnisblatt_hilfe.json`; ältere Läufe bekommen die Hilfe nach `transit report` neu. PNG und PDF bleiben unverändert.

Die folgenden Abschnitte beschreiben die **klassische** Oberfläche.

**Vorne**
- **Messordner:** alle Ordner unter `auto\`, die `LIGHT`, `LIGHTS`, `_work`, `_orig` oder `orig` enthalten.
- **Planet:** Vorschlag aus dem FITS-Header (`OBJECT`), in ExoClock-Schreibweise.
- **Filter:** die ExoClock-Menüeinträge. Vorschlag aus `FILTER` im Header, sonst aus `[export] filter`.
- **Kalibrierung:** f, bf, bfd oder raw.
- **Laufname:** leer = automatisch `gui_<Datum>_<Zeit>`.
- **Photometrie übernehmen von:** einen vorhandenen Lauf mit gleicher Kalibrierung wählen. Dann werden Cube, Kandidaten und Inventur kopiert, und `transit run` überspringt diese Schritte. Spart Minuten.
- **Prozesse:** leer = automatisch (Kerne − 2).
- **Start:** startet `transit run <Messordner> --out <lauf> --mode <…>`. Die Ausgabe landet in `RESULT\<lauf>\gui_konsole.txt`.
- **Läufe:** Tabelle aller Läufe mit Fortschritt (Balken, Prozent, voraussichtliches Ende, „hängt?“), O−C, Rp/Rs, Drift (Ampel), OOT-RMS, β, Flip-Unsicherheit, Radius, Ensemble und ausgeschlossenen Sternen. Sie aktualisiert sich alle 5 s.
  - Knopf **Blatt:** zeigt beide Seiten des Ergebnisblatts.
  - Knopf **Gültig:** wie `transit logbuch --gueltig`; die Upload-Datei unter `RESULT\` wird ersetzt.
  - Knopf **In AIJ öffnen:** wie `transit aij --oeffnen`.

**Erweitert** (zu jedem Feld steht ein Hilfetext daneben)

| Feld | wird zu |
|---|---|
| Flat, Bias, Dark (Pfad) | `[calib] flat/bias/dark`; leer = automatische Suche |
| Gaia-Quelle VizieR/ESA | `[gaia] quelle` (Standard VizieR) |
| Farbkamera automatisch/ja/nein | `[camera] farbkamera` (ändert die Photometrie → Cube wird neu gerechnet) |
| Helligkeit hell/schwach (ΔG) | `[comps] dmag_bright / dmag_faint` |
| Mindestabstand Nachbar, Rand (px) | `[comps] neighbour_px / edge_px` |
| Apertur von/bis (× FWHM) | `[search] radii`, aus der FWHM des Basislaufs in Pixel umgerechnet |
| Hintergrundring innen/außen | `[photometry] annulus` (ändert die Photometrie → Cube wird neu gerechnet) |
| Detrending linear/quadratisch | `[fit] airmass_order` |
| Airmass-Grenze | `[search] airmass_max` |
| Meridian-Flip Prior/frei/ignorieren | `[fit] flip` |
| Geometrie fest/frei | `[fit] fix_geometry` |
| MCMC-Schritte | `[fit] mcmc_steps` |
| Symmetrie-Gewicht | `[search] symmetry_weight` |
| Vergleichssterne (Haken) | `[comps] exclude_stars` |

Die Vergleichssterne erscheinen als Tabelle mit Ampel neben dem Feldbild des Basislaufs:
- RUWE > 1,4 gelb (möglicher Doppelstern)
- Gaia VARIABLE rot
- Transitfenster-Test > 3σ rot; das gibt es nur für Sterne im Ensemble des Basislaufs

Vorschlag: VARIABLE und auffällige Transitfenster-Sterne sind abgewählt, ebenso die schon im Basislauf ausgeschlossenen.

**Sicherheit**
- Der Server antwortet nur auf 127.0.0.1.
- Aktionen (POST) brauchen eine eigene Kopfzeile, die fremde Webseiten nicht senden können.
- Ausgeliefert werden nur Dateien unter `<Messordner>\RESULT\`.

**Grenzen des Prototyps**
- Vergleichssterne wählt man in der Tabelle aus, nicht durch Klick ins Bild.
- Die Aperturen müssen in der Photometrie vorhanden sein (Standard 8–24 px); andere Werte ändern `[photometry] radii` und rechnen den Cube neu.

---

## 16. Messungen am NAS finden

Statt eines Pfads geht auch der Name: `.\transit run KELT-7b`, `.\transit aij HAT-P-42b --oeffnen`, `.\transit logbuch toi-628b`. Groß/Klein und Bindestriche sind egal, `HAT-P-42b` = `HAT-42b` = `HAT42b`; auch der Planetenname aus `RESULT\transit.toml` zählt.

**Suchraum:** immer beide Orte rekursiv – der lokale Ordner `...\auto` und das NAS (`[paths] archiv_wurzel`, Standard `\\NAS\share\Photometry\done`), dazu die Archivpfade aus dem Logbuch. Gefunden werden Ordner mit Lights und Ordner mit Ergebnissen (`RESULT\`); Ordner, die nur Darks/Flats/Bias enthalten, zählen nicht. Die Suche ist ein Teilstring ohne Groß/Klein und ohne Satzzeichen („wasp“ findet WASP-52b und WASP-135b, „hat42“ findet HAT-P-42b und HAT-42b).

- Ein Treffer: „Messung gefunden (lokal|NAS): …“ und weiter. Mehrere: nummerierte Liste zum Auswählen (GUI: Knöpfe mit [lokal]/[NAS], Lights, Läufe, gültiger Lauf).
- Die NAS-Ordnerliste liegt in `_pipeline\cache
as_index.json`. Sie wird neu aufgebaut, wenn ein Name nicht darin steht (höchstens alle 5 min) und mit **Aktualisieren** in der GUI. NAS nicht erreichbar: Meldung, lokal geht es weiter.
- GUI-Auswahlliste „Messordner“: alle lokalen und NAS-Messungen (NAS mit „[NAS]“ markiert); „(alle Messordner)“ zeigt unter „Läufe“ die Läufe aller Orte.

Eine Messung am NAS wird wie eine lokale behandelt: Lights nur lesen, Ergebnisse in `RESULT\` desselben NAS-Ordners, Logbuch wie gewohnt. Erkannt werden nur Ordner mit `LIGHT`, `LIGHTS`, `_work`, `_orig` oder `orig`.

**GUI:** Feld „suchen“ neben dem Messordner. Findet es lokal nichts, kommt dieselbe Frage mit **Ja**/**Nein**; Treffer am NAS erscheinen als Knöpfe bzw. werden direkt gewählt.

**Messordner in der GUI (Ergänzung zu Kapitel 15).** Die Auswahlliste zeigt alle Ordner direkt unter `...\auto` (ohne `_`-Ordner) mit Name, Zahl der FITS-Lights und Stand: „gültig: <lauf>“, „n Läufe, keiner gültig“ oder „noch nicht ausgewertet“. Ordner nur mit `RESULT\` (Lights schon am NAS) stehen mit 0 Lights drin, damit Ergebnisse sichtbar bleiben. **Aktualisieren** liest die Liste neu; **Ordner wählen…** öffnet einen Windows-Ordnerdialog (erscheint evtl. hinter dem Browser) für Ordner an anderen Orten, auch am NAS.

**Wo die Lights liegen dürfen:** im ersten Unterordner `LIGHTS`, `LIGHT`, `LIGHT work`, `_work`, `_orig` oder `orig`, der FITS-Dateien enthält, sonst direkt im Messordner. Liegen sie direkt im Ordner, schreibt das Werkzeug nur in Unterordner (`RESULT\`, `SOLVED\`, …), nie daneben; die Lights werden wie immer nur gelesen und per Prüfsumme überwacht.

---

## 17. Feste und mitwachsende Apertur

### Was die Apertur physikalisch tut
Ein Stern ist auf dem Chip kein Punkt, sondern ein Lichtfleck (PSF), dessen Breite das Seeing bestimmt (FWHM). Eine Kreisapertur mit Radius r fängt davon nur einen Teil ein, den **eingefangenen Lichtanteil** (encircled energy, „Curve of Growth“). Für eine gaußförmige PSF gilt

  Anteil(r) = 1 − exp(−4 ln2 · r² / FWHM²)

also bei r = 1 × FWHM etwa 94 %, bei 1,5 × FWHM 99,8 %, darüber praktisch alles (reale PSFs haben breitere Flügel, daher eher 2–3 × FWHM für „fast alles“).

Bei **fester Apertur** ändert sich der Anteil mit dem Seeing: wird das Seeing schlechter, fällt mehr Licht über den Rand. In der **relativen** Photometrie (Ziel ÷ Summe der Vergleichssterne) kürzt sich das heraus, weil alle Sterne im selben Bild dieselbe PSF und dieselbe Apertur haben und daher denselben Anteil verlieren. Darum verfälscht eine feste Apertur die Transittiefe nicht.

Bei der **mitwachsenden Apertur** ist der Radius in jedem Bild r_i = k × FWHM_i. Der eingefangene Anteil bleibt damit über die Nacht konstant, und bei gutem Seeing wird die Apertur kleiner und sammelt weniger Himmelsrauschen. Auch hier haben Ziel und Vergleichssterne im selben Bild denselben Radius, also kürzt sich alles Gemeinsame heraus. **Die Tiefe wird dadurch nicht verzerrt.**

### Wann hilft welche?
- **Mitwachsend** hilft bei stark wechselndem Seeing oder Fokus (z. B. Autofokus mitten in der Nacht) und bei schwachen Zielen, wo das Himmelsrauschen zählt.
- **Fest** ist robuster, wenn das Seeing ruhig ist, bei dichten Feldern (Nachbarn) und bei sehr großen Aperturen, die ohnehin fast alles Licht enthalten.
- Bei hellen Sternen mit großer Apertur (z. B. KELT-7b, r = 20 px ≈ 4 × FWHM) macht es kaum einen Unterschied.

### Fallen
- **Nachbarsterne:** wächst die Apertur, kann ein schwacher Nachbar teilweise hineinrutschen. Seine Beimischung ändert sich dann mit dem Seeing: ein Trend oder eine verdünnte Tiefe. Das Ergebnisblatt prüft Gaia-Nachbarn bis zum **größten** verwendeten Radius („Blend … r max“).
- **PSF über das Feld:** ist die Sternform am Rand anders als in der Mitte (Koma, Verkippung, Bildfeldwölbung), gilt „gleicher Anteil für alle“ nicht mehr exakt – bei fester wie mitwachsender Apertur. Vergleichssterne nahe am Ziel helfen.
- **Verrauschte FWHM:** die FWHM eines Einzelbilds schwankt. Das Werkzeug nimmt deshalb den Median der Vergleichssterne (das Ziel bleibt draußen, damit der Transit nicht in den Radius gelangt) und glättet über 5 Bilder (laufender Median).
- **Zu kleiner Radius:** unter etwa 1,5 × FWHM wird jede Nachführ- oder Zentrierungsungenauigkeit zu Rauschen. Untergrenze im Werkzeug: 1,5 × Median-FWHM.

### Wie das Werkzeug es macht
- Der Cube enthält den Fluss jedes Sterns in festen Radien (`[photometry] radii`, Standard 8–24 px in 2-px-Schritten). Für die mitwachsende Apertur wird der Fluss bei r_i **zwischen den zwei benachbarten festen Radien linear interpoliert** (entlang der Curve of Growth), für Ziel und alle Vergleichssterne mit demselben r_i; Fehler ebenso. Es ist kein zweiter Durchgang über die Lights nötig. Der Fehler der Interpolation ist für alle Sterne gleichartig und kürzt sich im Verhältnis weitgehend heraus.
- Der Hintergrundring bleibt fest (`[photometry] annulus`, Standard 25–40 px); er muss außerhalb des größten Radius liegen.
- Ein k wird übersprungen (mit Hinweis), wenn sein Radius in mehr als 5 % der Bilder mehr als 1 px außerhalb der gemessenen Radien läge; dann `[photometry] radii` erweitern und den Cube neu rechnen.
- In der Kombinationssuche treten feste Radien (`[search] radii`) und mitwachsende k-Werte (`[photometry] k_fwhm`) **gegeneinander an**. Gewählt wird wie immer blind nach dem Rauschen außerhalb des Transits, nie nach Tiefe oder Tc.
- Einstellungen in `[photometry]`: `aperture_mode = "beides"` (Standard) | `"fest"` | `"variabel"`, `k_fwhm = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]`, `fwhm_smooth = 5`.
- Anzeige: Ergebnisblatt (Zeile „Apertur“, Kopfzeile), `summary.md`, Logbuch-Spalte `radius_px` (z. B. „mitwachsend k=2 x FWHM (r 9.1-12.8 px)“), AIJ-Tabelle (`Source_Radius` pro Bild), ExoClock-Datei (Kopfzeile, Englisch). Neues Bild `fwhm.png`: FWHM pro Bild, geglättet, und der Radius des besten Ensembles.
- In der GUI unter „Erweitert“: Feld **Aperturmodus**; „Apertur von/bis (x FWHM)“ gilt für die festen Radien und die k-Werte (Schritt 0,5).

### Beispiel HAT-P-42b (Test, gültiger Lauf unverändert)
FWHM 4,6–6,4 px. OOT-RMS: fest r = 10 px 4,36 ppt, r = 8 px 4,40 ppt; mitwachsend k = 2 (r 9,1–12,8 px) 4,39 ppt, k = 2,5 4,69 ppt. Tc und Tiefe aller Varianten liegen innerhalb ihrer Fehler beieinander. Blind gewählt würde r = 10 px fest – die mitwachsende Apertur ist hier gleichwertig, aber nicht besser.

Siehe auch `TODO.md` (geplante Erweiterungen).

---

## 18. Kalibrier-Master: Quellen und Formate

- **Formate:** FITS (`.fit`, `.fits`) und **XISF** (`.xisf`, PixInsight/Siril). XISF wird ohne Zusatzpaket gelesen (`transit\xisf.py`): unkomprimiert oder zlib (auch mit Byte-Shuffling). lz4/zstd-komprimierte XISF werden mit Meldung abgelehnt – dann den Master unkomprimiert oder als FITS speichern. Die FITS-Schlüsselwörter im XISF (Filter, Binning, Belichtung, Gain/Offset, Temperatur, Kamera) dienen wie bei FITS der Zuordnung. Test: alle 22 XISF-Master der Bibliothek erkannt; `FLAT_MASTER_L` und `BIAS_MASTER` vom 2024-10-09 sind pixelgleich mit ihren FITS-Gegenstücken (gleiche Ausrichtung).
- **Master im Messordner:** liegen Master (IMAGETYP Bias/Dark/Flat bzw. „Master…“) im Light-Ordner der Messung, werden sie nicht als Lights gezählt, sondern direkt für diese Nacht verwendet (nur die Bildgröße muss passen; Gain/Offset fehlen in solchen Headern oft).
- **Fehlender Master:** der Lauf bricht nicht ab. Er rechnet die beste mögliche Stufe – `bfd` → `bf` → `b` (nur Bias) → `raw` – und meldet in Konsole und `calib.json` (`mode_effektiv`, `warnungen`, `gesucht`), welcher Master fehlte und wonach gesucht wurde (Filter, Binning, Größe, Kamera, Gain/Offset). Auf dem Ergebnisblatt steht die tatsächlich verwendete Kalibrierung.
- **Plate-Solving:** `transit run` löst Frames ohne WCS jetzt selbst (ASTAP, Kopien in `SOLVED\`).

---

## 19. Kommentar für den ExoClock-Upload

`.\transit kommentar <Messordner>` (Standard: gültiger Lauf, sonst `--lauf`) erzeugt einen **kurzen** englischen Kommentar und kopiert ihn in die Zwischenablage. Er steht auch am Ende von `exoclock_formular.txt` (bei jedem `export`) und in der GUI im Bereich **ExoClock-Upload** (Formularwerte, Textfeld, Knöpfe „Kommentar kopieren“ und „Upload-Ordner öffnen“).

Inhalt: nur, was ExoClock nicht selbst sieht – höchstens ca. 300 Zeichen, wichtigstes zuerst: Meridian-Flip im Transit und wie korrigiert; von Hand ausgeschlossene Vergleichssterne; fehlender Flat oder Flat älter als 60 Tage; wechselnde Belichtungszeiten; sehr kurze Belichtung/Szintillation oder große Zeitunsicherheit; Datenlücken; Filter nicht im FITS-Header. Nicht enthalten: Bildzahl, Belichtung, Zeitformat, eigene Fitwerte, Standardmethodik. Ist nichts besonders: „No special remarks.“ Eigener Zusatz (z. B. „Replaces my earlier submission.“): `[export] kommentar_zusatz = "…"` in `RESULT\transit.toml` oder `lauf.toml`. Bereits von Hand angepasste Formular-Kommentare werden nur überschrieben, wenn `export` für diesen Lauf neu läuft.

## 20. Beobachtungsvorschlag (`transit plan`)

`transit plan` schlägt für die nächsten Nächte (Standard 3) Transits vor, die vom eigenen Standort mit dem eigenen Teleskop sinnvoll messbar sind. In der Oberfläche steht dasselbe ganz oben unter „Beobachtungsvorschlag“, mit Höhenkurven pro Nacht.

**Woher:** alle Planeten der ExoClock-Datenbank (derselbe Cache wie bei `inventory`), Transitzeiten aus deren Ephemeride, umgerechnet von BJD_TDB auf UTC. Standort aus `[site]`, Öffnung aus `fit.aperture_cm`, Pixelskala aus `[camera]`.

**Bedingungen (sonst nicht in der Liste):**
- Transit vollständig, inklusive 3 σ der Tc-Unsicherheit, in der Dunkelheit (`planning.sonne_max`) über `planning.alt_min`
- vor und nach dem Transit mindestens die halbe `baseline_min_h` beobachtbar
- ExoClock-Mindestöffnung ≤ eigene Öffnung (`planning.exoclock_oeffnung`)
- Transittiefe ≥ `tiefe_snr_min` × geschätztes Rauschen eines 10-min-Bins (Photonen + Himmel + Szintillation wie bei `fit.weights = "modell"`, ×1.3 für das Ensemble, plus `rauschboden_ppt`)

**Hinweise (Abzug im Score):** Meridian-Flip weniger als `flip_min_before_ingress_h` vor dem Ingress bis 15 min nach dem Egress (×0.75), Baseline kürzer als `baseline_min_h` (×0.7), Airmass über `airmass_max_baseline` (×0.8), heller Mond näher als `mond_abstand_min` (×0.85), mit `--vergleich` weniger als `search.n_min` Vergleichssterne im Feld (×0.6). Ohne Abzug: helle Sterne, Taugefahr, Böen, Regenrisiko.

**Score** = ExoClock-Priorität (alert 1, high 0.85, medium 0.6, low 0.35) × Genauigkeit (0.5 … 1, voll ab dreifachem Mindest-SNR) × (1 − mittlere Bewölkung im Beobachtungsfenster) × Abzüge, auf 0 … 100.

**Wetter:** Open-Meteo (kostenlos, ohne Schlüssel), stündlich: Gesamtbewölkung sowie tiefe, mittlere und hohe Wolken, Regenwahrscheinlichkeit, Luftfeuchte und Böen. Der Standort wird dabei auf 0.1° gerundet übertragen. Die Antwort wird eine Stunde in `cache\wetter.json` gehalten. Ohne Netz läuft der Vorschlag ohne Wetter.

**Ergebnis:** `plan\plan.json` (für die Oberfläche) und `plan\plan.csv`. Beide enthalten keine Standortkoordinaten.

Die Rauschschätzung ist grob, sie dient nur der Rangfolge. Wer `rauschboden_ppt` und `himmel_mag` an die eigenen OOT-RMS-Werte anpasst, bekommt realistischere SNR-Werte.

---

## 21. Farbkameras (Bayer/OSC)

**Problem.** Das Rohbild einer Farbkamera ist ein Mosaik aus roten, grünen und blauen Pixeln (`BAYERPAT = RGGB`). Der Himmel hat darin drei Niveaus, bei KPS-1b (ATR2600C, 2026-06-05) etwa R 759, G 851 und B 662 ADU. Der Median im Himmelsring springt dann von Bild zu Bild zwischen diesen Werten. Der Fehler wächst mit der Aperturfläche: zwei helle Vergleichssterne streuten gegeneinander um 17 ppt bei r = 8 px und um 108 ppt bei r = 24 px. Der Transit verschwand im Rauschen (O-C +41 ± 181 min).

**Lösung.** Nach der Kalibrierung (jeder Pixel mit seinem eigenen Bias/Flat) wird jedes 2×2-Feld zu einem Superpixel summiert, wie in HOPS (`colour_camera_mode`, `bin_fits 2`). Ein Superpixel enthält immer R + 2 G + B, das Muster ist weg. Die Photometrie läuft auf diesem halb so großen Bild.

**Was gleich bleibt.** Radien, Himmelsring, Positionen, FWHM und Himmel pro Pixel stehen im Cube weiter in Bildpixeln. Konfiguration, AIJ-Export, Feldbild und Ergebnisblatt brauchen also keine Umrechnung. Die Sättigungsprüfung nutzt den hellsten Einzelpixel im Rohbild.

**Steuerung.** `[camera] farbkamera = "auto"` (Standard) erkennt Farbkameras am Header-Schlüssel `BAYERPAT`; das Log zeigt dann „Farbkamera (BAYERPAT RGGB): Photometrie in 2x2-Superpixeln“. In der GUI unter „Erweitert“ → Farbkamera.

**Gaia-Feld wiederverwenden.** Fehlt einem neuen Lauf `gaia_field.csv`, übernimmt `cube` die Datei des jüngsten anderen Laufs derselben Messung (gleiches Feld) und fragt Gaia gar nicht erst ab. Nur die erste Auswertung einer Nacht braucht also Netz.

**Ergebnis KPS-1b.** Siehe Lauf `kps_bayer`: OOT-RMS 4,4 ppt statt 11,5 ppt.


## Vergleichssterne auf Variabilität prüfen

Ein Vergleichsstern, der selbst schwankt (Pulsation, Flecken, Flares), verfälscht die relative Lichtkurve des Ziels. Die Prüfung läuft in zwei Stufen.

**Stufe 1: Kataloge (`cube`).** Bekannte Veränderliche werden gar nicht erst Kandidaten: Gaia-DR3-Flag `VARIABLE` und Einträge im AAVSO-Katalog VSX (VizieR `B/vsx/vsx`, innerhalb 5″; Einträge „konstant“ oder „Duplikat“ zählen nicht). Der Grund steht mit Typ, Amplitude und Periode in `candidates_rejected.csv` und im Protokoll. VSX wird wie Gaia über VizieR (CDS, dann Harvard) abgefragt und pro Lauf in `vsx_field.csv` gespeichert. Ist VSX nicht erreichbar, läuft die Auswahl mit einer Warnung ohne VSX weiter. Abschalten: `[comps] katalog_variable = false`.

Die Kataloge sind lückenhaft: Das Gaia-Flag ist für die meisten Sterne leer, und Pulsatoren mit wenigen mmag Amplitude fehlen oft auch in VSX. Ein Stern ohne Katalogeintrag ist also nicht sicher ruhig. Dafür gibt es Stufe 2.

**Stufe 2: eigene Lichtkurve (`compsearch`, wie HOPS und AIJ).** Für jeden Kandidaten wird die Lichtkurve „Stern ÷ Summe der übrigen Kandidaten“ gebildet und mit derselben Basislinie wie der Transitfit detrendet (Airmass, Flip-Stufe). Daraus:

| Kennzahl | Bedeutung |
|---|---|
| RMS | Streuung pro Bild (weißes und rotes Rauschen) |
| 10-min-Streuung | Streuung der 10-Minuten-Mittel: weißes Rauschen mittelt sich weg, Pulsation, Flecken und Flares bleiben |
| Ruhe | 10-min-Streuung ÷ Median aller Kandidaten; 1 = typisch, 3 = dreimal unruhiger |
| beta | Rotrausch-Faktor (1 = rein zufällig) |

Ein Stern gilt als **variabel**, wenn Ruhe > `variab_sigma` (3) **und** beta > `variab_beta` (1,5). Weil die Ruhe relativ zum Median ist, macht eine schlechte Nacht nicht alle Sterne „variabel“. Verrauschte und variable Sterne werden in einem zweiten Durchgang aus der Referenz der anderen genommen, damit ein variabler Stern die übrigen nicht ansteckt. Variable Sterne kommen nicht in die Ensemble-Suche; der Grund steht im Protokoll, in `compsearch.json` (`prefilter`), auf Seite 2 des Ergebnisblatts und in `summary.md`. Abschalten: `[search] variab_check = false`.

**Bild `vergleichssterne_lc.png`** (nach `compsearch`, nach `report` mit markiertem Ensemble): ein Feld pro Kandidat, alle auf derselben Skala, das Transitfenster grau. Rot = verworfen, blau = im besten Ensemble, schwarz = brauchbar. In der Oberfläche unter „Vergleichen → Vergleichssterne“ und in „Erweitert → Vergleichssterne“ (Spalte **Ruhe**).

**Grenze.** Eine Schwankung mit Periode viel länger als die Nacht sieht wie ein Trend aus und wird vom Airmass-Term geschluckt; sie ist nur über Kataloge oder mehrere Nächte erkennbar.

**Warum ähnliche Farbe (`color_tol`).** Die Luft dämpft blaues Licht stärker als rotes. In einem breiten Filter (Luminanz, Clear) ändert sich das Verhältnis Ziel ÷ Vergleich deshalb mit der Airmass um etwa k″ × Δ(Farbe) × Airmass. Mit k″ grob 0,01–0,05 mag pro Airmass und Farbeinheit sind das bei ΔBP-RP = 0,5 etwa 5–25 ppt pro Einheit Airmass (Größenordnung, nicht gemessen). Das ist fast linear in der Airmass und wird vom Airmass-Term des Fits aufgefangen. Schleierwolken und Feuchte ändern die Durchlässigkeit aber farbabhängig und unabhängig von der Airmass; das kürzt sich nur bei ähnlicher Farbe heraus. Der Spektraltyp zählt nur indirekt: Sterne im Instabilitätsstreifen (BP-RP etwa 0,2–0,7) sind oft δ-Scuti-Pulsatoren, M-Zwerge zeigen Flares.

