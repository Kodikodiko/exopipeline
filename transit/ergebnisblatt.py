"""Ergebnisblatt: one sheet (PNG/PDF/HTML) per run with light curve, own values vs. literature, to-scale sketch,
O-C logbook, field image, planet profile and observing details.

Honesty rule: this module only DISPLAYS results.  Nothing here feeds back into frame/star/ensemble selection or the
fit, and no step of the pipeline uses the literature depth or radius ratio.  (The fit does use the ExoClock geometry
a/R*, i when fix_geometry = true, and the predicted ingress/egress to define the out-of-transit window - both are
documented in HANDBUCH.md.)  Literature values appear only in the comparison columns.
"""
import base64
import csv
import io
import json
import math
import os
import shutil
import time

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Circle

from . import __version__
from .config import PIPE_DIR
from .model import flux_z, model

R_SUN_RJ = 695700 / 71492          # R_sun in R_Jup
R_SUN_RE = 695700 / 6371.0         # R_sun in R_Earth
G_CGS = 6.674e-8
RHO_SUN = 1.41                     # g/cm^3
LOGBOOK = os.path.join(PIPE_DIR, "logbuch.csv")
LOG_FIELDS = ["planet", "nacht", "messordner", "lauf", "status", "modus", "epoche", "tc_bjd_tdb", "tc_err_min", "oc_min",
              "oc_err_min", "tiefe_ppt", "tiefe_err_ppt", "rp_rs", "rp_rs_err", "drift", "sigma_ppt", "snr", "radius_px", "ensemble",
              "tc_pred_bjd", "periode_d", "ephemeride", "upload_datei", "eingetragen", "archiv"]
VALID, VARIANT = "gueltig", "variante"
GREEN, YELLOW, RED, GREY = "#7bc67b", "#f2d35b", "#e8776f", "#dddddd"


# ------------------------------------------------------------------ literature (NASA Exoplanet Archive, cached)
def nasa_params(name, max_age_days=30):
    """Planet/star parameters from the NASA Exoplanet Archive (pscomppars), cached in _pipeline\\cache."""
    nm = name if name.endswith(" b") or " " in name else name[:-1] + " " + name[-1]
    cache = os.path.join(PIPE_DIR, "cache", f"nasa_{nm.replace(' ', '_')}.json")
    if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < max_age_days * 86400:
        return json.load(open(cache, encoding="utf-8"))
    cols = ("pl_name,st_rad,st_raderr1,st_raderr2,pl_bmassj,pl_bmassjerr1,pl_eqt,disc_year,sy_vmag,st_teff,st_spectype,st_mass,"
            "st_dens,pl_radj,pl_radjerr1,pl_ratror,pl_ratdor,pl_orbincl,pl_imppar,pl_trandur,pl_trandep,pl_orbper")
    try:
        from astroquery.ipac.nexsci.nasa_exoplanet_archive import NasaExoplanetArchive
        r = NasaExoplanetArchive.query_criteria("pscomppars", select=cols, where=f"pl_name='{nm}'")
        if len(r) == 0:
            return {}
        d = {}
        for c in cols.split(","):
            v = r[c][0]
            if np.ma.is_masked(v):
                d[c] = None
            elif hasattr(v, "value"):
                d[c] = float(v.value)
            elif isinstance(v, (str, np.str_)):
                d[c] = str(v) or None
            else:
                d[c] = float(v)
        d["_abgerufen"] = time.strftime("%Y-%m-%d")
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        json.dump(d, open(cache, "w", encoding="utf-8"), indent=1)
        return d
    except Exception as e:                                # offline: old cache or nothing
        if os.path.exists(cache):
            return json.load(open(cache, encoding="utf-8"))
        print(f"  NASA Exoplanet Archive nicht erreichbar ({e}) - Literaturspalten teilweise leer")
        return {}


def exoclock_entry(name):
    from .ephem import exoclock_db
    db = exoclock_db()
    key = name if name in db else next((k for k in db if k.replace(" ", "").lower() == name.replace(" ", "").lower()), None)
    return db.get(key, {}) if key else {}


def star_rgb(teff):
    """Approximate colour of a black body of temperature teff (K) as RGB 0..1 (Tanner Helland's fit to the Planck
    colours); None -> a sun-like 5800 K."""
    t = min(max(float(teff or 5800), 2000), 40000) / 100
    r = 1.0 if t <= 66 else 329.698727446 * (t - 60) ** -0.1332047592 / 255
    g = (99.4708025861 * math.log(t) - 161.1195681661) / 255 if t <= 66 else 288.1221695283 * (t - 60) ** -0.0755148492 / 255
    b = 1.0 if t >= 66 else (0.0 if t <= 19 else (138.5177312231 * math.log(t - 10) - 305.0447927307) / 255)
    return np.clip([r, g, b], 0, 1)


def draw_sketch(ax, k, k_e, lit_k, b_geo, b_lit, b_f, b_fe, weak, u, R_s, teff):
    """To-scale view of the transit: star (colour from Teff, limb darkening u of the fit) on a dark sky, planet with the
    measured Rp/R* on the measured impact parameter b (free geometry fit), literature chord and Rp/R* for comparison,
    Jupiter and Earth to the same scale when R* is known.  The planet always sits on the b of this night's free fit as
    long as that has an error below 1 (weakly determined is labelled as such, not replaced); only when b is undetermined
    (fit on the i = 90 deg bound, no error) the geometry of the MCMC (b_geo, normally the literature) is used.
    b_lit = literature b."""
    ax.set_facecolor("#05070d")
    b_ok = bool(np.isfinite(b_f) and np.isfinite(b_fe) and 0 < b_fe < 1)
    b_lit = b_lit if b_lit is not None and np.isfinite(b_lit) else float("nan")
    b_show = b_f if b_ok else b_geo
    lo = min(-1.08, -b_show - k - 0.08)
    yy, xx = np.mgrid[-1:1:500j, -1:1:500j]
    rr = np.hypot(xx, yy); mu = np.sqrt(np.clip(1 - rr ** 2, 0, 1))
    I = np.clip(1 - u[0] * (1 - mu) - u[1] * (1 - mu) ** 2, 0, 1)
    rgb = np.dstack([I * c_ for c_ in star_rgb(teff)] + [(rr <= 1).astype(float)])
    ax.imshow(rgb, extent=(-1, 1, -1, 1), origin="lower", interpolation="bilinear", zorder=1)
    x0 = -0.35                                             # planet a little before mid-transit, chord visible on both sides
    if b_ok:                                               # measured chord with its 1-sigma range
        ax.axhspan(-(b_f + b_fe), -max(b_f - b_fe, 0.0), color="#7fd3ff", alpha=0.18, lw=0, zorder=2)
        ax.axhline(-b_f, color="#7fd3ff", lw=.9, zorder=3)
    if np.isfinite(b_lit):
        ax.axhline(-b_lit, color="w", lw=.7, ls="--", alpha=.75, zorder=3)
    ax.add_patch(Circle((x0, -b_show), k, color="#000000", zorder=4))
    if lit_k:
        ax.add_patch(Circle((x0, -b_show), lit_k, fill=False, color="w", lw=.7, ls=(0, (2, 2)), zorder=5))
    tt = f", Teff {teff:.0f} K" if teff else ""          # title: what the scale and the colour come from
    if R_s:
        rJ, rE = 1 / (R_s * R_SUN_RJ), 1 / (R_s * R_SUN_RE)
        ax.add_patch(Circle((0.72, 0.88), rJ, color="#c99b6d", zorder=4))
        ax.text(0.72, 0.88 - rJ - 0.03, "Jupiter", ha="center", va="top", fontsize=6.5, color="0.85")
        ax.add_patch(Circle((0.95, 0.88), max(rE, 0.006), color="#4f8fe0", zorder=4))
        ax.text(0.95, 0.88 - 0.04, "Erde", ha="center", va="top", fontsize=6.5, color="0.85")
        ax.set_title(f"Massstab: R* = {R_s:.2f} R_sun{tt}\n(Stern aus der Literatur, Planet gemessen)", fontsize=8.5)
    else:
        ax.set_title(f"Massstab: R* unbekannt{tt}\n(Planet relativ zum Stern, gemessen)", fontsize=8.5)
    ax.set_xlim(-1.08, 1.08); ax.set_ylim(lo, 1.08); ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    kt = f"Planet Rp/R* = {k:.3f}" + (f" ± {k_e:.3f}" if k_e and np.isfinite(k_e) else "") + " (gemessen)"
    if lit_k:
        kt += f"\nLiteratur {lit_k:.3f} (gestrichelter Umriss)"
    if b_ok:
        bt = (f"b = {b_f:.2f} ± {b_fe:.2f} (freier Fit{', schwach bestimmt' if weak else ''}, blau)"
              + (f"\nLiteratur b = {b_lit:.2f} (gestrichelt)" if np.isfinite(b_lit) else ""))
    else:
        bt = f"b = {b_geo:.2f} (Geometrie des Fits;\nb aus dieser Nacht unbestimmt)"
    ax.text(0.5, -0.02, kt + "\n" + bt, transform=ax.transAxes, ha="center", va="top", fontsize=7.2)


