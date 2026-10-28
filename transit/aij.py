"""AstroImageJ export: measurement table (AIJ column names, tab separated) + .plotcfg (Multi-Plot layout) + macro.

RESULT\\<lauf>\\aij\\<Planet>_<Datum>_<lauf>_Measurements.xls      table as AIJ writes it (Label, J.D.-2400000, JD_UTC, ...)
RESULT\\<lauf>\\aij\\<Planet>_<Datum>_<lauf>_Measurements.plotcfg  same name -> AIJ loads it together with the table
RESULT\\<lauf>\\aij\\oeffnen.ijm                                  ImageJ macro: MultiPlot_.openDataAndConfig(<table>)
RESULT\\<lauf>\\aij\\LIESMICH.txt

The plot configuration is the user's own AIJ configuration (template in _pipeline\\aij_vorlage.plotcfg) with the
columns, curve offsets, markers and title of this run filled in.  Display only - nothing here feeds back into the fit.
"""
import glob
import os
import subprocess
import time

import numpy as np

from .config import PIPE_DIR

TEMPLATE = os.path.join(PIPE_DIR, "aij_vorlage.plotcfg")
AIJ_EXE_CANDIDATES = [r"C:\Program Files\AstroImageJ\AstroImageJ.exe", r"C:\AstroImageJ\AstroImageJ.exe",
                      os.path.expanduser(r"~\AstroImageJ\AstroImageJ.exe")]
SHOW_COMPS = 5                                             # comparison curves below the target curve
COMP_SHIFT0, COMP_SHIFT_STEP = -0.045, -0.005             # -> 0.955, 0.950, 0.945 ...


def find_aij():
    for p in AIJ_EXE_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def _template(log):
    if not os.path.exists(TEMPLATE):
        raise SystemExit(f"AIJ-Vorlage fehlt: {TEMPLATE} (eine .plotcfg aus AstroImageJ dorthin kopieren)")
    lines = open(TEMPLATE, encoding="latin-1").read().splitlines()
    head = [l for l in lines if l.startswith("#")]
    kv = {}
    for l in lines:
        if "=" in l and not l.startswith("#"):
            k, v = l.split("=", 1)
            kv[k] = v
    return head, kv


def _esc(v):
    """Java properties: escape ':' and '=' and backslashes in values."""
    return str(v).replace("\\", "\\\\").replace(":", "\\:").replace("=", "\\=")


