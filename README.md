# transit – Exoplaneten-Transits auswerten

`transit` führt eine Beobachtungsnacht nachvollziehbar von den Light-Frames bis zur Lichtkurve und zur
ExoClock-Upload-Datei: Kalibrierung, Plate-Solving, Mehrfachapertur-Photometrie, automatische Suche nach
Vergleichssternen, Transit-Fit (MCMC) mit Airmass-Detrending und Meridian-Flip-Korrektur, Ergebnisblatt und Logbuch.
Bedienung über eine Browser-Oberfläche oder die Kommandozeile (Windows).

## Voraussetzungen

- Windows, Python **3.11 oder neuer** (getestet mit 3.13)
- Pakete aus `requirements.txt`: numpy, scipy, astropy, astroquery, photutils, matplotlib
- [ASTAP](https://www.hnsky.org/astap.htm) mit Sternkatalog (z. B. D50) für das Plate-Solving
- optional: [AstroImageJ](https://www.astro.louisville.edu/software/astroimagej/) zum Ansehen/Vergleichen der Ergebnisse
- Internet für Gaia-, ExoClock- und NASA-Exoplanet-Archive-Abfragen (Ergebnisse werden in `cache\` zwischengespeichert)

## Installation

```
git clone https://github.com/Kodikodiko/exopipeline.git _pipeline
cd _pipeline
python -m pip install -r requirements.txt
copy config.example.toml config.local.toml
```

Den Ordner am besten **innerhalb** des Ordners mit den Messungen ablegen (z. B. `C:\Photometry\auto\_pipeline`);
die Oberfläche sucht Messungen im übergeordneten Ordner und zusätzlich unter `[paths] archiv_wurzel`.

## Konfiguration

`config.local.toml` enthält die eigenen Werte und wird nicht ins Git aufgenommen. Anpassen:
`[site]` (Standort), `[camera]` (Gain, Ausleserauschen, Sättigung, Pixelgröße, Brennweite),
`[calib] library` (Ordner mit Master-Bias/Dark/Flat), `[paths] astap` und `archiv_wurzel`, `[observer]`.
Fehlt `config.local.toml`, wird `config.example.toml` verwendet. Einzelne Werte lassen sich pro Messung in
`<Messordner>\RESULT\transit.toml` überschreiben.

## Start

- Oberfläche: Doppelklick auf `transit_gui.cmd` (öffnet http://127.0.0.1:8765 im Browser)
- Kommandozeile (PowerShell im Pipeline-Ordner): `.\transit hilfe`, z. B. `.\transit run ..\WASP-52b`

Alles Weitere – Ordnerstruktur, Ablauf, alle Parameter, Erklärung der Ergebnisse – steht im [HANDBUCH](HANDBUCH.md).
Geplante Erweiterungen: [TODO](TODO.md).

## Lizenz

MIT, siehe [LICENSE](LICENSE).