# ------------------------------------------------------------------ geometry helpers (circular orbit)
def durations(P, k, ars, inc):
    """t14, t23 in days (t23 = nan for grazing)."""
    si = math.sin(math.radians(inc)); b = ars * math.cos(math.radians(inc))
    f = lambda kk: (P / math.pi * math.asin(min(1.0, math.sqrt(max(0.0, kk ** 2 - b ** 2)) / (ars * si)))
                    if kk > b else float("nan"))
    return f(1 + k), f(1 - k)


def obs_depth(k, b, u):
    """Observed depth at mid-transit (limb darkening included), fraction."""
    return float(1 - flux_z(np.array([b]), k, *u)[0])


def mmag(d):
    return -2500 * math.log10(1 - d)


def rho_star(ars, P):
    return 3 * math.pi * ars ** 3 / (G_CGS * (P * 86400) ** 2)


def spectral_from_rho(r):
    """Very rough main-sequence class from the mean density (in solar units)."""
    for lim, t in ((0.35, "A"), (0.75, "F"), (1.4, "G"), (4.0, "K")):
        if r < lim:
            return t
    return "M"


def sym(p):
    """Median and symmetric 1-sigma from 16/50/84 percentiles."""
    return p[1], 0.5 * (p[2] - p[0])


def undetermined(r):
    """Error bar meaningless (fit at a bound or degenerate): larger than 10x the value and at least 10."""
    e, v = r.get("e"), r.get("v")
    return e is not None and v is not None and (not np.isfinite(e) or e > 10 * max(abs(v), 1.0))


def light(dev):
    if dev is None or not np.isfinite(dev):
        return GREY
    a = abs(dev)
    return GREEN if a < 2 else YELLOW if a < 3 else RED