def write_aij(m, n, c, fr, inv, log=print):
    best = fr["best"]
    r_px = best["radius"]
    ir = n.ir(r_px)
    idx = {nm: i for i, nm in enumerate(n.names)}
    ens = [idx[s] for s in best["comps"]]
    sel = n.sel
    F = c["flux"][sel][:, :, ir]; E = c["flux_err"][sel][:, :, ir]
    T, eT = F[:, 0], E[:, 0]
    C = F[:, ens]; eC = E[:, ens]
    totC = C.sum(1); etotC = np.sqrt((eC ** 2).sum(1))
    rel = {"T1": T / totC}
    relerr = {"T1": rel["T1"] * np.hypot(eT / T, etotC / totC)}
    labels = ["T1"] + [f"C{k + 2}" for k in range(len(ens))]
    for k, j in enumerate(ens):                             # AIJ: comp k relative to the sum of the other comps
        oth = totC - C[:, k]
        lab = labels[k + 1]
        rel[lab] = C[:, k] / oth
        relerr[lab] = rel[lab] * np.hypot(eC[:, k] / C[:, k], np.sqrt(etotC ** 2 - eC[:, k] ** 2) / oth)
    stars = [0] + ens
    jd = c["jd_utc_mid"][sel]
    files = c["frame_file"][sel]
    ann = m.cfg["photometry"]["annulus"]
    exp = np.full(sel.sum(), float(np.median(inv["exptimes"])))
    hp = m.path("headers.csv")
    if os.path.exists(hp):                                  # per-frame exposure (some nights mix exposure times)
        import csv
        ex = {r["file"]: float(r["EXPTIME"] or "nan") for r in csv.DictReader(open(hp, encoding="utf-8"))}
        exp = np.array([ex.get(str(f), np.nan) for f in files])
    cols = {"J.D.-2400000": jd - 2400000.0, "JD_UTC": jd, "BJD_TDB": c["bjd_tdb"][sel], "AIRMASS": c["airmass_calc"][sel],
            "CCD-TEMP": c["ccd_temp"][sel], "EXPTIME": exp, "FWHM_Mean": c["fwhm"][sel],
            "Source_Radius": (c["vap"][r_px]["r"][sel] if r_px in c.get("vap", {}) else np.full(sel.sum(), float(r_px))), "Sky_Rad(min)": np.full(sel.sum(), float(ann[0])),
            "Sky_Rad(max)": np.full(sel.sum(), float(ann[1])),
            "Meridian_Flip": c["east"][sel].astype(float)}
    for lab in labels:
        cols[f"rel_flux_{lab}"] = rel[lab]
    for lab in labels:
        cols[f"rel_flux_err_{lab}"] = relerr[lab]
    cols["tot_C_cnts"] = totC; cols["tot_C_err"] = etotC
    for lab, j in zip(labels, stars):
        cols[f"X(FITS)_{lab}"] = c["x"][sel][:, j] + 1          # AIJ FITS pixel convention (1-based)
        cols[f"Y(FITS)_{lab}"] = c["y"][sel][:, j] + 1
        cols[f"RA_{lab}"] = np.full(sel.sum(), float(c["star_ra"][j]) / 15)
        cols[f"DEC_{lab}"] = np.full(sel.sum(), float(c["star_dec"][j]))
        cols[f"Source-Sky_{lab}"] = F[:, j]
        cols[f"Source_Error_{lab}"] = E[:, j]
        cols[f"Peak_{lab}"] = c["peak_raw"][sel][:, j]
        cols[f"Sky/Pixel_{lab}"] = c["background"][sel][:, j]
        cols[f"FWHM_{lab}"] = c["fwhm_star"][sel][:, j]
    planet = inv["planet"]["name"]
    lauf = os.path.basename(m.out)
    from astropy.time import Time
    date = Time(c["jd_start"][sel].min(), format="jd").iso[:10]
    base = f"{planet}_{date}_{lauf}_Measurements"
    out = os.path.join(m.out, "aij")
    os.makedirs(out, exist_ok=True)
    tab = os.path.join(out, base + ".xls")
    names = list(cols)
    with open(tab, "w", newline="\r\n", encoding="utf-8") as fh:
        fh.write("Label\t" + "\t".join(names) + "\n")
        for i in range(sel.sum()):
            fh.write(str(files[i]) + "\t" + "\t".join(f"{cols[k][i]:.10g}" for k in names) + "\n")
    # ---------------- plot configuration from the user's own AIJ template
    head, kv = _template(log)
    pred = fr["ephemeris"]
    off = float(np.median(c["bjd_tdb"][sel] - jd))           # BJD_TDB - JD_UTC for this night
    x0 = np.floor(jd.min())
    frac = lambda b: round(b - off - x0, 5)                  # AIJ markers: x minus the integer day
    shown = labels[1:1 + SHOW_COMPS]
    mc = fr["mcmc"]
    kv.update({
        ".plot.title": f"{planet}  {date}", ".plot.useTitle": "true",
        ".plot.subtitle": f"{lauf}: {n.r_text(r_px)}, Ensemble {' '.join(best['comps'])}, O-C {mc['OC_min']:+.1f} min (transit)",
        ".plot.useSubtitle": "true",
        ".plot.xlabeldefault": "JD_UTC", ".plot.useXColumnName": "true",
        ".plot.vMarker1Value": frac(pred["ingress"]), ".plot.vMarker1TopText": "Predicted", ".plot.vMarker1BotText": "Ingress",
        ".plot.vMarker2Value": frac(pred["egress"]), ".plot.vMarker2TopText": "Predicted", ".plot.vMarker2BotText": "Egress",
        ".plot.dMarker1Value": round(jd.min() - x0 - 0.002, 5), ".plot.dMarker2Value": frac(pred["ingress"]),
        ".plot.dMarker3Value": frac(pred["egress"]), ".plot.dMarker4Value": round(jd.max() - x0 + 0.002, 5),
        ".plot.orbitalPeriod0": pred["P"],
        ".plot.detrendlabel[0][0]": "AIRMASS",
        ".plot.detrendlabel[0][1]": "Meridian_Flip" if n.flip_mode != "none" else "",
    })
    for k in range(8):
        on = k <= len(shown)
        kv[f".plot.plotY{k}"] = "true" if on else "false"
        kv[f".plot.xlabel{k}"] = "default"
        if not on:
            continue
        lab = "T1" if k == 0 else shown[k - 1]
        kv[f".plot.ylabel{k}"] = f"rel_flux_{lab}"
        kv[f".plot.oplabel{k}"] = f"source-sky_{lab}" if k else "source-sky_T1"
        kv[f".plot.useTransitFit{k}"] = "true" if k == 0 else "false"
        kv[f".plot.showModel{k}"] = "true" if k == 0 else "false"
        kv[f".plot.showResidual{k}"] = "true" if k == 0 else "false"
        kv[f".plot.customScaleFactor{k}"] = "1.0"
        kv[f".plot.customShiftFactor{k}"] = "0.0" if k == 0 else f"{COMP_SHIFT0 + COMP_SHIFT_STEP * (k - 1):.3f}"
        kv[f".plot.colorIndex{k}"] = str(7 + k)
        kv[f".plot.modelColorIndex{k}"] = str(7 + k)
        if k:
            kv[f".plot.detrendFitIndex{k}"] = "0"
    cfg = os.path.join(out, base + ".plotcfg")
    with open(cfg, "w", encoding="latin-1", newline="\n") as fh:
        fh.write("#AstroImageJ Plot Configuration (erzeugt von transit)\n#" + time.strftime("%a %b %d %H:%M:%S %Y") + "\n")
        for k in sorted(kv):
            fh.write(f"{k}={_esc(kv[k]) if kv[k] != '' else ''}\n")
    # ---------------- macro + readme
    ijm = os.path.join(out, "oeffnen.ijm")
    with open(ijm, "w", encoding="utf-8") as fh:
        fh.write("// von transit erzeugt: Multi-Plot starten, dann Messtabelle + gleichnamige .plotcfg laden\n"
                 "// (openDataAndConfig ohne offenes Multi-Plot wirft eine Exception - getestet mit AIJ 6.0.11)\n"
                 'call("ij.IJ.runPlugIn", "Astronomy.MultiPlot_", "");\nwait(4000);\n'
                 f'call("Astronomy.MultiPlot_.openDataAndConfig", "{tab.replace(chr(92), "/")}");\n')
    with open(os.path.join(out, "LIESMICH.txt"), "w", encoding="utf-8") as fh:
        fh.write(readme(planet, date, lauf, tab, cfg, shown, n.flip_mode != "none"))
    log(f"AIJ: {os.path.relpath(tab, m.root)} (+ .plotcfg, oeffnen.ijm, LIESMICH.txt)")
    return tab, cfg, ijm


