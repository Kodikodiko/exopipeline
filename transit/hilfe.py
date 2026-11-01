"""German help topics: transit hilfe <thema>.  The full manual is HANDBUCH.md in the _pipeline folder."""
import os
import re

from .config import PIPE_DIR

THEMEN = {
    "start": """SCHNELLSTART
  1. Lights einer Nacht liegen in <Messordner>\\LIGHTS (oder _work). Dort wird nie geschrieben.
  2. transit inventory <Messordner>     Header, Pruefsummen, Ephemeride, Planungs-Warnungen,
                                         legt RESULT\\transit.toml an
  3. transit solve <Messordner>          nur falls Frames ohne WCS (ASTAP, Kopien in SOLVED\\)
  4. transit calibrate <Messordner>      passende Master suchen (Bias/Flat/Dark)
  5. transit cube <Messordner>           Gaia-Vergleichssterne + Photometrie
  6. transit compsearch <Messordner>     beste Vergleichsstern-Ensembles
  7. transit fit <Messordner>            Transit-Fit, Robustheit, MCMC
  8. transit export <Messordner>         ExoClock-Datei + Formularwerte + AIJ-radec
  9. transit report <Messordner>         Plots + summary.md
  Oder alles auf einmal: transit run <Messordner>   (fertige Schritte werden uebersprungen)
  Fortschritt aus einem zweiten Fenster: transit status <Messordner>   (transit hilfe fortschritt)
  Ergebnisse: <Messordner>\\RESULT\\pipeline\\
  PowerShell: im Ordner _pipeline mit .\\ davor, z. B.  .\\transit run <Messordner>
  Bedienoberflaeche: Doppelklick auf _pipeline\\transit_gui.cmd""",
    "ablauf": """ABLAUF EINER NACHT (Reihenfolge und Abhaengigkeiten)
  inventory -> (solve) -> calibrate -> cube -> compsearch -> fit -> export -> report
  Jeder Schritt liest die Dateien des vorherigen aus RESULT\\pipeline\\:
    inventory.json, headers.csv  ->  calib.json  ->  candidates.csv, cube_<modus>.npz
    -> compsearch.json  ->  fit.json, top50.csv  ->  Exportdateien, summary.md
  Vor und nach jedem Schritt werden die Pruefsummen der Lights kontrolliert.""",
    "ordner": """ORDNERSTRUKTUR
  <Messordner>\\LIGHTS oder _work   Original-Lights, NUR LESEN (Schreibversuch -> Abbruch)
  <Messordner>\\SOLVED              geloeste Kopien (transit solve)
  <Messordner>\\CALIBRATED          kalibrierte Frames (nur mit transit calibrate --write)
  <Messordner>\\AIJ                 fuer AstroImageJ-Projekte (frei nutzbar)
  <Messordner>\\RESULT\\transit.toml   Einstellungen dieser Messung
  <Messordner>\\RESULT\\pipeline\\     alle Ergebnisse des Werkzeugs (--out aendert den Namen)
  <Messordner>\\RESULT\\lights_checksums.json   Pruefsummen der Lights
  _pipeline\\config.local.toml     globale Standardwerte (Vorlage: config.example.toml)""",
    "parameter": """PARAMETER: siehe HANDBUCH.md Kapitel 4 (alle Werte mit Standard und Wirkung).
  Wichtigste: camera.saturation_adu (60000), photometry.radii, search.radii (14-20),
  fit.fix_geometry (true), fit.flip (prior), calib.mode (bf), search.aij_table / exclude_frames.""",
    "flip": """MERIDIAN-FLIP
  Nach dem Flip liegt das Feld um 180 Grad gedreht auf dem Sensor; Flat-Reste erzeugen eine Stufe
  im relativen Fluss (hier -4 bis +8 ppt pro Stern). Das Werkzeug misst die Stufe an allen
  Vergleichssternen in einem Fenster um den Flip (fit.flip_window_h), sagt sie fuer das Ziel voraus
  (Ebene in x/y) und nutzt sie als Gauss-Prior (fit.flip = "prior"). "free" = freier Parameter,
  "none" = ignorieren. Liegt der Flip weniger als 1 h vor dem Ingress, warnt inventory (CRIT).
  Abhilfe beim Beobachten: Flip vor die Baseline legen oder ueber den Meridian nachfuehren.""",
    "saettigung": """SAETTIGUNG / LINEARITAET
  camera.saturation_adu (60000): Frames, in denen Ziel oder ein Ensemble-Stern darueber liegt,
  werden verworfen; Vergleichssterne, die in >5 % der Frames darueber liegen, fliegen raus.
  camera.linearity_warn_adu (45000): nur Hinweis. Fuer die ATR2600M (Gain 100) wurde aus den
  TOI-628b-Daten Linearitaet besser 0.2 % bis 60000 ADU gemessen (transit report -> linearity.png).""",
    "airmass": """AIRMASS
  NINA schreibt AIRMASS aus der Montierungsposition; die ist je nach Pier-Seite um bis zu 0.7 Grad
  falsch -> Sprung beim Flip und Fehler bei tiefem Stand. Das Werkzeug berechnet die Airmass immer
  aus den Zielkoordinaten (astropy, Standort aus config/Header). inventory zeigt die Abweichung.""",
    "zeit": """ZEIT / BJD_TDB
  Belichtungsmitte aus DATE-AVG (sonst DATE-OBS + EXPTIME/2), BJD_TDB mit astropy
  (Lichtlaufzeit baryzentrisch, Schaltsekunden aus der IANA-Tabelle, TAI-UTC = 37 s seit 2017).
  ExoClock-Export: JD_UTC des Belichtungsstarts (empfohlen von ExoClock/HOPS).""",
    "kalibrierung": """KALIBRIERUNG
  calib.library wird nach Mastern durchsucht (Dateiname MASTER oder STACKCNT/NCOMBINE).
  Passend = gleiche Kamera, Gain, Offset, Groesse; Flat mit gleichem Filter; Dark mit gleicher
  Belichtung; naechstes Datum. Siril-Master (0..1) werden x65535 skaliert.
  Modi: raw | bf (Bias+Flat, Standard) | bfd (+ Dark mit Skalierungsfaktor aus Hot-Pixeln).
  Wenn die Kamera die Solltemperatur nicht erreicht hat, passt kein Dark -> bf verwenden.""",
    "vergleichssterne": """VERGLEICHSSTERNE
  Kandidaten aus Gaia DR3: G im Fenster [Ziel-0.5, Ziel+2], BP-RP +-0.5, >= 80 px vom Rand,
  kein Nachbar heller als G+3 innerhalb 40 px, keine bekannten Veraenderlichen (Gaia-Flag VARIABLE,
  AAVSO VSX innerhalb 5"), max. 30 (comps.*). Optional die Sterne einer AIJ-.apertures-Datei
  (comps.aij_apertures). compsearch: Vorfilter (RMS/Trend > 3x Median), Lichtkurve jedes Sterns gegen
  die uebrigen (Airmass/Flip detrendet, wie HOPS): variabel bei Streuung der 10-min-Mittel > 3x Median
  UND beta > 1.5 -> verworfen, Bild vergleichssterne_lc.png; dann gierige Vor-/Rueckwaertsauswahl
  (3-12 Sterne) je Radius nach OOT-RMS.""",
    "aij": """ASTROIMAGEJ-EINSTELLUNGEN (CCD Data Processor -> General FITS Header Settings)
  Zielkoordinaten-Quelle: "FITS header target RA/DEC (J2000)" mit OBJCTRA / OBJCTDEC
     (nicht "target name": "TOI-628b" wird bei SIMBAD evtl. nicht gefunden).
  Standort-Quelle: FITS header latitude/longitude, SITELAT / SITELONG, Ost positiv.
  RA/Dec Epoch-of-date Speichern als RA_OBJ / DEC_OBJ (sonst ueberschreibt AIJ NINAs J2000-Werte).
  Hoehe: AIJ liest keine Hoehe -> im DP Coordinate Converter 640 m eintragen.
  Zeit: AIJ nimmt DATE-OBS + EXPTIME/2 (Belichtungsmitte) - korrekt.
  Schaltsekunden: DP Coordinate Converter "auto leap seconds" an, letzter Eintrag 2017-01-01 = 37 s.
  Wichtig: CCD Data Processor MIT "calculate headers" auf die zu messenden Frames anwenden,
  sonst bleiben BJD_TDB/JD_UTC leer (BJD_TDB = 0 in der Messtabelle).
  radec-Datei des besten Ensembles: transit export -> *_best_ensemble.radec.txt""",
    "exoclock": """EXOCLOCK-UPLOAD (das Werkzeug laedt NICHTS hoch)
  Datei: *_exoclock_JDUTC.txt  (JD_UTC Belichtungsstart, relativer Fluss, Fehler;
  NICHT airmass-detrendet, Flip-Stufe korrigiert). Formular: Time format JD_UTC, Time stamp
  Exposure start, Flux format Flux, Filter Luminance (fuer L), Belichtung in s.
  Alle Werte zum Kopieren: exoclock_formular.txt. Upload: https://www.exoclock.space/upload/ (Login).""",
    "fortschritt": """FORTSCHRITT, STATUS, FORTSETZEN (Handbuch Kapitel 10)
  Konsole: Balken mit %, Restzeit und Ende (Ortszeit CEST/CET) fuer cube, compsearch, fit, MCMC.
           Die Restzeit der Fits enthaelt die geschaetzte MCMC-Dauer ("inkl. MCMC").
  transit status <Messordner> [-v]   alle Laeufe in RESULT\\: Schritt, %, fertig ca., haengt?
           haengt? JA = Prozess beendet oder > 120 s kein Lebenszeichen; steht? = 15 min kein Fortschritt
  RESULT\\<lauf>\\status.json     alle 10 s: Schritt, Prozent, ETA, heartbeat, PID
  RESULT\\<lauf>\\run.log         jede Zeile mit Zeitstempel; --verbose (-v) fuer Debug-Zeilen
  RESULT\\<lauf>\\run_state.json  fertige Schritte mit Parametern -> Fortsetzen
  transit run <Messordner>   ueberspringt fertige Schritte und macht beim ersten fehlenden weiter
           --from fit = ab fit neu, --force = alles neu
  --toast  Windows-Benachrichtigung am Ende (oder [progress] toast = true), ohne Installation""",
    "parallel": """GESCHWINDIGKEIT / PARALLEL (Handbuch Kapitel 11)
  --workers N (-j N) bei jedem Befehl; Standard [run] workers = 0 -> Kerne - 2 (30). 1 = seriell wie frueher.
  Zwei Auswertungen gleichzeitig: jede mit --workers 15.
  cube: Frames auf bis zu [run] cube_workers (8) Prozesse, Ergebnis bitgenau gleich.
  fit: jede Top-Kombination ein Auftrag (identische Ergebnisse); MCMC als mehrere Ketten
       (30000 Schritte -> 15 x 2000), Konvergenz per Gelman-Rubin R-hat (< 1.05 ok, sonst --mcmc-steps erhoehen).
  Transitmodell rechnet nur die vom Planetenrand geschnittenen Ringe: identisch, ca. 3x schneller.
  TOI-628b: cube 75 s -> 20 s, fit 515 s -> 18 s.""",
    "ergebnisblatt": """ERGEBNISBLATT (Handbuch Kapitel 12)
  transit report erzeugt RESULT\\<lauf>\\ergebnisblatt.png / .pdf / .html, Kopie in exoclock_paket\\
  Inhalt: Lichtkurve (Einzelpunkte grau, 10-min-Mittel, Modell, Residuen, Kontakte gemessen/vorhergesagt),
    Tabelle "Dein Wert vs. Literatur" mit Abweichung in sigma und Ampel (gruen < 2, gelb 2-3, rot > 3),
    massstaeblicher Stern (Farbe aus Teff) mit Planet (gemessenes Rp/R* und b, Literatur gestrichelt), Jupiter und Erde,
    O-C aller eigenen Messungen (_pipeline\\logbuch.csv),
    Planetenprofil (Literatur), Fusszeile mit Geraet/Ort/Version.
  Seite 2 (ergebnisblatt_feld.png, PDF Seite 2): gestretchtes Feldbild, Norden oben/Osten links, Kompass, 10'-Massstab;
    Ziel rot beschriftet, Vergleichssterne C1.. blau in Aperturgroesse, nicht genutzte grau, verworfene x.
    Tabelle: Gaia-ID, RA/Dec, Abstand, G/dG, BP-RP/dFarbe, Peak, RUWE, Variabilitaet, Nachbarn < 10",
    eigene Streuung, Ensemble-Anteil, Jackknife-dO-C, Begruendung; dazu verworfene Kandidaten mit Grund.
    RUWE/Variabilitaet: Gaia-Archiv, Cache RESULT\\<lauf>\\gaia_details.json.
  Literatur: ExoClock (Cache) + NASA Exoplanet Archive (Cache 30 Tage, _pipeline\\cache\\nasa_*.json).
  Ehrlichkeitsregel: das Blatt zeigt nur an. Kein Auswahlschritt benutzt Literatur-Tiefe oder -Tc.
  Rp/R*-Drift wie ExoClock: (Rp/R* - Lit)/Wurzel(s^2+s_Lit^2), Ampel gruen < 2, gelb 2-3, rot >= 3 (ExoClock lehnt ab).
  Optionen fuer Problemnaechte: [comps] exclude_stars, [search] airmass_max / symmetry_weight, [fit] airmass_order
    (am besten pro Lauf in RESULT\\<lauf>\\lauf.toml).
  Tiefe > 3 sigma daneben -> Warnung mit Pruefung: Blend (Gaia-Nachbarn), Nichtlinearitaet, Airmass-Kopplung,
    kurze Baseline, Flip-Prior.
  Logbuch: pro Planet und Nacht genau ein Lauf gueltig (O-C farbig, Upload-Paket), andere = Varianten (grau,
    Paket-Dateien NICHT_HOCHLADEN_...). Waehlen: transit logbuch <Messordner> --gueltig <lauf>
  Upload-Datei: <Planet>_<Datum>_<lauf>_exoclock_JDUTC.txt; Formular beginnt mit DIESE DATEI HOCHLADEN: <Pfad>.
  [observer] name / telescope / camera in transit.toml fuer die Fusszeile; [report] bin_min fuer die Mittelwerte.""",
    "archiv": """ARCHIVIEREN (Handbuch Kapitel 13)
  transit archiv <Messordner> --ziel <NAS-Pfad> --probe      Trockenlauf
  transit archiv <Messordner> --ziel <NAS-Pfad>              kopieren, SHA-256 aller Dateien pruefen, Logbuch: Archivpfad
  transit archiv <Messordner> --ziel <NAS-Pfad> --loeschen   danach lokal loeschen (nur wenn alle Pruefsummen stimmen)
  Lokal bleiben: _pipeline (Code, cache, logbuch.csv). Die O-C-Grafik liest nur das Logbuch.
  Logbuch-Spalten nachtragen: transit logbuch <Messordner> --nachtragen""",
    "planung": """BEOBACHTUNGSVORSCHLAG (transit plan)
  transit plan                 beobachtbare Transits der naechsten 3 Naechte, mit Wetter
  transit plan -n 5 --top 5    5 Naechte, je 5 Vorschlaege
  transit plan --prioritaet alert high   nur dringende ExoClock-Ziele
  transit plan --vergleich 5   fuer die besten 5 pro Nacht Vergleichssterne bei Gaia zaehlen
  transit plan --ohne-wetter   ohne Open-Meteo
  Bedingungen: ganzer Transit (+-3 sigma Tc) und mindestens die halbe Baseline in der Dunkelheit
  (planning.sonne_max) ueber planning.alt_min; ExoClock-Mindestoeffnung <= fit.aperture_cm;
  Tiefe >= planning.tiefe_snr_min x geschaetztes Rauschen eines 10-min-Bins.
  Score = Prioritaet x Genauigkeit x (1 - Bewoelkung) x Abzuege (Flip, kurze Baseline, Airmass, Mond).
  Ergebnis: plan\\plan.json, plan\\plan.csv; in der Oberflaeche oben unter "Beobachtungsvorschlag".""",
    "warnungen": """WARNUNGEN UND ABHILFE
  [CRIT] Meridian-Flip im/nahe Transit  -> fit.flip = prior; kuenftig Flip verlegen
  [WARN] Baseline zu kurz / zu hohe Airmass -> laengere Sequenz, Transit nahe Kulmination
  [WARN] Header-AIRMASS weicht ab -> wird automatisch ersetzt
  [WARN] Kameratemperatur nicht gehalten -> calib.mode = bf
  [WARN] Ziel-Peak > Saettigung -> kuerzer belichten / defokussieren
  [WARN] Frames ohne WCS -> transit solve
  Abbruch "Light-Dateien veraendert" -> jemand hat Lights geaendert; Pruefsummen neu: transit inventory""",
}


def show(thema=""):
    t = (thema or "").lower().replace("ä", "ae").replace("ü", "ue").replace("ö", "oe")
    if not t:
        print("transit hilfe <thema>   Themen: " + ", ".join(THEMEN))
        print(f"Handbuch: {os.path.join(PIPE_DIR, 'HANDBUCH.md')}")
        print("Hilfe zu einem Befehl: transit <befehl> --help")
        return
    if t in THEMEN:
        print(THEMEN[t]); return
    hb = os.path.join(PIPE_DIR, "HANDBUCH.md")
    if os.path.exists(hb):
        txt = open(hb, encoding="utf-8").read()
        hits = [s for s in re.split(r"\n(?=#)", txt) if t in s.lower()]
        if hits:
            print("\n\n".join(hits[:3])); return
    print(f"Kein Thema '{thema}'. Themen: " + ", ".join(THEMEN))