# ------------------------------------------------------------------ logbook
class _LogbookLock:
    """Exclusive lock file next to the logbook, so parallel reports cannot overwrite each other's rows."""
    def __enter__(self):
        self.p = LOGBOOK + ".lock"
        for _ in range(600):
            try:
                self.fd = os.open(self.p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return self
            except FileExistsError:
                if time.time() - os.path.getmtime(self.p) > 120:      # stale lock from a crashed run
                    try:
                        os.remove(self.p)
                    except OSError:
                        pass
                time.sleep(0.1)
        raise SystemExit(f"Logbuch gesperrt: {self.p} (aelter als 60 s - von Hand loeschen, falls kein transit laeuft)")

    def __exit__(self, *a):
        os.close(self.fd)
        os.remove(self.p)


def logbook_read():
    rows = list(csv.DictReader(open(LOGBOOK, encoding="utf-8"))) if os.path.exists(LOGBOOK) else []
    for r in rows:                                        # logbooks from older versions: missing columns empty
        for k in LOG_FIELDS:
            if r.get(k) is None:
                r[k] = ""
    for key in {(r["planet"], r["nacht"]) for r in rows}:  # exactly one valid run per planet and night
        same = [r for r in rows if (r["planet"], r["nacht"]) == key]
        if not any(r["status"] == VALID for r in same):
            same.sort(key=lambda r: r["eingetragen"])
            for i, r in enumerate(same):
                r["status"] = VALID if i == 0 else VARIANT
    return rows


def logbook_write(rows):
    rows.sort(key=lambda r: (r["planet"], float(r["tc_bjd_tdb"]), r["status"] != VALID, r["lauf"]))
    with open(LOGBOOK, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=LOG_FIELDS, extrasaction="ignore"); w.writeheader(); w.writerows(rows)


def same_run(r, root, lauf):
    here = [x for x in (r["messordner"], r.get("archiv")) if x]          # archived measurements keep their entries
    return r["lauf"] == lauf and any(os.path.normcase(x) == os.path.normcase(root) for x in here)


def logbook_update(row):
    """Insert/replace this run.  A new run of a night that already has a valid run is a variant
    (transit logbuch <Messung> --gueltig <lauf> changes that)."""
    with _LogbookLock():
        return _logbook_update(row)


def _logbook_update(row):
    rows = logbook_read()
    old = next((r for r in rows if same_run(r, row["messordner"], row["lauf"])), None)
    rows = [r for r in rows if r is not old]
    if old is not None:
        row["status"] = old["status"]
        row.setdefault("archiv", old.get("archiv", ""))
    else:
        row["status"] = VARIANT if any(r["status"] == VALID for r in rows if (r["planet"], r["nacht"]) == (row["planet"], row["nacht"])) else VALID
    rows.append(row)
    logbook_write(rows)
    return [r for r in rows if r["planet"] == row["planet"]]


DONT = "NICHT_HOCHLADEN_"


def build_package(out, planet, is_valid, valid_lauf, log=print):
    """RESULT\\<lauf>\\exoclock_paket\\: upload file, form, sheet.  Runs that are not the valid run of their night get
    every upload/form file prefixed NICHT_HOCHLADEN_ and a warning on top of the form."""
    lauf = os.path.basename(out)
    pkg = os.path.join(out, "exoclock_paket")
    os.makedirs(pkg, exist_ok=True)
    for f in os.listdir(pkg):                               # our own generated files only
        if f.endswith("_exoclock_JDUTC.txt") or f.endswith("exoclock_formular.txt"):
            os.remove(os.path.join(pkg, f))
    ups = [f for f in os.listdir(out) if f.endswith("_exoclock_JDUTC.txt") and f.startswith(planet)]
    for f in ups:                                          # legacy name without the run: rename (generated by us)
        if f"_{lauf}_" not in f:
            new = f.replace("_exoclock_JDUTC.txt", f"_{lauf}_exoclock_JDUTC.txt")
            if os.path.exists(os.path.join(out, new)):
                os.remove(os.path.join(out, f))
            else:
                os.replace(os.path.join(out, f), os.path.join(out, new))
    ups = sorted(f for f in os.listdir(out) if f.endswith(f"_{lauf}_exoclock_JDUTC.txt"))
    if not ups:
        log("  kein Upload-File (zuerst transit export)"); return
    up = ups[0]
    d = np.loadtxt(os.path.join(out, up))
    dst = os.path.join(pkg, (DONT if not is_valid else "") + up)
    shutil.copy2(os.path.join(out, up), dst)
    form = os.path.join(out, "exoclock_formular.txt")
    body = open(form, encoding="utf-8").read() if os.path.exists(form) else ""
    if is_valid:
        head = [f"DIESE DATEI HOCHLADEN: {dst}",
                f"  {len(d)} Punkte, erster Zeitpunkt JD_UTC {d[0, 0]:.7f}, letzter {d[-1, 0]:.7f}",
                "  (bei ExoClock nach dem Upload Punktezahl und letzten Zeitpunkt vergleichen)"]
    else:
        head = [f"NICHT HOCHLADEN - dieser Lauf ({lauf}) ist eine Variante.",
                f"Gueltige Messung dieser Nacht: {valid_lauf or '-'}  (aendern: transit logbuch <Messung> --gueltig <lauf>)",
                f"  Diese Datei: {len(d)} Punkte, letzter Zeitpunkt JD_UTC {d[-1, 0]:.7f}"]
    with open(os.path.join(pkg, (DONT if not is_valid else "") + "exoclock_formular.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(head + ["=" * 60, ""]) + body)
    if is_valid:
        result_copy(out, planet, log)
    for f in ("ergebnisblatt.pdf", "ergebnisblatt.png", "ergebnisblatt_feld.png", "ergebnisblatt.html"):
        if os.path.exists(os.path.join(out, f)):
            try:
                shutil.copy2(os.path.join(out, f), pkg)
            except PermissionError:                         # e.g. the PDF is open in a viewer
                log(f"  {f} im Paket nicht ersetzt (Datei ist geoeffnet) - nach dem Schliessen transit report erneut")
    log(f"  exoclock_paket: {os.path.basename(dst)} ({'GUELTIG - hochladen' if is_valid else 'Variante - nicht hochladen'})")


def result_copy(out, planet, log=print):
    """Copy the valid run's upload file + form to <Messordner>\\RESULT\\ - exactly one upload file per night there.
    Only the copies in RESULT\\ are written or removed, never files inside run folders."""
    lauf = os.path.basename(out)
    res_dir = os.path.dirname(out)
    ups = sorted(f for f in os.listdir(out) if f.endswith(f"_{lauf}_exoclock_JDUTC.txt") and f.startswith(planet))
    if not ups:
        log(f"  {lauf}: keine Upload-Datei - RESULT\\-Kopie nicht moeglich"); return None
    up = ups[0]
    night = up.split(f"_{lauf}_")[0]                       # <Planet>_<Datum>
    d = np.loadtxt(os.path.join(out, up))
    for f in os.listdir(res_dir):
        if f.startswith(night + "_") and f.endswith("_exoclock_JDUTC.txt") and f != up and os.path.isfile(os.path.join(res_dir, f)):
            os.remove(os.path.join(res_dir, f))            # copy of a run that is no longer valid
    dst = os.path.join(res_dir, up)
    shutil.copy2(os.path.join(out, up), dst)
    form = os.path.join(out, "exoclock_formular.txt")
    body = open(form, encoding="utf-8").read() if os.path.exists(form) else ""
    head = [f"DIESE DATEI HOCHLADEN: {dst}",
            f"  {len(d)} Punkte, erster Zeitpunkt JD_UTC {d[0, 0]:.7f}, letzter {d[-1, 0]:.7f}",
            "  (bei ExoClock nach dem Upload Punktezahl und letzten Zeitpunkt vergleichen)"]
    with open(os.path.join(res_dir, f"{night}_exoclock_formular.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(head + ["=" * 60, ""]) + body)
    log(f"  {dst} (+ {night}_exoclock_formular.txt) = Upload-Datei dieser Nacht")
    return dst


def refresh_packages(planet, nacht, log=print):
    """Rebuild the packages of all runs of one night (after the valid run changed)."""
    rows = [r for r in logbook_read() if r["planet"] == planet and r["nacht"] == nacht]
    valid = next((r["lauf"] for r in rows if r["status"] == VALID), None)
    for r in rows:
        out = os.path.join(r["messordner"], "RESULT", r["lauf"])
        if os.path.isdir(out):
            build_package(out, planet, r["status"] == VALID, valid, log)
        elif r.get("archiv") and os.path.isdir(os.path.join(r["archiv"], "RESULT", r["lauf"])):
            if r["status"] == VALID:                         # archived: only the RESULT\\ copy, nothing else is changed
                result_copy(os.path.join(r["archiv"], "RESULT", r["lauf"]), planet, log)
        else:
            log(f"  {r['lauf']}: Messordner nicht lokal ({r.get('archiv') or 'kein Archiv eingetragen'}) - Paket nicht angepasst")


def logbook_backfill(root, log=print):
    """Fill the newer logbook columns of all runs of <root> from their fit.json (before archiving)."""
    import math
    with _LogbookLock():
        rows = logbook_read()
        n = 0
        for r in rows:
            if os.path.normcase(r["messordner"]) != os.path.normcase(root):
                continue
            out = os.path.join(root, "RESULT", r["lauf"])
            fp = os.path.join(out, "fit.json")
            if not os.path.exists(fp):
                continue
            f = json.load(open(fp, encoding="utf-8"))
            mc, pred = f["mcmc"], f["ephemeris"]
            kp = [math.sqrt(x / 1e3) for x in mc["depth_ppt"]]
            ke = (kp[2] - kp[0]) / 2
            ex = exoclock_entry(r["planet"])
            lk, lke = ex.get("rp_over_rs"), abs(ex.get("rp_over_rs_e1") or 0)
            fill = dict(rp_rs_err=f"{ke:.5f}", radius_px=str(f["best"]["radius"]), tc_pred_bjd=f"{pred['Tc']:.6f}",
                        periode_d=f"{pred['P']:.8f}", ephemeride=str(pred.get("source", "")),
                        drift=f"{(kp[1] - lk) / math.hypot(ke, lke):.2f}" if lk else "",
                        upload_datei=next((x for x in sorted(os.listdir(out)) if x.endswith(f"_{r['lauf']}_exoclock_JDUTC.txt")), ""))
            for k_, v in fill.items():
                if not r.get(k_):
                    r[k_] = v; n += 1
        logbook_write(rows)
    log(f"  Logbuch: {n} Felder nachgetragen")


def logbook_set_archive(root, target):
    with _LogbookLock():
        rows = logbook_read()
        k = 0
        for r in rows:
            if os.path.normcase(r["messordner"]) == os.path.normcase(root):
                r["archiv"] = target; k += 1
        logbook_write(rows)
    return k


def logbook_set_valid(root, lauf):
    """Mark <lauf> of measurement <root> as the valid run of its night; the other runs of that night become variants."""
    with _LogbookLock():
        return _logbook_set_valid(root, lauf)


def _logbook_set_valid(root, lauf):
    rows = logbook_read()
    me = next((r for r in rows if same_run(r, root, lauf)), None)
    if me is None:
        raise SystemExit(f"Lauf {lauf} von {root} steht nicht im Logbuch (erst transit report ... --out {lauf})")
    for r in rows:
        if (r["planet"], r["nacht"]) == (me["planet"], me["nacht"]):
            r["status"] = VALID if r is me else VARIANT
    logbook_write(rows)
    return me


# ------------------------------------------------------------------ depth plausibility check
def depth_checks(m, n, c, fr, inv, best, ens, r_lab, pix_arcsec):
    """Likely causes of a depth that disagrees with the literature (each: name, flagged, text)."""
    out = []
    # blend: Gaia neighbours inside the aperture
    gp = m.path("gaia_field.csv")
    from .apertur import is_variable, px
    r_px = px(c, r_lab, n.sel)[2]                          # growing aperture: neighbours up to its largest radius
    if os.path.exists(gp):
        g = list(csv.DictReader(open(gp)))
        ra0, de0, G0 = float(c["star_ra"][0]), float(c["star_dec"][0]), float(c["star_G"][0])
        cont, nb = 0.0, []
        tid = str(c["star_gaia"][0])
        for s in g:
            if str(s.get("SOURCE_ID") or s.get("source_id")) == tid:      # the target itself (its Gaia position can be ~1" off)
                continue
            d = math.hypot((float(s["ra"]) - ra0) * math.cos(math.radians(de0)), float(s["dec"]) - de0) * 3600
            if d < r_px * pix_arcsec and s["phot_g_mean_mag"]:
                cont += 10 ** (-0.4 * (float(s["phot_g_mean_mag"]) - G0)); nb.append(f"G={float(s['phot_g_mean_mag']):.1f} bei {d:.0f}\"")
        out.append(("Blend (Gaia-Nachbarn in der Apertur)", cont > 0.02,
                    f"{len(nb)} Stern(e) in r{' max' if is_variable(r_lab) else ''}={r_px:.1f} px ({r_px * pix_arcsec:.0f}\"), Fremdlicht {cont * 100:.1f} % -> Tiefe um "
                    f"Faktor {1 / (1 + cont):.3f} verduennt" + (f" ({', '.join(nb[:4])})" if nb else "")))
    # non-linearity
    pk = c["peak_raw"][n.sel, 0]
    warn = m.cfg["camera"]["linearity_warn_adu"]
    out.append(("Nichtlinearitaet (Ziel-Peak)", float(np.nanmax(pk)) > warn,
                f"Ziel-Peak Median {np.nanmedian(pk):.0f}, Max {np.nanmax(pk):.0f} ADU (Hinweisgrenze {warn})"))
    # airmass coupling
    fb = n.fit(best["radius"], ens)
    cc = float(np.corrcoef(n.am[fb["mask"]], fb["model"])[0, 1]) if np.ptp(fb["model"]) > 0 else 0.0
    out.append(("Kopplung Airmass <-> Transit", abs(cc) > 0.5,
                f"Korrelation Airmass-Term mit Transitform r = {cc:+.2f} (ab |r| > 0.5 kann der Airmass-Term Tiefe schlucken)"))
    # baseline
    pred = fr["ephemeris"]; mg = m.cfg["search"]["oot_margin_min"] / 1440
    t = n.t
    pre = max(0.0, (pred["ingress"] - mg - t.min()) * 24); post = max(0.0, (t.max() - pred["egress"] - mg) * 24)
    bmin = m.cfg["planning"]["baseline_min_h"]
    out.append(("Kurze Baseline", min(pre, post) < bmin,
                f"Baseline vor Ingress {pre:.2f} h, nach Egress {post:.2f} h (Wunsch >= {bmin} h)"))
    if n.flip_mode != "none":
        out.append(("Meridian-Flip", fr["info"].get("flip_mode") == "prior",
                    f"Flip-Stufe ueber Prior {fr['flip_target'][0] * 1e3:+.2f} +- {fr['flip_target'][1] * 1e3:.2f} ppt; "
                    "Fehler im Prior gehen direkt in die Tiefe ein"))
    return out


# ------------------------------------------------------------------ main
def make_sheet(m, n, c, log):
    fr = json.load(open(m.path("fit.json"), encoding="utf-8"))
    inv = json.load(open(m.path("inventory.json"), encoding="utf-8"))
    cs = json.load(open(m.path("compsearch.json"), encoding="utf-8"))
    pred, mc, best, geo = fr["ephemeris"], fr["mcmc"], fr["best"], fr["geometry"]
    planet = inv["planet"]["name"]
    ex = exoclock_entry(planet)
    na = nasa_params(planet)
    u = n.u
    P = pred["P"]
    idx = {nm: i for i, nm in enumerate(n.names)}
    ens = [idx[s] for s in best["comps"]]
    r_px = best["radius"]
    fb = n.fit(r_px, ens)
    ff = n.fit(r_px, ens, free=True)                       # free geometry, for a/R*, i, b, rho (info only)
    ir = n.ir(r_px)

    # ---------------- own values
    tc, tc_e = sym(mc["Tc"])
    k_p = [math.sqrt(d / 1e3) for d in mc["depth_ppt"]]     # Rp/R* percentiles
    k, k_e = sym(k_p)
    b_fix = geo["ars"] * math.cos(math.radians(geo["inc"]))
    dep = [obs_depth(x, b_fix, u) for x in k_p]
    d_obs, d_e = sym(dep)
    t14, t23 = durations(P, k, geo["ars"], geo["inc"])
    errs = ff.get("errs") or [float("nan")] * 4
    a_f, a_fe = ff["ars"], errs[2]
    i_f, i_fe = ff["inc"], errs[3]
    cov = ff.get("cov")
    ci = math.cos(math.radians(i_f)); si = math.sin(math.radians(i_f))
    b_f = a_f * ci
    if cov is not None:                                    # b = a cos i with the a-i covariance
        J = np.array([0, 0, ci, -a_f * si * math.pi / 180])
        b_fe = float(math.sqrt(max(0.0, J @ np.array(cov) @ J)))
    else:
        b_fe = math.hypot(ci * a_fe, a_f * si * math.radians(i_fe))
    rho = rho_star(a_f, P); rho_e = 3 * rho * a_fe / a_f if np.isfinite(a_fe) else float("nan")
    # weak: a/R* worse than 10 %, i undetermined (> 3 deg) or the fit sits on the i = 90 deg bound
    weak = not (np.isfinite(a_fe) and a_fe / a_f < 0.10 and np.isfinite(i_fe) and i_fe < 3 and i_f < 89.9)
    rho_ok = (not weak) and np.isfinite(rho_e) and rho_e / rho < 0.20
    R_s = na.get("st_rad"); R_s_e = na.get("st_raderr1")

    # ---------------- literature
    def ex_e(key):
        return abs(ex.get(f"{key}_e1") or 0) or None
    lit_k, lit_k_e = ex.get("rp_over_rs"), ex_e("rp_over_rs")
    lit_a, lit_a_e = ex.get("sma_over_rs"), ex_e("sma_over_rs")
    lit_i, lit_i_e = ex.get("inclination"), ex_e("inclination")
    lit_d_mmag = ex.get("depth_r_mmag")
    lit_d = 1 - 10 ** (-0.4 * lit_d_mmag / 1000) if lit_d_mmag else None
    lit_d_e = lit_d * 2 * lit_k_e / lit_k if (lit_d and lit_k and lit_k_e) else None
    lit_b = lit_a * math.cos(math.radians(lit_i)) if (lit_a and lit_i) else na.get("pl_imppar")
    lit_t14 = ex.get("duration_hours") or na.get("pl_trandur")
    lit_t12 = None
    if lit_k and lit_a and lit_i:
        a14, a23 = durations(P, lit_k, lit_a, lit_i)
        lit_t12 = (a14 - a23) / 2 * 1440 if np.isfinite(a23) else None
    lit_rj = na.get("pl_radj"); lit_rj_e = na.get("pl_radjerr1")

    # ---------------- table rows: (Groesse, eigener Wert, Fehler, Literatur, Fehler, Einheit/Format, Quelle, Hinweis)
    rows = []

    def add(name, v, e, lv, le, fmt, src, note=""):
        dev = None
        if v is not None and lv is not None and e is not None and np.isfinite(v) and np.isfinite(e):
            s = math.hypot(e, le or 0)
            dev = (v - lv) / s if s > 0 else None
        rows.append(dict(name=name, v=v, e=e, lv=lv, le=le, fmt=fmt, src=src, note=note, dev=dev))
    add("Tc (BJD_TDB)", tc, tc_e, pred["Tc"], pred["Tc_err"], "{:.5f}", f"{pred['source']} Ephemeride", "Fehler in Tagen")
    add("O-C (min)", mc["OC_min"], tc_e * 1440, 0.0, pred["Tc_err"] * 1440, "{:+.1f}", "Vorhersage")
    add("Tiefe (ppt)", d_obs * 1e3, d_e * 1e3, lit_d and lit_d * 1e3, lit_d_e and lit_d_e * 1e3, "{:.2f}", "ExoClock depth_r_mmag",
        "Modell-Minimum mit Randverdunklung")
    add("Tiefe (mmag)", mmag(d_obs), d_e * 1e3 * 1.0857, lit_d_mmag, lit_d_e and lit_d_e * 1e3 * 1.0857, "{:.2f}", "ExoClock")
    add("Rp/R*", k, k_e, lit_k, lit_k_e, "{:.4f}", "ExoClock")
    drift = (k - lit_k) / math.hypot(k_e, lit_k_e or 0) if (lit_k and k_e) else None
    rows.append(dict(name="Rp/R*-Drift (ExoClock-Art)", v=drift, e=None, lv=None, le=None, fmt="{:+.2f}", src="ExoClock-Kriterium",
                     note="(k - k_Lit) / Wurzel(s^2 + s_Lit^2)", dev=drift,
                     ltxt="|Drift| < 2 gut, < 3 ok"))
    if R_s:
        rj = k * R_s * R_SUN_RJ
        rj_e = rj * math.hypot(k_e / k, (R_s_e or 0) / R_s)
        add("Rp (R_Jup)", rj, rj_e, lit_rj, lit_rj_e, "{:.2f}", "NASA (R* aus Literatur)", f"R* = {R_s:.2f} R_sun")
        add("Rp (R_Erde)", rj * R_SUN_RE / R_SUN_RJ, rj_e * R_SUN_RE / R_SUN_RJ, lit_rj and lit_rj * R_SUN_RE / R_SUN_RJ,
            lit_rj_e and lit_rj_e * R_SUN_RE / R_SUN_RJ, "{:.1f}", "NASA")
    add("t14 (h)", t14 * 24, None, lit_t14, None, "{:.2f}", "ExoClock", "aus a/R*, i (fest) und eigenem Rp/R*")
    add("t12 = t34 (min)", (t14 - t23) / 2 * 1440 if np.isfinite(t23) else float("nan"), None, lit_t12, None, "{:.1f}",
        "berechnet (ExoClock)", "eigener Wert: Geometrie fest, eigenes Rp/R*")
    wn = "zur Info, schwach bestimmt" if weak else "Geometrie frei"
    add("a/R* (frei)", a_f, a_fe, lit_a, lit_a_e, "{:.2f}", "ExoClock", wn)
    add("i (Grad, frei)", i_f, i_fe, lit_i, lit_i_e, "{:.2f}", "ExoClock", wn)
    add("b (frei)", b_f, b_fe, lit_b, None, "{:.2f}", "aus ExoClock a/R*, i", wn)
    add("rho* (g/cm3, frei)", rho, rho_e, na.get("st_dens"), None, "{:.2f}", "NASA",
        "aus a/R* und P" if rho_ok else "zur Info, schwach bestimmt")
    sp_own = spectral_from_rho(rho / RHO_SUN) if rho_ok else None
    rows.append(dict(name="Spektraltyp (geschaetzt)", v=None, e=None, lv=None, le=None, fmt="{}", src="NASA",
                     note="aus rho*, Hauptreihe angenommen" if rho_ok else "nicht bestimmt (rho* zu unsicher)", dev=None,
                     vtxt=sp_own or "-", ltxt=na.get("st_spectype") or (f"Teff {ex.get('teff'):.0f} K" if ex.get("teff") else "-")))

    # quality (no literature)
    err = n.rel_err(ir, ens)[fb["mask"]]
    kpar = 2 + fb["ncol"]
    chi2 = float(((fb["res"] / err) ** 2).sum() / (len(err) - kpar))
    ts = fr["top_summary"]["OC_fix_min"]
    sig_res = float(np.std(fb["f"] - fb["model"] * fb["base"]) * 1e3)   # all points, unweighted: comparable to ExoClock "Residuals STD"
    dq = mc["depth_ppt"]
    snr = float(dq[1] / max((dq[2] - dq[0]) / 2, 1e-9))                 # depth / its error, as ExoClock "Transit SNR"
    prev = [float(r["sigma_ppt"]) for r in logbook_read() if r.get("sigma_ppt") and r["status"] == VALID
            and not same_run(r, m.root, os.path.basename(m.out))]
    exp_txt = f"; bisher im Mittel {np.mean(prev):.2f} ppt ({len(prev)} Messungen)" if prev else ""
    qual = [("Streuung sigma (ppt = Promille)", f"{sig_res:.2f}", "Residuen aller Punkte, wie ExoClock \"Residuals STD\"" + exp_txt),
            ("Transit-SNR", f"{snr:.1f}", "Tiefe / Fehler der Tiefe, wie ExoClock (gut: deutlich > 10)"),
            ("OOT-RMS (ppt)", f"{best['oot_rms_ppt']:.2f}"), ("chi2/dof", f"{chi2:.2f}"), ("BIC", f"{fb['bic']:.1f}"),
            ("beta (rotes Rauschen)", f"{mc['beta']:.2f}"), ("Tc-Streuung Top-50 (min)", f"{(ts[2] - ts[0]) / 2:.1f} (MCMC {tc_e * 1440:.1f})"),
            ("MCMC", f"{mc.get('n_chains', 1)} Kette(n)" + (f", R-hat {mc['rhat_max']:.3f}" if mc.get("rhat_max") else "")),
            ("Detrending", f"Airmass {'quadr.' if fr['info'].get('airmass_order', 1) >= 2 else 'linear'}"
                           + (" + Flip" if n.flip_mode != "none" else ""),
             f"Frames mit Airmass > {fr['info']['airmass_max']} weg ({fr['info'].get('excluded_airmass', 0)})" if fr["info"].get("airmass_max") else ""),
            ("Apertur", n.r_text(best["radius"]), "fest oder mitwachsend (k x FWHM), blind nach OOT-RMS gewaehlt; FWHM-Verlauf: fwhm.png"),
            ("Ensemble-Asymmetrie", f"{n.asym(ens, ir):.2f}" if hasattr(n, "asym") else "-",
             "0 = rundum ausgeglichen, 1 = einseitig" + (f"; Symmetrie-Gewicht {fr['info']['symmetry_weight']}" if fr["info"].get("symmetry_weight") else "")),
            ("Ausgeschlossene Sterne", ", ".join(fr["info"].get("excluded_stars", [])) or "-", "von Hand ([comps] exclude_stars)")]
    qual = [q if len(q) == 3 else (q[0], q[1], "Fehler nur Photonen+Lesen" if q[0] == "chi2/dof" else "") for q in qual]

    # pixel scale from the cube (two stars)
    xs, ys = np.nanmedian(c["x"], axis=0), np.nanmedian(c["y"], axis=0)
    j = int(np.nanargmax(np.hypot(xs - xs[0], ys - ys[0])))
    dsky = math.hypot((c["star_ra"][j] - c["star_ra"][0]) * math.cos(math.radians(c["star_dec"][0])), c["star_dec"][j] - c["star_dec"][0]) * 3600
    pix = dsky / math.hypot(xs[j] - xs[0], ys[j] - ys[0])

    drow = rows[2]
    checks = depth_checks(m, n, c, fr, inv, best, ens, r_px, pix)
    try:
        from .feld import transit_window_signal
        tws = transit_window_signal(n, c, ens, ir, pred)
        wf = np.nanmedian(c["flux"][n.sel][:, ens, ir], axis=0); wf = wf / wf.sum()
        bad = [(n.names[j], v, e, v * wf[ens.index(j)]) for j, (v, e) in tws.items() if abs(v) > 3 * e]
        checks.append(("Vergleichsstern veraendert sich im Transitfenster", bool(bad),
                       "; ".join(f"{nm}: {v:+.1f} +- {e:.1f} ppt, Tiefe ca. {d:+.2f} ppt verfaelscht" for nm, v, e, d in bad)
                       or "kein Ensemble-Stern weicht im Transitfenster > 3 sigma ab"))
    except Exception as e_:
        log(f"  Transitfenster-Test nicht moeglich: {e_}")
    if drift is not None:
        checks.insert(0, ("Rp/R*-Drift wie ExoClock", abs(drift) >= 2,
                          f"{drift:+.2f} sigma ({'gut' if abs(drift) < 2 else 'akzeptabel' if abs(drift) < 3 else 'ROT, ExoClock lehnt ab'}: "
                          "ExoClock verlangt |Drift| < 3, besser < 2)"))
    depth_bad = (drow["dev"] is not None and abs(drow["dev"]) > 3) or (drift is not None and abs(drift) >= 3)
    if depth_bad:
        log(f"  WARNUNG Ergebnisblatt: Tiefe weicht {drow['dev']:+.1f} sigma von der Literatur ab. Moegliche Ursachen:")
        for nm, fl, txt in checks:
            log(f"    [{'!' if fl else ' '}] {nm}: {txt}")

    # ---------------- logbook
    night = inv["date_first"][:10]
    lb = logbook_update(dict(planet=planet, nacht=night, messordner=m.root, lauf=os.path.basename(m.out),
                             modus=c["calib"].item() if hasattr(c["calib"], "item") else str(c["calib"]), epoche=pred["epoch"],
                             tc_bjd_tdb=f"{tc:.6f}", tc_err_min=f"{tc_e * 1440:.2f}", oc_min=f"{mc['OC_min']:.2f}",
                             oc_err_min=f"{tc_e * 1440:.2f}", tiefe_ppt=f"{d_obs * 1e3:.3f}", tiefe_err_ppt=f"{d_e * 1e3:.3f}",
                             rp_rs=f"{k:.5f}", rp_rs_err=f"{k_e:.5f}", drift="" if drift is None else f"{drift:.2f}",
                             radius_px=n.r_text(r_px), sigma_ppt=f"{sig_res:.3f}", snr=f"{snr:.1f}", ensemble=" ".join(best["comps"]), tc_pred_bjd=f"{pred['Tc']:.6f}",
                             periode_d=f"{P:.8f}", ephemeride=str(pred.get("source", "")),
                             upload_datei=next((f for f in sorted(os.listdir(m.out)) if f.endswith(f"_{os.path.basename(m.out)}_exoclock_JDUTC.txt")), ""),
                             eingetragen=time.strftime("%Y-%m-%d %H:%M")))

    # ---------------- header info
    hdr = {}
    hp = m.path("headers.csv")
    if os.path.exists(hp):
        hdr = next(csv.DictReader(open(hp, encoding="utf-8")), {})
    obs = m.cfg.get("observer", {})
    lauf = os.path.basename(m.out)

    # ================================================================ figure (A3 width, height from the content)
    # plausibility text, wrapped, so its height is known before the layout
    import textwrap
    txt = ["TIEFE / DRIFT AUFFAELLIG - moegliche Ursachen ([!] = auffaellig):" if depth_bad
           else "Plausibilitaet der Tiefe ([!] = auffaellig):"]
    for nm_, fl, t_ in checks:
        txt += textwrap.wrap(f"[{'!' if fl else ' '}] {nm_}: {t_}", 165, subsequent_indent="      ")
    n_tab = len(rows) + len(qual) + 1                          # parameter rows + quality rows + header
    # every block in inches from the top; table rows are 0.23 in (10 pt x 1.2 x scale 1.38) - 0.245 leaves room
    Y = {}
    y = 1.35
    Y["lc"] = (y, 2.85); Y["res"] = (y + 2.9, 0.95); Y["sketch"] = (y, 3.85); y += 3.85 + 0.85
    Y["tab"] = (y, 0.245 * n_tab); y += 0.245 * n_tab + 0.25
    Y["chk"] = (y, 0.135 * len(txt) + 0.05); y += 0.135 * len(txt) + 0.05 + 0.6
    Y["bot"] = (y, 2.8); y += 2.8 + 0.65
    Y["foot"] = (y, 0.5); y += 0.5 + 0.15
    H = y
    fig = plt.figure(figsize=(11.69, H))
    box = lambda key, x0=0.06, x1=0.97: [x0, 1 - (Y[key][0] + Y[key][1]) / H, x1 - x0, Y[key][1] / H]
    fig.text(0.06, 1 - 0.3 / H, f"Ergebnisblatt {planet}", fontsize=22, weight="bold", va="top")
    fig.text(0.06, 1 - 0.68 / H, f"Nacht {night}  |  Lauf {lauf} (Kalibrierung {c['calib']})  |  {fr['info']['frames_used']} Frames",
             fontsize=10.5, va="top")
    fig.text(0.06, 1 - 0.9 / H, f"Ensemble {n.r_text(r_px)}: {' '.join(best['comps'])}", fontsize=10.5, va="top")
    kopf = fig.text(0.97, 1 - 0.3 / H, f"Tc = {tc:.5f} BJD_TDB\n+{(mc['Tc'][2] - tc) * 1440:.1f} / -{(tc - mc['Tc'][0]) * 1440:.1f} min,  "
             f"O-C {mc['OC_min']:+.1f} min\nSTD {sig_res:.2f} ‰,  SNR {snr:.1f}", fontsize=13, ha="right", va="top", weight="bold")

    # ---- 1. light curve
    a0 = fig.add_axes(box("lc", 0.06, 0.66)); a1 = fig.add_axes(box("res", 0.06, 0.66), sharex=a0)
    off = float(np.floor(fb["t"].min()))
    h = (fb["t"] - off) * 24
    det = fb["f"] / fb["base"]
    a0.plot(h, det, ".", color="0.78", ms=3, zorder=1, label="Einzelpunkte")
    binm = float(m.cfg.get("report", {}).get("bin_min", 10))
    edges = np.arange(h.min(), h.max() + binm / 60, binm / 60)
    ib = np.digitize(h, edges)
    bh, bd, be, br = [], [], [], []
    for q in np.unique(ib):
        s = ib == q
        if s.sum() >= 3:
            bh.append(h[s].mean()); bd.append(det[s].mean()); be.append(det[s].std(ddof=1) / math.sqrt(s.sum()))
            br.append(fb["res"][s].mean())
    a0.errorbar(bh, bd, be, fmt="o", color="#1f3b73", ms=4, capsize=0, zorder=3, label=f"{binm:g}-min-Mittel")
    tm = np.linspace(fb["t"].min(), fb["t"].max(), 2000)
    a0.plot((tm - off) * 24, model(tm, tc, P, k, geo["ars"], geo["inc"], *u), color="#c0392b", lw=1.6, zorder=4, label="Modell (MCMC)")
    yl = a0.get_ylim()
    for v, ls, col, lab in ((pred["Tc"], ":", "0.3", "Tc Vorhersage"), (tc, "-", "#c0392b", "Tc gemessen")):
        a0.axvline((v - off) * 24, color=col, ls=ls, lw=1, label=lab)
    for v in (pred["ingress"], pred["egress"]):
        a0.axvline((v - off) * 24, color="0.5", ls="--", lw=.7)
    for v in (tc - t14 / 2, tc + t14 / 2):
        a0.axvline((v - off) * 24, color="#c0392b", ls="--", lw=.7)
    if np.isfinite(t23):
        for v in (tc - t23 / 2, tc + t23 / 2):
            a0.axvline((v - off) * 24, color="#c0392b", ls=":", lw=.6)
    a0.set_ylim(yl)
    a0.legend(fontsize=7.5, ncol=3, loc="lower left")
    a0.set_ylabel("rel. Fluss (detrendet)")
    a0.set_title("Lichtkurve  (gestrichelt grau: Ingress/Egress Vorhersage, rot: gemessen 1./4. und 2./3. Kontakt)", fontsize=9)
    plt.setp(a0.get_xticklabels(), visible=False)
    a1.plot(h, fb["res"] * 1e3, ".", color="0.78", ms=3)
    a1.plot(bh, np.array(br) * 1e3, "o", color="#1f3b73", ms=3.5)
    a1.axhline(0, color="#c0392b", lw=1)
    a1.set_ylabel("Resid. [ppt]"); a1.set_xlabel(f"BJD_TDB - {off:.0f}  [h]")
    a1.text(0.01, 0.95, f"STD = {sig_res:.3f} ‰", transform=a1.transAxes, fontsize=11, weight="bold", va="top")   # as in the ExoClock report
    a1.text(0.01, 0.05, f"Transit SNR = {snr:.2f}", transform=a1.transAxes, fontsize=11, weight="bold", va="bottom")

    # ---- 3. to-scale sketch: star colour from Teff, limb darkening of the fit, planet Rp/R* and b as measured
    a3 = fig.add_axes(box("sketch", 0.71, 0.97))
    draw_sketch(a3, k, k_e, lit_k, b_fix, lit_b, b_f, b_fe, weak, u, R_s, ex.get("teff") or na.get("st_teff"))

    # ---- 2. parameter table
    at = fig.add_axes(box("tab")); at.axis("off")
    cell, col = [], []
    f_ = lambda fmt, v: "-" if v is None or (isinstance(v, float) and not np.isfinite(v)) else fmt.format(v)
    for r in rows:
        own = r.get("vtxt") or (f_(r["fmt"], r["v"]) + ("" if r["e"] is None else
                                (" (unbestimmt)" if undetermined(r) else f" +- {f_(r['fmt'], r['e'])}")))
        lit = r.get("ltxt") or (f_(r["fmt"], r["lv"]) + ("" if not r["le"] else f" +- {f_(r['fmt'], r['le'])}"))
        dv = "-" if r["dev"] is None else f"{r['dev']:+.1f}"
        weakrow = "schwach" in r["note"] or "nicht bestimmt" in r["note"]
        cell.append([r["name"], own, lit, dv, r["src"], r["note"]])
        col.append(["w", "w", "w", GREY if weakrow and r["dev"] is not None else light(r["dev"]), "w", "w"])
    for nm, v, nt in qual:
        cell.append([nm, v, "", "", "eigene Messung", nt or "Guete"])
        col.append(["#f4f4f4"] * 6)
    tb = at.table(cellText=cell, cellColours=col, colLabels=["Groesse", "Dein Wert", "Literatur", "Abw. sigma", "Quelle", "Hinweis"],
                  colWidths=[0.16, 0.19, 0.17, 0.07, 0.17, 0.24], loc="upper center", cellLoc="left")
    tb.auto_set_font_size(False); tb.set_fontsize(8.0); tb.scale(1, 1.38)
    for (i, j_), cl in tb.get_celld().items():
        cl.set_edgecolor("0.75")
        if i == 0:
            cl.set_text_props(weight="bold"); cl.set_facecolor("#e3e8f0")
    at.set_title("Dein Wert vs. Literatur   (Ampel: gruen < 2 sigma, gelb 2-3 sigma, rot > 3 sigma, grau = schwach bestimmt / ohne Fehler)",
                 fontsize=9.5, loc="left")
    assert len(cell) + 1 == n_tab, (len(cell), n_tab)       # layout above counts on this
    ac = fig.add_axes(box("chk")); ac.axis("off")
    ac.text(0.0, 1.0, "\n".join(txt), transform=ac.transAxes, fontsize=7.6, va="top", family="monospace",
            color="#a33" if depth_bad else "0.25")

    # ---- 4. O-C diagram from the logbook
    a4 = fig.add_axes(box("bot", 0.06, 0.66))
    pe = pred["Tc_err"] * 1440
    ep = np.array([float(r["epoche"]) for r in lb]); oc = np.array([float(r["oc_min"]) for r in lb])
    oe = np.array([float(r["oc_err_min"]) for r in lb])
    cur = np.array([same_run(r, m.root, lauf) for r in lb])
    val = np.array([r.get("status") == VALID for r in lb])
    span = max(1.0, np.ptp(ep)) if len(ep) else 1.0
    a4.axhspan(-pe, pe, color="0.9", label="Vorhersage +-1 sigma")
    a4.axhline(0, color="k", lw=.7)
    vs = ~val & ~cur                                       # variants of a night: faint grey, slightly to the right
    if vs.any():
        a4.errorbar(ep[vs] + 0.012 * max(span, 20), oc[vs], oe[vs], fmt="o", ms=3, capsize=0, color="0.75", alpha=.6,
                    label=f"Varianten ({vs.sum()}, nicht gewertet)")
    s = val & ~cur
    if s.any():
        a4.errorbar(ep[s], oc[s], oe[s], fmt="o", ms=5, capsize=0, color="#1f3b73", label="gueltige Messungen")
    if cur.any():
        is_val = bool(val[cur][0])
        a4.errorbar(ep[cur], oc[cur], oe[cur], fmt="*", ms=11, capsize=0, color="#c0392b" if is_val else "0.45",
                    label=f"diese ({lauf}{'' if is_val else ', Variante'})")
    pad = max(5.0, 0.08 * span)                            # one night or several: readable epoch axis, no offset notation
    a4.set_xlim(ep.min() - pad, ep.max() + pad)
    a4.ticklabel_format(axis="x", useOffset=False, style="plain")
    a4.set_xlabel("Epoche (ExoClock)"); a4.set_ylabel("O-C [min]")
    a4.set_title(f"O-C eigener Messungen ({int(val.sum())} gueltig, {int((~val).sum())} Varianten im Logbuch)", fontsize=9)
    a4.legend(fontsize=6.5)

    # ---- 6. planet profile (literature)
    a6 = fig.add_axes(box("bot", 0.71, 0.97)); a6.axis("off")
    g = lambda d, k_, fmt: "-" if d.get(k_) in (None, "") else fmt.format(d[k_])
    prof = [("Periode", f"{P:.6f} d"), ("Masse", g(na, "pl_bmassj", "{:.2f} M_Jup")),
            ("Radius", g(na, "pl_radj", "{:.2f} R_Jup")), ("T_eq", g(na, "pl_eqt", "{:.0f} K")),
            ("Entdeckt", g(na, "disc_year", "{:.0f}") + (f" ({ex.get('discovery_ref')})" if ex.get("discovery_ref") else "")),
            ("Stern", ex.get("star", "-")), ("V", g(ex, "v_mag", "{:.2f} mag") if ex.get("v_mag") else g(na, "sy_vmag", "{:.2f} mag")),
            ("R*", g(na, "st_rad", "{:.2f} R_sun")), ("M*", g(na, "st_mass", "{:.2f} M_sun")),
            ("Teff", g(ex, "teff", "{:.0f} K")), ("Spektraltyp", na.get("st_spectype") or "-"),
            ("a/R*, i", f"{lit_a} / {lit_i} Grad" if lit_a else "-")]
    a6.add_patch(plt.Rectangle((0, 0), 1, 1, transform=a6.transAxes, fill=True, color="#f6f3ea", ec="0.6"))
    a6.text(0.05, 0.96, "Planetenprofil  -  LITERATUR", transform=a6.transAxes, weight="bold", fontsize=10, va="top")
    a6.text(0.05, 0.86, "\n".join(f"{a_:<12s} {b_}" for a_, b_ in prof), transform=a6.transAxes, family="monospace",
            fontsize=8, va="top", linespacing=1.5)
    src = (f"Quellen: ExoClock-Datenbank (Stand {time.strftime('%Y-%m-%d', time.localtime(os.path.getmtime(os.path.join(PIPE_DIR, 'cache', 'exoclock_planets.json'))))}), "
           f"NASA Exoplanet Archive pscomppars ({na.get('_abgerufen', 'nicht erreichbar')})")
    a6.text(0.05, 0.03, src, transform=a6.transAxes, fontsize=6.3, va="bottom", wrap=True)

    # ---- 7. footer
    af = fig.add_axes(box("foot")); af.axis("off")
    site = m.cfg["site"]
    foot = (f"Beobachter: {obs.get('name') or '-'}   |   Teleskop: {obs.get('telescope') or hdr.get('TELESCOP', '-')}   |   "
            f"Kamera: {obs.get('camera') or hdr.get('INSTRUME', '-')}, Gain {hdr.get('GAIN', '-')}, {hdr.get('CCD-TEMP', '-')} C   |   "
            f"Filter {hdr.get('FILTER') or m.cfg.get('export', {}).get('filter') or '-'}, {hdr.get('EXPTIME', '-')} s   |   Standort {site['lat']:.4f} N {site['lon']:.4f} E {site['elev']:.0f} m\n"
            f"Erzeugt {time.strftime('%Y-%m-%d %H:%M')} mit transit {__version__}  |  {m.root}\\RESULT\\{lauf}\n"
            "Das Blatt zeigt nur Ergebnisse an; keine Auswahl im Werkzeug benutzt Literatur-Tiefe oder Literatur-Tc.")
    af.text(0, 0.9, foot, fontsize=7.4, va="top", color="0.25")

    png = m.path("ergebnisblatt.png"); pdf = m.path("ergebnisblatt.pdf"); png2 = m.path("ergebnisblatt_feld.png")
    fig.savefig(png, dpi=110)
    from . import blatthilfe                               # help areas for the GUI (rectangles in PNG fractions)
    try:
        hilfe1 = blatthilfe.regions(fig, dict(kopf=kopf, lc=a0, res=a1, skizze=a3, tabelle=at.title, plausi=ac, oc=a4,
                                              profil=a6, fuss=af), tb)
    except Exception as e_:
        log(f"  Hilfe zum Ergebnisblatt nicht erzeugt: {e_}"); hilfe1 = []
    # ---- page 2: stretched field + comparison-star table
    from .feld import draw_page
    fig2 = plt.figure(figsize=(11.69, 16.54))
    feld_ok = True
    try:
        crow, crej, cunused, cframe = draw_page(fig2, m, n, c, fr, cs, ens, planet, ex.get("star") or planet[:-1], log)
    except Exception as e_:                                # e.g. NAS not connected: no frame for the field image
        log(f"  Seite 2 (Feldbild) nicht erzeugt: {type(e_).__name__} {e_}")
        fig2.clf(); fig2.set_size_inches(11.69, 3)
        fig2.text(0.05, 0.6, f"Feldbild nicht erzeugt (kein Bild der Nacht lesbar, weder lokal noch am NAS):\n{e_}", fontsize=11, va="top")
        crow, crej, cunused, cframe, feld_ok = [], [], [], None, False
        if os.path.exists(png2):
            png2 = m.path("ergebnisblatt_feld_neu.png")    # keep the earlier field page
    try:                                                   # machine-readable comparison-star table (GUI)
        if not feld_ok:
            raise ValueError("kein Feldbild")
        clean = lambda v: None if (isinstance(v, float) and not np.isfinite(v)) else (v.item() if hasattr(v, "item") else v)
        json.dump(dict(ensemble=[{k: clean(v) for k, v in r.items()} for r in crow], verworfen=[list(x) for x in crej],
                       nicht_genutzt=cunused, frame=cframe), open(m.path("vergleichssterne.json"), "w", encoding="utf-8"),
                  indent=1, ensure_ascii=False)
    except Exception as e_:
        log(f"  vergleichssterne.json nicht geschrieben: {e_}")
    af2 = fig2.text(0.05, 0.2 / fig2.get_size_inches()[1], f"Erzeugt {time.strftime('%Y-%m-%d %H:%M')} mit transit {__version__}  |  Seite 2/2", fontsize=7, color="0.4")
    fig2.savefig(png2, dpi=110)
    hilfe2 = []
    if feld_ok:
        try:
            fa = next(a for a in fig2.axes if a.images)
            ta = next(a for a in fig2.axes if a.tables)
            hilfe2 = blatthilfe.regions(fig2, dict(feldbild=fa, feldtabelle=ta), ta.tables[0], blatthilfe.FELD_SPALTE, {},
                                        blatthilfe.FELD_BLOCK)
        except Exception as e_:
            log(f"  Hilfe zum Feldbild nicht erzeugt: {e_}")
    try:
        blatthilfe.write(m.path("ergebnisblatt_hilfe.json"), hilfe1, hilfe2)
    except OSError as e_:
        log(f"  ergebnisblatt_hilfe.json nicht geschrieben: {e_}")
    with PdfPages(pdf) as pp:
        pp.savefig(fig)
        pp.savefig(fig2)
    plt.close(fig); plt.close(fig2)

    # ================================================================ HTML (self-contained, table as text)
    b64 = base64.b64encode(open(png, "rb").read()).decode()
    b64f = base64.b64encode(open(png2, "rb").read()).decode()
    fm = lambda v, fmt: "&ndash;" if v is None or (isinstance(v, float) and not np.isfinite(v)) else fmt.format(v)
    twtxt = lambda r: "&ndash;" if r["tw"] is None else "{:+.1f} &plusmn; {:.1f}".format(r["tw"], r["tw_e"])
    ctab = "".join(
        f"<tr><td>{r['id']} ({r['name']})</td><td>{r['gaia']}</td><td>{r['ra']} {r['dec']}</td><td>{fm(r['dist'], '{:.1f}')}</td>"
        f"<td>{fm(r['G'], '{:.2f}')}</td><td>{fm(r['dG'], '{:+.2f}')}</td><td>{fm(r['col'], '{:.2f}')}</td><td>{fm(r['dc'], '{:+.2f}')}</td>"
        f"<td>{fm(r['peak'], '{:.0f}')}</td><td>{fm(r['ruwe'], '{:.2f}')}</td><td>{r['var_s']}</td><td>{r['nb']}</td>"
        f"<td>{fm(r['rms'], '{:.1f}')}</td><td>{fm(r['share'], '{:.0f}')}</td><td>{fm(r['jk'], '{:+.1f}')}</td>"
        f"<td{' style=background:#f6c1bd' if r['tw_flag'] else ''}>{twtxt(r)}</td><td>{r['why']}</td></tr>"
        for r in crow)
    rtab = "".join(f"<li><b>{a_}</b>: {b_}</li>" for a_, b_ in crej)
    def hrow(r):
        own = r.get("vtxt") or (f_(r["fmt"], r["v"]) + ("" if r["e"] is None else
                                (" (unbestimmt)" if undetermined(r) else f" &plusmn; {f_(r['fmt'], r['e'])}")))
        lit = r.get("ltxt") or (f_(r["fmt"], r["lv"]) + ("" if not r["le"] else f" &plusmn; {f_(r['fmt'], r['le'])}"))
        weakrow = "schwach" in r["note"] or "nicht bestimmt" in r["note"]
        colr = GREY if weakrow and r["dev"] is not None else light(r["dev"])
        dv = "&ndash;" if r["dev"] is None else f"{r['dev']:+.1f}"
        return (f"<tr><td>{r['name']}</td><td>{own}</td><td>{lit}</td><td><span class=dot style='background:{colr}'></span> {dv}</td>"
                f"<td>{r['src']}</td><td>{r['note']}</td></tr>")
    html = f"""<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ergebnisblatt {planet} {night}</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:16px;max-width:1150px;color:#222;background:#fff}}
h1{{margin:0 0 4px}} .sub{{color:#555;margin-bottom:12px}} .res{{font-size:1.25em;font-weight:600;margin:8px 0 16px}}
table{{border-collapse:collapse;width:100%;font-size:14px;margin:8px 0 16px}} td,th{{border:1px solid #ccc;padding:4px 6px;text-align:left}}
th{{background:#e3e8f0}} .dot{{display:inline-block;width:11px;height:11px;border-radius:50%;vertical-align:middle;border:1px solid #888}}
.chk{{font-family:Consolas,monospace;font-size:13px;white-space:pre-wrap;background:#f7f7f7;padding:8px;border:1px solid #ddd}}
.bad{{color:#a33}} img{{max-width:100%;border:1px solid #ddd}} .foot{{color:#666;font-size:12px;margin-top:14px}}
</style></head><body>
<h1>Ergebnisblatt {planet}</h1>
<div class=sub>Nacht {night} &middot; Lauf {lauf} (Kalibrierung {c['calib']}) &middot; {fr['info']['frames_used']} Frames &middot; Ensemble {n.r_text(r_px)}: {' '.join(best['comps'])}</div>
<div class=res>Tc = {tc:.5f} BJD_TDB (+{(mc['Tc'][2] - tc) * 1440:.1f} / &minus;{(tc - mc['Tc'][0]) * 1440:.1f} min), O&minus;C {mc['OC_min']:+.1f} min, Tiefe {d_obs * 1e3:.2f} &plusmn; {d_e * 1e3:.2f} ppt, STD {sig_res:.2f} &permil;, SNR {snr:.1f}</div>
<h2>Dein Wert vs. Literatur</h2>
<table><tr><th>Gr&ouml;&szlig;e</th><th>Dein Wert</th><th>Literatur</th><th>Abw. [&sigma;]</th><th>Quelle</th><th>Hinweis</th></tr>
{''.join(hrow(r) for r in rows)}
{''.join(f"<tr style='background:#f4f4f4'><td>{a_}</td><td>{b_}</td><td></td><td></td><td>eigene Messung</td><td>{c_ or 'G&uuml;te'}</td></tr>" for a_, b_, c_ in qual)}
</table>
<p>Ampel: gr&uuml;n &lt; 2&sigma;, gelb 2&ndash;3&sigma;, rot &gt; 3&sigma;, grau = schwach bestimmt oder ohne Fehler.</p>
<div class="chk{' bad' if depth_bad else ''}">{chr(10).join(txt)}</div>
<h2>Vergleichssterne</h2>
<table><tr><th>Kennung</th><th>Gaia DR3</th><th>RA / Dec</th><th>Abst. &prime;</th><th>G</th><th>&Delta;G</th><th>BP&minus;RP</th><th>&Delta;Farbe</th>
<th>Peak max</th><th>RUWE</th><th>Var.</th><th>Nachb. &lt;10&Prime;</th><th>Streu. ppt</th><th>Anteil %</th><th>JK &Delta;O&minus;C min</th><th>Transitfenster ppt</th><th>Begr&uuml;ndung</th></tr>
{ctab}</table>
<p>Nicht genutzt, aber geeignet: {', '.join(cunused) or '&ndash;'}. Verworfen (Auswahl):</p><ul>{rtab}</ul>
<h2>Blatt</h2><img alt="Ergebnisblatt {planet}" src="data:image/png;base64,{b64}">
<h2>Feld</h2><img alt="Feld {planet}" src="data:image/png;base64,{b64f}">
<div class=foot>{src}<br>{foot.replace(chr(10), '<br>')}</div>
</body></html>"""
    hp_ = m.path("ergebnisblatt.html")
    with open(hp_, "w", encoding="utf-8") as fh:
        fh.write(html)

    # ---------------- ExoClock package: upload file + form values + sheet
    me = next(r for r in lb if same_run(r, m.root, lauf))
    valid = next((r["lauf"] for r in lb if r["nacht"] == me["nacht"] and r["status"] == VALID), None)
    build_package(m.out, planet, me["status"] == VALID, valid, log)
    if me["status"] == VALID:                              # AstroImageJ files for the valid run
        try:
            from .aij import write_aij
            write_aij(m, n, c, fr, inv, log)
        except Exception as e_:
            log(f"  AIJ-Export nicht moeglich: {e_}")
    log(f"Ergebnisblatt: ergebnisblatt.png/_feld.png/.pdf/.html (+ exoclock_paket\\), Logbuch {LOGBOOK} ({len(lb)} Eintraege {planet})")
    return dict(depth_dev_sigma=drow["dev"], checks=checks)