def readme(planet, date, lauf, tab, cfg, shown, flip):
    return f"""AstroImageJ-Dateien fuer {planet}, Nacht {date}, Lauf {lauf}
{'=' * 70}

Inhalt
  {os.path.basename(tab)}
      Messtabelle im AIJ-Format (tab-getrennt): JD_UTC (Belichtungsmitte), BJD_TDB, AIRMASS,
      rel_flux_T1 (Ziel / Summe der Vergleichssterne), rel_flux_C2.. (Vergleichsstern / Summe der
      anderen), Fehler, Source-Sky, Peak, Sky/Pixel, FWHM, Pixelpositionen, Meridian_Flip (0/1).
  {os.path.basename(cfg)}
      Multi-Plot-Konfiguration (deine eigene AIJ-Einstellung als Vorlage): oben rel_flux_T1 mit
      Transitmodell, darunter {len(shown)} Vergleichssterne ({', '.join(shown)}) versetzt um
      -0.045, -0.050, ...; rote Marker "Predicted Ingress/Egress"; x-Achse JD_UTC; Detrending AIRMASS
      {'+ Meridian_Flip' if flip else ''}.
  oeffnen.ijm   Makro, das beides zusammen laedt.

Oeffnen - automatisch
  transit aij <Messordner> --oeffnen        (startet AstroImageJ und laedt Tabelle + Konfiguration)
  In PowerShell im Ordner _pipeline:  .\\transit aij <Messordner> --oeffnen

Oeffnen - von Hand in AstroImageJ
  1. AstroImageJ starten.
  2. In der AIJ-Leiste: Multi-Plot-Symbol (Diagramm) -> es oeffnet sich "Multi-plot Main".
  3. Dort: File -> "Open table and plot configuration from file..." und die .xls-Datei waehlen.
     AIJ laedt die gleichnamige .plotcfg automatisch dazu.
     (Alternativ: "Open table from file..." und danach "Open plot configuration from file...".)
  4. Oder: Makro ausfuehren: Plugins -> Macros -> Run... -> oeffnen.ijm
  Hinweis: Die Tabelle ist nur eine Ansicht der transit-Messung. Ein Fit in AIJ ist eine eigene,
  unabhaengige Auswertung; fuer ExoClock gilt die Datei direkt unter RESULT\\.
"""


def cmd_aij(a):
    from .config import Measurement
    from . import cli
    from .ergebnisblatt import VALID, logbook_read, same_run
    root = os.path.abspath(a.messordner)
    lauf = a.lauf
    if not lauf:
        rows = [r for r in logbook_read() if os.path.normcase(root) in (os.path.normcase(r["messordner"]), os.path.normcase(r.get("archiv") or "-"))
                and r["status"] == VALID]
        if not rows:
            raise SystemExit("Kein gueltiger Lauf im Logbuch - --lauf <name> angeben")
        lauf = rows[0]["lauf"]
    m = Measurement(root, lauf)
    tabs = sorted(glob.glob(os.path.join(m.out, "aij", "*_Measurements.xls")))
    if a.neu or not tabs:
        import types
        import json
        cubes = glob.glob(m.path("cube_*.npz"))
        if not cubes:
            raise SystemExit(f"kein Cube in {m.out}")
        mode = os.path.basename(cubes[0])[5:-4]
        n, c, pred, par = cli.night_from(m, types.SimpleNamespace(mode=mode))
        n.prefilter(); n.flip_offsets()
        fr = json.load(open(m.path("fit.json"), encoding="utf-8"))
        inv = json.load(open(m.path("inventory.json"), encoding="utf-8"))
        tab, cfg, ijm = write_aij(m, n, c, fr, inv, print)
    else:
        tab = tabs[0]; ijm = os.path.join(m.out, "aij", "oeffnen.ijm")
        print(f"AIJ-Dateien vorhanden: {tab} (neu erzeugen: --neu)")
    if a.oeffnen:
        exe = find_aij()
        if not exe:
            raise SystemExit("AstroImageJ nicht gefunden (gesucht: " + ", ".join(AIJ_EXE_CANDIDATES) + ")")
        subprocess.Popen([exe, "-macro", ijm], cwd=os.path.dirname(exe))
        print(f"AstroImageJ gestartet: {exe} -macro {ijm}")
