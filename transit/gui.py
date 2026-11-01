"""transit gui - local browser front end (Python standard library only).

Starts a small HTTP server on 127.0.0.1 and opens the browser.  Every action runs the existing command line
(`python -m transit run/logbuch/aij ...`) as a subprocess - no second implementation of any logic.
Settings of a run go into RESULT\\<lauf>\\lauf.toml, exactly as if written by hand.
"""
import csv
import glob
import html
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import FITS_EXT, PIPE_DIR, find_lights, has_fits, lights_elsewhere, unwrap
from .export import FILTER_EXOCLOCK

BASE_DEFAULT = os.path.dirname(PIPE_DIR)                  # ...\auto
EXOCLOCK_FILTERS = ["Clear (UV to IR)", "Luminance (B to R)", "U (Johnson)", "B (Johnson)", "V (Johnson)", "R (Cousins)",
                    "I (Cousins)", "H (2MASS)", "J (2MASS)", "Ks (2MASS)", "u' (SDSS)", "g' (SDSS)", "r' (SDSS)",
                    "i' (SDSS)", "z' (SDSS)", "Astrodon ExoPlanet-BB (V to IR)"]
JOBS = {}                                                  # (messordner, lauf) -> Popen
TOKEN_HEADER = "X-Transit"                                 # browsers cannot send it cross-site without CORS -> no CSRF


# ------------------------------------------------------------------ helpers
def is_measurement(p):
    return find_lights(p) is not None


def light_dir(p):
    return find_lights(p)


def listable(p):
    """For the list and for showing results: lights or at least a RESULT folder (lights moved to the NAS)."""
    return os.path.isdir(os.path.join(p, "RESULT")) or is_measurement(p)    # cheap test first (light folders on the NAS are slow)


def overview(p):
    """One line for the folder list: number of lights, runs in RESULT, valid run from the logbook."""
    ld = find_lights(p)
    n = sum(f.lower().endswith(FITS_EXT) for f in os.listdir(ld)) if ld else 0
    res = os.path.join(p, "RESULT")
    runs = [d for d in os.listdir(res) if os.path.isfile(os.path.join(res, d, "fit.json"))] if os.path.isdir(res) else []
    valid = [r["lauf"] for r in logbook() if r.get("status") == "gueltig"
             and os.path.normcase(p) in (os.path.normcase(r["messordner"]), os.path.normcase(r.get("archiv") or "-"))]
    return dict(pfad=p, name=os.path.basename(p), n_lights=n, ausgewertet=len(runs), gueltig=valid[0] if valid else "")


_META = {}


def meta(p):
    """(planet key, night) of a folder: from a run's inventory.json, else from the middle light header (cached)."""
    if p in _META:
        return _META[p]
    from datetime import datetime, timedelta
    from .finden import key
    planet, date = "", ""
    for inv in sorted(glob.glob(os.path.join(p, "RESULT", "*", "inventory.json"))):
        try:
            j = json.load(open(inv, encoding="utf-8"))
            planet, date = j["planet"]["name"], j["date_first"]
            break
        except Exception:
            pass
    if not date:
        ld = find_lights(p)
        fs = sorted(f for f in os.listdir(ld) if f.lower().endswith(FITS_EXT)) if ld else []
        if fs:
            try:
                from astropy.io import fits
                h = fits.getheader(os.path.join(ld, fs[len(fs) // 2]))
                planet, date = str(h.get("OBJECT") or ""), str(h.get("DATE-OBS") or "")
            except Exception:
                pass
    try:
        night = (datetime.fromisoformat(date[:19]) - timedelta(hours=12)).strftime("%Y-%m-%d")
    except ValueError:
        night = ""
    _META[p] = (key(planet or os.path.basename(p)), night)
    return _META[p]


def result_time(p):
    """Newest fit.json in RESULT (when the results were last produced); None = not evaluated."""
    ts = [os.path.getmtime(f) for f in glob.glob(os.path.join(p, "RESULT", "*", "fit.json"))]
    return max(ts) if ts else None


def grouped(ms):
    """One entry per measurement (same planet and night): local and NAS folders merged.  Shown and used is the
    folder with the newest RESULT; without results the folder with the lights."""
    groups = {}
    for p, ort in ms:
        try:
            o = dict(overview(p), ort=ort, t_res=result_time(p))
        except OSError:
            continue
        k = meta(p)
        groups.setdefault(k if k[1] else (k[0], p), []).append(o)
    out = []
    for g in groups.values():
        res = sorted([o for o in g if o["t_res"]], key=lambda o: -o["t_res"])
        lig = max(g, key=lambda o: o["n_lights"])
        main = res[0] if res else lig
        out.append(dict(main, auch=", ".join(sorted({o["ort"] for o in res[1:] if o["ort"] != main["ort"]} |
                                                ({"anderer Ordner"} if any(o["ort"] == main["ort"] for o in res[1:]) else set()))),
                        lights_ort=lig["ort"] if lig["n_lights"] else "", n_lights=lig["n_lights"], lights_pfad=lig["pfad"],
                        alle=[o["pfad"] for o in g]))
    return sorted(out, key=lambda e: e["name"].lower())


def lights_folder(p):
    """Folder with the lights of the measurement shown as p (may be the NAS copy when p only holds results)."""
    if find_lights(p) and any(f.lower().endswith(FITS_EXT) for f in os.listdir(find_lights(p))):
        return p
    from .finden import all_measurements, copies
    for e in grouped(all_measurements(False, log=lambda *x: None)):
        if os.path.normcase(p) in {os.path.normcase(x) for x in e["alle"]} and e["n_lights"]:
            return e["lights_pfad"]
    for c in copies(p):                                    # archive path from the logbook, same folder name locally/NAS
        ld = find_lights(c)                                # (rebuilds an old NAS list once)
        if ld and any(f.lower().endswith(FITS_EXT) for f in os.listdir(ld)):
            return c
    return p


def run_folder(p):
    """Folder a new run of the measurement shown as p is written to: the local copy under ...\\auto when there is one
    (the lights may stay on the NAS, they are only read from there), else the folder with the lights."""
    from .finden import BASE, copies
    nc = lambda x: os.path.normcase(os.path.abspath(x))
    local = lambda x: nc(x).startswith(nc(BASE) + os.sep)
    if local(p) and (os.path.isdir(os.path.join(p, "RESULT")) or is_measurement(p)):
        return p
    for c in copies(p):
        if local(c):
            return c
    return lights_folder(p)


def pick_folder():
    """Local folder dialog (tkinter, standard library); runs on this computer only."""
    try:
        import tkinter
        from tkinter import filedialog
    except ImportError:                                    # portable package: Python without tkinter
        return pick_folder_powershell()
    root = tkinter.Tk(); root.withdraw(); root.attributes("-topmost", True)
    try:
        return filedialog.askdirectory(parent=root, initialdir=BASE_DEFAULT, title="Messordner waehlen") or ""
    finally:
        root.destroy()


def pick_folder_powershell():
    """Same dialog via Windows PowerShell (Windows Forms) for a Python without tkinter."""
    if os.name != "nt":
        return ""
    esc = lambda s: str(s).replace("'", "''")
    ps = ("Add-Type -AssemblyName System.Windows.Forms;"
          "$o=New-Object System.Windows.Forms.Form -Property @{TopMost=$true};"
          "$d=New-Object System.Windows.Forms.FolderBrowserDialog;"
          f"$d.Description='Messordner waehlen';$d.SelectedPath='{esc(BASE_DEFAULT)}';"
          "if($d.ShowDialog($o) -eq 'OK'){[Console]::OutputEncoding=[Text.Encoding]::UTF8;$d.SelectedPath}")
    exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    r = subprocess.run([exe, "-NoProfile", "-STA", "-Command", ps], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.stdout.decode("utf-8", errors="replace").strip()


def header_guess(p):
    """Planet (OBJECT) and filter from the first FITS header."""
    try:
        from astropy.io import fits
        f = sorted(glob.glob(os.path.join(light_dir(p), "*.fit*")))[0]
        h = fits.getheader(f)
        filt = str(h.get("FILTER") or "").strip()
        tt = os.path.join(p, "RESULT", "transit.toml")
        if not filt and os.path.exists(tt):                # header without FILTER: value set for this measurement
            import tomllib
            filt = str(tomllib.load(open(tt, "rb")).get("export", {}).get("filter") or "")
        return dict(planet=str(h.get("OBJECT") or "").strip(), filter_header=filt,
                    filter_exoclock=FILTER_EXOCLOCK.get(filt.upper(), "") if filt else "",
                    n_frames=len(glob.glob(os.path.join(light_dir(p), "*.fit*"))),
                    exptime=h.get("EXPTIME"), binning=h.get("XBINNING"), size=f"{h.get('NAXIS1')}x{h.get('NAXIS2')}")
    except Exception as e:
        return dict(error=str(e))


def logbook():
    from .ergebnisblatt import logbook_read
    try:
        return logbook_read()
    except Exception:
        return []


def runs_of(p):
    res = os.path.join(p, "RESULT")
    lb = {r["lauf"]: r for r in logbook() if os.path.normcase(r["messordner"]) == os.path.normcase(p)}
    out = []
    for d in sorted(glob.glob(os.path.join(res, "*", ""))):
        lauf = os.path.basename(os.path.dirname(d))
        if lauf in ("inventory", "cube", "exoclock") or not (os.path.exists(os.path.join(d, "status.json")) or os.path.exists(os.path.join(d, "fit.json"))):
            continue
        r = dict(lauf=lauf, status=lb.get(lauf, {}).get("status", ""), pfad=p, mess=os.path.basename(p))
        try:
            s = json.load(open(os.path.join(d, "status.json"), encoding="utf-8"))
            r.update(zustand=s.get("state"), schritt=s.get("step") or s.get("command"), task=s.get("task"),
                     prozent=s.get("percent"), eta=s.get("eta_local"), fehler=s.get("error"),
                     heartbeat_alter=round(time.time() - s.get("heartbeat_unix", 0)))
        except Exception:
            pass
        job = JOBS.get((os.path.normcase(p), lauf))
        if job is not None:
            r["laeuft_aus_gui"] = job.poll() is None
        try:
            f = json.load(open(os.path.join(d, "fit.json"), encoding="utf-8"))
            mc = f["mcmc"]
            r.update(oc=round(mc["OC_min"], 2), oc_err=round((mc["Tc"][2] - mc["Tc"][0]) / 2 * 1440, 2), tc=mc["Tc"][1],
                     oot_rms=round(f["best"]["oot_rms_ppt"], 2), beta=round(mc["beta"], 2), radius=f["best"]["radius"],
                     ensemble=" ".join(f["best"]["comps"]), ausgeschlossen=", ".join(f["info"].get("excluded_stars", [])),
                     rhat=mc.get("rhat_max"), flip_prior=[round(x * 1e3, 2) for x in f.get("flip_target", [0, 0])])
            lr = lb.get(lauf, {})
            r.update(drift=lr.get("drift"), rp=lr.get("rp_rs"), rp_err=lr.get("rp_rs_err"), tiefe=lr.get("tiefe_ppt"))
        except Exception:
            pass
        r["blatt"] = os.path.exists(os.path.join(d, "ergebnisblatt.png"))
        out.append(r)
    return out


_CAND = {}
_CAND_FILES = ("candidates.csv", "compsearch.json", "fit.json", "vergleichssterne.json", "lauf.toml", "gaia_details.json",
               "vergleichssterne_lc.png", "ergebnisblatt_feld.png")


def _sig(d):
    return tuple(os.path.getmtime(f) if os.path.exists(f) else 0 for f in (os.path.join(d, n) for n in _CAND_FILES))


def candidates(p, lauf):
    """Candidates with Gaia flags (cached Gaia query) and, for the run's ensemble, the transit-window test.
    Kept in memory per run until one of its input files changes (switching views must not redo the work)."""
    d = os.path.join(p, "RESULT", lauf)
    hit = _CAND.get(d)
    if hit and hit[0] == _sig(d):
        return hit[1]
    out = _candidates(p, lauf, d)
    _CAND[d] = (_sig(d), out)                              # after the call: it may have written gaia_details.json
    return out


def _candidates(p, lauf, d):
    rows = list(csv.DictReader(open(os.path.join(d, "candidates.csv"), encoding="utf-8")))
    cmp = {}
    vj = os.path.join(d, "vergleichssterne.json")
    if os.path.exists(vj):
        for r in json.load(open(vj, encoding="utf-8")).get("ensemble", []):
            cmp[r["name"]] = r
    det = {}
    try:
        from .config import Measurement
        from .feld import gaia_details
        det = gaia_details(Measurement(p, lauf), [r["source_id"] for r in rows], print, netz=False)   # no waiting on Gaia here
    except (Exception, SystemExit) as e:                   # SystemExit: lights moved away (Measurement needs them)
        print("Gaia:", e)
    pre = {}
    cj = os.path.join(d, "compsearch.json")
    if os.path.exists(cj):                                 # per-star quietness (light curve vs the other candidates)
        try:
            pre = {q["name"]: q for q in json.load(open(cj, encoding="utf-8")).get("prefilter", [])}
        except Exception:
            pre = {}
    ein = {}
    fj = os.path.join(d, "fit.json")
    try:                                                   # single-star test (fit, else the ensemble search)
        e = (json.load(open(fj, encoding="utf-8")).get("einzel") if os.path.exists(fj) else None) or \
            (json.load(open(cj, encoding="utf-8")).get("einzel") if os.path.exists(cj) else None) or {}
        ein = {x["name"]: x for x in e.get("stars", [])}
    except Exception:
        ein = {}
    excl = []
    lt = os.path.join(d, "lauf.toml")
    if os.path.exists(lt):
        import tomllib
        excl = tomllib.load(open(lt, "rb")).get("comps", {}).get("exclude_stars", [])
    out = []
    for r in rows:
        g = det.get(str(r["source_id"]), {})
        c = cmp.get(r["name"], {})
        out.append(dict(name=r["name"], gaia=r["source_id"], G=round(float(r["G"]), 2), bp_rp=round(float(r["bp_rp"] or "nan"), 2),
                        ruwe=g.get("ruwe"), var=g.get("var"), im_ensemble=bool(c), tw=c.get("tw"), tw_e=c.get("tw_e"),
                        tw_flag=c.get("tw_flag"), ausgeschlossen=r["name"] in excl, ziel=r["role"] == "target",
                        ruhe=_num(pre.get(r["name"], {}).get("ruhe")), beta=_num(pre.get(r["name"], {}).get("beta")),
                        bin_ppt=_num(pre.get(r["name"], {}).get("bin_ppt")),
                        variabel=bool(pre.get(r["name"], {}).get("variabel")),
                        verworfen=pre.get(r["name"], {}).get("grund") or ("Vorfilter" if pre.get(r["name"], {}).get("rejected") else ""),
                        ein_rp=_num(ein.get(r["name"], {}).get("rp"), 4), ein_med=_num(ein.get(r["name"], {}).get("dev_med")),
                        ein_lit=_num(ein.get(r["name"], {}).get("dev_lit")), ein_oc=_num(ein.get(r["name"], {}).get("OC_min")),
                        ein_auff=bool(ein.get(r["name"], {}).get("auffaellig")), ein_weg=bool(ein.get(r["name"], {}).get("verworfen"))))
    fwhm, radii = None, []
    cubes = glob.glob(os.path.join(d, "cube_*.npz"))
    if cubes:
        import numpy as np
        z = np.load(cubes[0])
        fwhm, radii = float(np.nanmedian(z["fwhm"])), [float(x) for x in z["radii"]]
    try:                                                   # ensemble of the run (also for runs without vergleichssterne.json)
        ens = json.load(open(fj, encoding="utf-8"))["best"]["comps"] if os.path.exists(fj) else []
    except Exception:
        ens = []
    return dict(kandidaten=out, feldbild=os.path.exists(os.path.join(d, "ergebnisblatt_feld.png")), fwhm=fwhm, radii=radii,
                lcbild=os.path.exists(os.path.join(d, "vergleichssterne_lc.png")), ensemble=ens)


def _num(v, nd=2):
    """JSON-safe number (NaN/None -> None), rounded for display."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return round(v, nd) if v == v else None


def toml_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, list):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def write_lauf_toml(path, sections, note):
    lines = [f"# erzeugt von transit gui {time.strftime('%Y-%m-%d %H:%M')}: {note}"]
    for sec, kv in sections.items():
        kv = {k: v for k, v in kv.items() if v not in (None, "", [])}
        if not kv:
            continue
        lines.append(f"\n[{sec}]")
        lines += [f"{k} = {toml_value(v)}" for k, v in kv.items()]
    open(path, "w", encoding="utf-8").write("\n".join(lines) + "\n")


def start_run(q, launch=None):
    """q: messordner, lauf, basis (optional run to reuse photometry from), mode, workers + advanced settings.
    launch(p, lauf, mode, workers, new_stars) -> cmd replaces the plain start (used by the new page)."""
    shown = unwrap(os.path.abspath(q["messordner"]))
    p = run_folder(shown)                                  # results stay local, lights may be read from the NAS
    if not listable(p):
        raise ValueError(f"kein Messordner: {p}")
    if not has_fits(find_lights(p)) and not lights_elsewhere(p):
        from .finden import nas_root
        raise ValueError(f"Zu {p} wurden keine Lights gefunden, weder dort noch am NAS ({nas_root() or 'kein [paths] archiv_wurzel'}). "
                         "NAS verbunden? Sonst 'Ordner waehlen...' oder 'Suchen' benutzen.")
    lauf = (q.get("lauf") or time.strftime("gui_%Y%m%d_%H%M")).strip()
    if not lauf.replace("_", "").replace("-", "").isalnum():
        raise ValueError("Laufname nur aus Buchstaben, Ziffern, _ und -")
    out = os.path.join(p, "RESULT", lauf)
    if os.path.exists(os.path.join(out, "fit.json")):
        raise ValueError(f"Lauf {lauf} existiert schon - anderen Namen waehlen")
    os.makedirs(out, exist_ok=True)
    mode = q.get("mode") or "f"
    basis = q.get("basis")
    a = q.get("erweitert") or {}
    new_stars = any(a.get(k) not in (None, "") for k in ("dmag_bright", "dmag_faint", "neighbour_px", "edge_px"))
    new_phot = (new_stars or a.get("annulus") not in (None, "", []) or any(a.get(k) for k in ("flat", "bias", "dark"))
                or a.get("farbkamera") not in (None, ""))
    if basis:                                              # reuse photometry of an existing run (same mode)
        import shutil
        from .finden import copies
        src = next((d for d in (os.path.join(r, "RESULT", basis) for r in [p, shown] + copies(p)) if os.path.isdir(d)),
                   os.path.join(p, "RESULT", basis))      # the basis run may lie in another copy (e.g. on the NAS)
        keep = ["inventory.json", "headers.csv", "gaia_field.csv", "gaia_details.json", "vsx_field.csv"]
        if not new_phot:                                   # changed candidates/annulus/masters -> new photometry
            keep += ["calib.json", "candidates.csv", "candidates_rejected.csv", f"cube_{mode}.npz"]
        for f in keep:
            if os.path.exists(os.path.join(src, f)) and not os.path.exists(os.path.join(out, f)):
                shutil.copy2(os.path.join(src, f), out)
    sec = {"target": {"planet": q.get("planet")}, "export": {"filter": q.get("filter")},
           "comps": {"exclude_stars": a.get("exclude_stars"), "dmag_bright": a.get("dmag_bright"), "dmag_faint": a.get("dmag_faint"),
                     "neighbour_px": a.get("neighbour_px"), "edge_px": a.get("edge_px")},
           "photometry": {"annulus": a.get("annulus"), "aperture_mode": a.get("aperture_mode"), "k_fwhm": a.get("k_fwhm")},
           "search": {"radii": a.get("radii"), "airmass_max": a.get("airmass_max"), "symmetry_weight": a.get("symmetry_weight"),
                      "einzel_tiefe_sigma": a.get("einzel_tiefe_sigma"), "tiefen_gewicht": a.get("tiefen_gewicht")},
           "fit": {"airmass_order": a.get("airmass_order"), "flip": a.get("flip"), "fix_geometry": a.get("fix_geometry"),
                   "mcmc_steps": a.get("mcmc_steps"), "ausreisser_sigma": a.get("ausreisser_sigma")},
           "calib": {"flat": a.get("flat"), "bias": a.get("bias"), "dark": a.get("dark")},
           "camera": {"farbkamera": a.get("farbkamera")}, "gaia": {"quelle": a.get("gaia_quelle")}}
    if q.get("ensemble"):                                  # stars chosen by hand (tab Vergleichssterne): no ensemble search
        sec["search"]["ensemble"] = [str(x) for x in q["ensemble"]]
    if q.get("einstellungen_von"):                         # same settings as that run; the new values above win
        try:
            import tomllib
            src = tomllib.load(open(os.path.join(p, "RESULT", q["einstellungen_von"], "lauf.toml"), "rb"))
        except Exception:
            src = {}
        for sk, kv in src.items():
            if isinstance(kv, dict):
                d = sec.setdefault(sk, {})
                for k, v in kv.items():
                    if d.get(k) in (None, "", []):
                        d[k] = v
    write_lauf_toml(os.path.join(out, "lauf.toml"), sec, f"Lauf {lauf}" + (f", Photometrie aus {basis}" if basis else "")
                    + (f", Vergleichssterne von Hand: {' '.join(q['ensemble'])}" if q.get("ensemble") else ""))
    if launch is not None:
        return dict(ok=True, lauf=lauf, pfad=p, befehl=" ".join(launch(p, lauf, mode, q.get("workers"), new_stars)))
    cmd = [sys.executable, "-m", "transit", "run", p, "--out", lauf, "--mode", mode]
    if q.get("workers"):
        cmd += ["--workers", str(int(q["workers"]))]
    if new_stars:
        cmd += ["--new-stars"]
    log = open(os.path.join(out, "gui_konsole.txt"), "w", encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=PIPE_DIR + os.pathsep + os.environ.get("PYTHONPATH", ""), PYTHONIOENCODING="utf-8")
    JOBS[(os.path.normcase(p), lauf)] = subprocess.Popen(cmd, cwd=PIPE_DIR, stdout=log, stderr=subprocess.STDOUT, env=env,
                                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return dict(ok=True, lauf=lauf, pfad=p, befehl=" ".join(cmd))


def run_cli(args):
    env = dict(os.environ, PYTHONPATH=PIPE_DIR + os.pathsep + os.environ.get("PYTHONPATH", ""), PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, "-m", "transit"] + args, cwd=PIPE_DIR, capture_output=True, text=True, env=env,
                       encoding="utf-8", errors="replace", timeout=600,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return dict(ok=r.returncode == 0, ausgabe=(r.stdout + r.stderr)[-4000:])


def _sterne(q):
    st = [str(x).strip() for x in (q.get("sterne") or []) if str(x).strip()]
    if not st or not all(x.replace("_", "").isalnum() for x in st):
        raise ValueError("keine oder ungueltige Sternnamen")
    return st


def preview(q):
    """Quick fit (no MCMC) for a hand-made choice of comparison stars of one run: transit vorschau."""
    p = os.path.abspath(q["messordner"])
    lauf = str(q["lauf"])
    if not os.path.isdir(os.path.join(p, "RESULT", lauf)):
        raise ValueError(f"Lauf {lauf} nicht gefunden")
    r = run_cli(["vorschau", p, "--out", lauf, "--sterne", ",".join(_sterne(q))])
    from .vorschau import MARK
    line = next((l for l in r["ausgabe"].splitlines()[::-1] if l.startswith(MARK)), None)
    if not line:
        return dict(ok=False, fehler="Vorschau fehlgeschlagen: " + r["ausgabe"].strip().splitlines()[-1][-300:] if r["ausgabe"].strip() else "keine Ausgabe")
    return dict(json.loads(line[len(MARK):]), ok=True)


def start_hand(q):
    """New run with the stars chosen in the tab Vergleichssterne: photometry and settings of run q["lauf"], ensemble
    fixed ([search] ensemble), full fit with MCMC and checks.  The old run stays as it is."""
    p = os.path.abspath(q["messordner"])
    lauf = str(q["lauf"])
    d = os.path.join(p, "RESULT", lauf)
    mt, cj = jload(os.path.join(d, GUI_META)), jload(os.path.join(d, "calib.json"))
    cubes = sorted(os.path.basename(f)[5:-4] for f in glob.glob(os.path.join(d, "cube_*.npz")))
    mode = mt.get("mode") or (cj.get("mode") if cj.get("mode") in cubes else None) or (cubes[0] if cubes else "f")
    neu = time.strftime("gui_%Y%m%d_%H%M") + f"_{mode}_hand"
    return start_neu(dict(messordner=p, lauf=neu, mode=mode, basis=lauf, workers=mt.get("workers"), ensemble=_sterne(q),
                          einstellungen_von=lauf))


def allowed_file(path):
    """Only files inside <measurement>\\RESULT may be served."""
    p = os.path.abspath(path)
    parts = os.path.normcase(p).split(os.sep)
    if "result" not in parts:
        return False
    root = os.sep.join(p.split(os.sep)[:parts.index("result")])
    return listable(root) and os.path.isfile(p)


# ------------------------------------------------------------------ new GUI (page in gui_neu.py; the classic page stays at /klassisch)
UPLOAD_MARK = "hochgeladen.json"          # RESULT\<lauf>\hochgeladen.json: {"datum": ...} once the user ticked "hochgeladen"
HIDE_MARK = "versteckt.json"              # RESULT\<lauf>\versteckt.json: run hidden in the list (nothing deleted)
GUI_META = "gui_lauf.json"                # RESULT\<lauf>\gui_lauf.json: how the GUI started the run (mode, workers, ...)
WAITING = {}                              # (messordner, lauf) -> dict of the queued start (second calibration variant)
STOPPED = set()                           # (messordner, lauf) stopped by the user: queued follow-up runs are dropped
_NAME = {}


def jload(path, default=None):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return {} if default is None else default


def tail(path, n=14):
    """Last n lines of a console file (n=None: the whole file); progress bars (\\r) collapse to their newest state."""
    try:
        with open(path, "rb") as fh:
            if n is not None:
                fh.seek(0, 2)
                fh.seek(max(0, fh.tell() - 24000))
            txt = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    out = []
    for line in txt.replace("\r\n", "\n").split("\n"):
        line = line.split("\r")
        line = next((s for s in reversed(line) if s.strip()), "")
        if line.strip():
            out.append(line.rstrip())
    return out if n is None else out[-n:]


def planet_name(p):
    """Planet as written (KPS-1b): inventory.json of a run, else RESULT\\transit.toml, else the folder name."""
    if p in _NAME:
        return _NAME[p]
    name = ""
    for inv in sorted(glob.glob(os.path.join(p, "RESULT", "*", "inventory.json"))):
        name = jload(inv).get("planet", {}).get("name", "")
        if name:
            break
    if not name:
        try:
            import tomllib
            name = tomllib.load(open(os.path.join(p, "RESULT", "transit.toml"), "rb")).get("target", {}).get("planet", "")
        except Exception:
            name = ""
    if not name:                                           # not evaluated yet: OBJECT of the first light
        try:
            from astropy.io import fits
            ld = find_lights(p)
            f = sorted(x for x in os.listdir(ld) if x.lower().endswith(FITS_EXT))[0]
            name = str(fits.getheader(os.path.join(ld, f)).get("OBJECT") or "").strip()
        except Exception:
            name = ""
    _NAME[p] = name or os.path.basename(p)
    return _NAME[p]


def run_states(p):
    """{lauf: state} from the status.json files plus the GUI's own job list (quick, for the folder list)."""
    out = {}
    for f in glob.glob(os.path.join(p, "RESULT", "*", "status.json")):
        lauf = os.path.basename(os.path.dirname(f))
        out[lauf] = jload(f).get("state", "")
    for (mp, lauf), job in JOBS.items():
        if mp == os.path.normcase(p) and job.poll() is None:
            out[lauf] = "laeuft"
    for (mp, lauf) in WAITING:
        if mp == os.path.normcase(p):
            out.setdefault(lauf, "wartet")
    return out


def measurements_list(neu=False):
    from .finden import all_measurements
    out = []
    for e in grouped(all_measurements("force" if neu else False, log=lambda *x: None)):
        p = e["pfad"]
        try:
            _, nacht = meta(p)
        except Exception:
            nacht = ""
        st = run_states(p)
        up = [os.path.basename(os.path.dirname(f)) for f in glob.glob(os.path.join(p, "RESULT", "*", UPLOAD_MARK))]
        zust = ("laeuft" if "laeuft" in st.values() else "wartet" if "wartet" in st.values()
                else "fehler" if st and all(v == "fehler" for v in st.values()) and not e["ausgewertet"] else "")
        out.append(dict(e, planet=planet_name(p), nacht=nacht, zustand=zust,
                        hochgeladen=bool(e["gueltig"] and e["gueltig"] in up)))
    return sorted(out, key=lambda e: (e["nacht"] or "0000", e["planet"].lower()), reverse=True)


def defaults(p=None):
    """Values a blank field stands for (global configuration merged with RESULT\\transit.toml)."""
    import tomllib
    from .config import DEFAULT_TOML, _merge
    cfg = tomllib.load(open(DEFAULT_TOML, "rb"))
    if p:
        tt = os.path.join(p, "RESULT", "transit.toml")
        if os.path.exists(tt):
            cfg = _merge(cfg, tomllib.load(open(tt, "rb")))
    g = lambda s, k, d=None: cfg.get(s, {}).get(k, d)
    w = g("run", "workers", 0) or max(1, (os.cpu_count() or 4) - 2)
    return dict(mode=g("calib", "mode", "bf"), workers=w, gaia_quelle=g("gaia", "quelle", "vizier"), gaia_timeout=g("gaia", "timeout_s", 60),
                farbkamera=g("camera", "farbkamera", "auto"), dmag_bright=g("comps", "dmag_bright"), dmag_faint=g("comps", "dmag_faint"),
                neighbour_px=g("comps", "neighbour_px"), edge_px=g("comps", "edge_px"), annulus=g("photometry", "annulus"),
                aperture_mode=g("photometry", "aperture_mode", "beides"), k_fwhm=g("photometry", "k_fwhm"), radii=g("search", "radii"),
                airmass_order=g("fit", "airmass_order", 1), airmass_max=g("search", "airmass_max", 0), flip=g("fit", "flip", "prior"),
                fix_geometry=g("fit", "fix_geometry", True), mcmc_steps=g("fit", "mcmc_steps"), symmetry_weight=g("search", "symmetry_weight", 0),
                ausreisser_sigma=g("fit", "ausreisser_sigma", 0), einzel_tiefe_sigma=g("search", "einzel_tiefe_sigma", 0),
                tiefen_gewicht=g("search", "tiefen_gewicht", 0))


def hints(p):
    """Notes for the measurement shown before a start: colour camera, filter, lights location, ExoClock entry."""
    out, info = [], {}
    ld = find_lights(p)
    fs = sorted(f for f in os.listdir(ld) if f.lower().endswith(FITS_EXT)) if ld else []
    if not fs:
        out.append(dict(level="info", titel="Lights nicht in diesem Ordner",
                        text="Hier liegen nur Ergebnisse. Ein neuer Lauf liest die Lights vom NAS, die Ergebnisse kommen in den lokalen RESULT-Ordner."))
    else:
        try:
            from astropy.io import fits
            h = fits.getheader(os.path.join(ld, fs[0]))
            bp = str(h.get("BAYERPAT") or "").strip()
            fk = str(defaults(p)["farbkamera"]).lower()
            if bp and fk != "nein":
                out.append(dict(level="warn", titel=f"Farbkamera erkannt (BAYERPAT = {bp})",
                                text="Die Bilder werden vor der Photometrie zu 2×2-Superpixeln zusammengefasst (Erweitert › Kamera & Gaia)."))
        except Exception:
            pass
    hg = header_guess(p) if fs else {}
    if fs and not hg.get("filter_exoclock"):
        out.append(dict(level="warn", titel="Filter bitte prüfen",
                        text=f"Header FILTER = {hg.get('filter_header') or 'leer'}: keine eindeutige Zuordnung zum ExoClock-Menü."))
    try:
        from .ephem import CACHE
        db = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else None
    except Exception:
        db = None
    pl = (hg.get("planet") or planet_name(p)) if fs else planet_name(p)
    if db is not None and pl:
        k = pl if pl in db else next((x for x in db if x.replace(" ", "").lower() == pl.replace(" ", "").lower()), None)
        if k:
            e = db[k]
            info = dict(name=k, prio=e.get("priority", ""), gefunden=True)
        else:
            info = dict(name=pl, gefunden=False)
    return dict(hinweise=out, exoclock=info, kopf=hg)


def step_minutes(runs):
    """Typical duration per pipeline step from the runs of this measurement (median of finished steps, seconds)."""
    import statistics
    d = {}
    for r in runs:
        for s in r.get("schritte") or []:
            if s.get("state") == "fertig" and s.get("duration_s"):
                d.setdefault(s["name"], []).append(s["duration_s"])
    return {k: statistics.median(v) for k, v in d.items()}


def run_checks(r, inv, d=None):
    """Checklist for one finished run: planning warnings from inventory.json plus fit quality."""
    out = []
    for c in inv.get("checks", []):
        lev = str(c.get("level", "")).upper()
        out.append(dict(level="warn" if lev in ("WARN", "WARNING") else "bad" if lev in ("ERROR", "FEHLER") else "ok", text=c.get("text", "")))
    if inv and not any(o["level"] != "ok" for o in out):
        out.insert(0, dict(level="ok", text="Keine Planungs-Warnungen (Baseline, Airmass, Flip)"))
    if r.get("drift") not in (None, ""):
        try:
            v = abs(float(r["drift"]))
            out.append(dict(level="ok" if v < 2 else "warn" if v < 3 else "bad", text=f"Drift {v:.1f} (ExoClock: gut unter 2)".replace(".", ",")))
        except ValueError:
            pass
    if r.get("rhat") is not None:
        v = float(r["rhat"])
        out.append(dict(level="ok" if v < 1.05 else "warn", text=f"R-hat {v:.2f} (konvergiert unter 1,05)".replace(".", ",", 1)))
    if r.get("ausgeschlossen"):
        out.append(dict(level="ok", text=f"Ausgeschlossene Vergleichssterne: {r['ausgeschlossen']}"))
    fr = jload(os.path.join(d, "fit.json")) if d else {}
    tc = fr.get("tc_check")
    if tc:                                                 # reviewer check: a second valley / O-C moves with the depth
        out.append(dict(level={"gruen": "ok", "gelb": "warn", "rot": "bad"}.get(tc.get("ampel"), "warn"),
                        text="Tc eindeutig? " + str(tc.get("text", "")).replace(".", ",")))
    e = fr.get("einzel") or {}
    bad = [x["name"] for x in e.get("stars", []) if x.get("auffaellig")]
    if e.get("stars"):
        ins = [x["name"] for x in e["stars"] if x.get("auffaellig") and x.get("im_ensemble")]
        out.append(dict(level="warn" if ins else "ok",
                        text=(f"Einzeltest: {', '.join(ins)} im Ensemble, aber Tiefe allein auffällig" if ins else
                              f"Einzeltest: {len(bad)} auffällige(r) Stern(e) ({', '.join(bad)}), nicht im Ensemble" if bad else
                              f"Einzeltest: alle {len(e['stars'])} Vergleichssterne geben allein eine passende Tiefe")))
    return out


def runs_detail(p):
    runs = runs_of(p)
    for r in runs:
        d = os.path.join(p, "RESULT", r["lauf"])
        st, mt = jload(os.path.join(d, "status.json")), jload(os.path.join(d, GUI_META))
        r["modus"] = mt.get("mode") or jload(os.path.join(d, "calib.json")).get("mode", "")
        r["schritte"] = st.get("steps", [])
        if r.get("zustand") == "laeuft" and not r.get("schritt"):
            r["schritt"] = next((x["name"] for x in r["schritte"] if x.get("state") == "laeuft"), "")
        r["dauer_s"] = st.get("elapsed_s")
        r["gestartet"] = st.get("started")
        g = re.match(r"gui_(\d{4})(\d\d)(\d\d)_(\d\d)(\d\d)", r["lauf"])   # sort key: first start of the run
        r["sortzeit"] = mt.get("gestartet") or (f"{g[1]}-{g[2]}-{g[3]} {g[4]}:{g[5]}" if g else str(st.get("started") or "").replace("T", " "))
        ar = os.path.join(d, "ausreisser.json")
        r["ausreisser"] = len(jload(ar).get("frames", [])) if os.path.exists(ar) else None
        r["hochgeladen"] = jload(os.path.join(d, UPLOAD_MARK)).get("datum", "")
        r["versteckt"] = os.path.exists(os.path.join(d, HIDE_MARK))
        if r.get("oc") is not None:
            r["pruefungen"] = run_checks(r, jload(os.path.join(d, "inventory.json")), d)
        if (os.path.normcase(p), r["lauf"]) in WAITING:
            r["zustand"] = "wartet"
    return runs


def run_detail(p, lauf, voll=False):
    """voll=True: the whole console log instead of the last 14 lines (scrollable log of the new GUI)."""
    d = os.path.join(p, "RESULT", lauf)
    st = jload(os.path.join(d, "status.json"))
    toml = {}
    try:
        import tomllib
        toml = tomllib.load(open(os.path.join(d, "lauf.toml"), "rb"))
    except Exception:
        pass
    q = (toml.get("gaia", {}).get("quelle") or defaults(p)["gaia_quelle"])
    job = JOBS.get((os.path.normcase(p), lauf))
    n = None if voll else 14
    log = tail(os.path.join(d, "gui_konsole.txt"), n) or [l[20:] if l[:2] == "20" else l for l in tail(os.path.join(d, "run.log"), n)]
    others = [r for r in runs_detail(p) if r["lauf"] != lauf]
    return dict(lauf=lauf, pfad=p, status=st, meta=jload(os.path.join(d, GUI_META)), einstellungen=toml,
                gaia=dict(quelle=q, timeout=defaults(p)["gaia_timeout"]), log=log, jetzt=time.time(),
                laeuft_aus_gui=bool(job and job.poll() is None), wartet=(os.path.normcase(p), lauf) in WAITING,
                schaetzung=step_minutes(others), folgelauf=[k[1] for k, v in WAITING.items() if v.get("nach") == lauf and k[0] == os.path.normcase(p)])


def active_runs():
    out = []
    for (mp, lauf), job in list(JOBS.items()):
        if job.poll() is not None:
            continue
        st = jload(os.path.join(mp, "RESULT", lauf, "status.json"))
        p = getattr(job, "transit_pfad", mp)
        out.append(dict(pfad=p, planet=planet_name(p), lauf=lauf, schritt=st.get("step"), task=st.get("task"), prozent=st.get("percent"),
                        seit=st.get("last_progress_unix"), jetzt=time.time()))
    for (mp, lauf), w in WAITING.items():
        out.append(dict(pfad=w["pfad"], planet=planet_name(w["pfad"]), lauf=lauf, schritt="wartet", wartet=True))
    return out


def _launch(p, lauf, mode, workers=None, new_stars=False, append=False):
    cmd = [sys.executable, "-m", "transit", "run", p, "--out", lauf, "--mode", mode]
    if workers:
        cmd += ["--workers", str(int(workers))]
    if new_stars:
        cmd += ["--new-stars"]
    out = os.path.join(p, "RESULT", lauf)
    log = open(os.path.join(out, "gui_konsole.txt"), "a" if append else "w", encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=PIPE_DIR + os.pathsep + os.environ.get("PYTHONPATH", ""), PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    job = subprocess.Popen(cmd, cwd=PIPE_DIR, stdout=log, stderr=subprocess.STDOUT, env=env,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    job.transit_pfad = p
    JOBS[(os.path.normcase(p), lauf)] = job
    return cmd


def start_neu(q):
    """Start from the new page: like start_run, with unbuffered console output, a gui_lauf.json and optional
    follow-up runs in other calibration modes (q["danach"] = ["bf"]) that start when this one has finished."""
    r = start_run(q, launch=_launch)
    p = run_folder(unwrap(os.path.abspath(q["messordner"])))
    lauf, mode = r["lauf"], q.get("mode") or "f"
    json.dump(dict(mode=mode, workers=q.get("workers"), basis=q.get("basis"), gestartet=time.strftime("%Y-%m-%d %H:%M:%S"),
                   befehl=r["befehl"]), open(os.path.join(p, "RESULT", lauf, GUI_META), "w", encoding="utf-8"))
    base = lauf[: -len("_" + mode)] if lauf.endswith("_" + mode) else lauf
    queued = []
    for m2 in q.get("danach") or []:
        if m2 == mode:
            continue
        l2 = f"{base}_{m2}"
        d2 = os.path.join(p, "RESULT", l2)
        if os.path.exists(os.path.join(d2, "fit.json")):
            continue
        os.makedirs(d2, exist_ok=True)
        json.dump(dict(state="wartet", command="run", steps=[]), open(os.path.join(d2, "status.json"), "w", encoding="utf-8"))
        WAITING[(os.path.normcase(p), l2)] = dict(q, mode=m2, lauf=l2, basis=None, danach=None, nach=lauf, pfad=p)
        queued.append(l2)
    if queued:
        threading.Thread(target=_follow, args=(p, lauf, queued), daemon=True).start()
    return dict(r, folgelauf=queued)


def _follow(p, lauf, queued):
    job = JOBS.get((os.path.normcase(p), lauf))
    if job is not None:
        job.wait()
    for l2 in queued:
        q2 = WAITING.get((os.path.normcase(p), l2))
        if q2 is None:
            continue
        if (os.path.normcase(p), lauf) in STOPPED:
            WAITING.pop((os.path.normcase(p), l2), None)
            json.dump(dict(state="fehler", error="nicht gestartet: vorheriger Lauf wurde abgebrochen", steps=[]),
                      open(os.path.join(p, "RESULT", l2, "status.json"), "w", encoding="utf-8"))
            continue
        try:
            os.remove(os.path.join(p, "RESULT", l2, "status.json"))
            WAITING.pop((os.path.normcase(p), l2), None)
            start_neu(dict(q2, danach=None))
            j2 = JOBS.get((os.path.normcase(p), l2))
            if j2 is not None:
                j2.wait()
        except Exception as e:
            WAITING.pop((os.path.normcase(p), l2), None)
            json.dump(dict(state="fehler", error=str(e), steps=[]), open(os.path.join(p, "RESULT", l2, "status.json"), "w", encoding="utf-8"))


def stop_neu(q):
    p = os.path.abspath(q["messordner"])
    key = (os.path.normcase(p), q["lauf"])
    STOPPED.add(key)
    for k, w in list(WAITING.items()):                     # the queued follow-up runs of this run are dropped too
        if k[0] == key[0] and w.get("nach") == q["lauf"]:
            WAITING.pop(k, None)
            json.dump(dict(state="fehler", error="nicht gestartet: vorheriger Lauf wurde abgebrochen", steps=[]),
                      open(os.path.join(p, "RESULT", k[1], "status.json"), "w", encoding="utf-8"))
    j = JOBS.get(key)
    if j and j.poll() is None:
        j.terminate()
    return dict(ok=True)


def switch_gaia(q):
    """Stop the run, set [gaia] quelle in its lauf.toml and continue it (finished steps are skipped)."""
    p = os.path.abspath(q["messordner"])
    lauf, quelle = q["lauf"], ("esa" if q.get("quelle") == "esa" else "vizier")
    d = os.path.join(p, "RESULT", lauf)
    key = (os.path.normcase(p), lauf)
    j = JOBS.get(key)
    if j and j.poll() is None:
        j.terminate()
        try:
            j.wait(15)
        except Exception:
            pass
    lt = os.path.join(d, "lauf.toml")
    txt = open(lt, encoding="utf-8").read() if os.path.exists(lt) else ""
    import re
    if re.search(r"^\[gaia\]", txt, re.M):
        if re.search(r"^\[gaia\][^\[]*^quelle\s*=", txt, re.M | re.S):
            txt = re.sub(r"(^\[gaia\][^\[]*?^quelle\s*=\s*)\"[^\"]*\"", lambda m_: m_.group(1) + f'"{quelle}"', txt, flags=re.M | re.S)
        else:
            txt = re.sub(r"^\[gaia\]\s*$", f'[gaia]\nquelle = "{quelle}"', txt, flags=re.M)
    else:
        txt = txt.rstrip("\n") + f'\n\n[gaia]\nquelle = "{quelle}"\n'
    open(lt, "w", encoding="utf-8").write(txt)
    mt = jload(os.path.join(d, GUI_META))
    mode = mt.get("mode") or jload(os.path.join(d, "calib.json")).get("mode") or "f"
    with open(os.path.join(d, "gui_konsole.txt"), "a", encoding="utf-8") as fh:
        fh.write(f"\n--- Gaia-Quelle auf {quelle} umgestellt, Lauf wird fortgesetzt ---\n")
    _launch(p, lauf, mode, mt.get("workers"), append=True)
    return dict(ok=True, quelle=quelle)


def mark_uploaded(q):
    p = os.path.abspath(q["messordner"])
    f = os.path.join(p, "RESULT", q["lauf"], UPLOAD_MARK)
    if q.get("wert"):
        json.dump(dict(datum=time.strftime("%Y-%m-%d %H:%M")), open(f, "w", encoding="utf-8"))
    elif os.path.exists(f):
        os.remove(f)
    return dict(ok=True)


def mark_hidden(q):
    """Hide a run in the lists of the new page or show it again; only a marker file, the run itself stays."""
    p = os.path.abspath(q["messordner"])
    lauf = str(q["lauf"])
    if not lauf or os.sep in lauf or "/" in lauf or lauf in (".", ".."):
        raise ValueError(f"ungueltiger Laufname: {lauf}")
    d = os.path.join(p, "RESULT", lauf)
    if not os.path.isdir(d):
        raise ValueError(f"Lauf {lauf} nicht gefunden")
    f = os.path.join(d, HIDE_MARK)
    if q.get("wert"):
        json.dump(dict(datum=time.strftime("%Y-%m-%d %H:%M")), open(f, "w", encoding="utf-8"))
    elif os.path.exists(f):
        os.remove(f)
    return dict(ok=True)


# ------------------------------------------------------------------ HTTP
class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        try:
            if u.path in ("/", "/klassisch"):               # new page; the classic one stays available at /klassisch
                if u.path == "/":
                    from .gui_neu import PAGE_NEU
                b = (PAGE_NEU if u.path == "/" else PAGE).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
            elif u.path == "/api/messungen2":
                self._json(measurements_list(q.get("neu") == "1"))
            elif u.path == "/api/messung2":
                p = os.path.abspath(q["pfad"])
                if not listable(p):
                    raise ValueError(f"kein Messordner: {p}")
                if q.get("leicht") == "1":                 # polling: runs only
                    self._json(dict(pfad=p, laeufe=runs_detail(p),
                                    upload=sorted(os.path.basename(f) for f in glob.glob(os.path.join(p, "RESULT", "*_exoclock_JDUTC.txt")))))
                    return
                try:
                    nacht = meta(p)[1]
                except Exception:
                    nacht = ""
                self._json(dict(hints(p), pfad=p, planet=planet_name(p), nacht=nacht, laeufe=runs_detail(p), filter_menu=EXOCLOCK_FILTERS,
                                vorgaben=defaults(p), cpu=os.cpu_count(),
                                upload=sorted(os.path.basename(f) for f in glob.glob(os.path.join(p, "RESULT", "*_exoclock_JDUTC.txt")))))
            elif u.path == "/api/lauf":
                self._json(run_detail(os.path.abspath(q["pfad"]), q["lauf"], q.get("voll") == "1"))
            elif u.path == "/api/aktiv":
                self._json(active_runs())
            elif u.path == "/api/vorgaben":
                self._json(defaults())
            elif u.path == "/api/logbuch":
                self._json(logbook())
            elif u.path == "/handbuch":
                b = open(os.path.join(PIPE_DIR, "HANDBUCH.md"), "rb").read()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
            elif u.path == "/api/messungen":
                from .finden import all_measurements, nas_root   # local tree + NAS (cached list; neu=1 rebuilds)
                msg = []
                ms = all_measurements("force" if q.get("neu") == "1" else False, log=msg.append)
                self._json(grouped(ms))
            elif u.path == "/api/suche":                   # local first; NAS only with nas=1 (user said yes)
                from .finden import nas_root, search
                msg = []
                hits = {os.path.normcase(p_) for p_, _ in search(q["name"], log=msg.append)}
                from .finden import all_measurements
                tre = [e for e in grouped(all_measurements(False, log=msg.append)) if hits & {os.path.normcase(x) for x in e["alle"]}]
                self._json(dict(treffer=tre, hinweis=" ".join(m_ for m_ in msg if "nicht erreichbar" in m_), nas_wurzel=nas_root()))
            elif u.path == "/api/upload":                  # copy template for the ExoClock form of one run
                from .kommentar import load_cfg, make
                p, lauf = os.path.abspath(q["pfad"]), q["lauf"]
                out = os.path.join(p, "RESULT", lauf)
                fp = os.path.join(out, "exoclock_formular.txt")
                form = open(fp, encoding="utf-8").read().split("\nKommentar fuer ExoClock")[0] if os.path.exists(fp) else ""
                self._json(dict(lauf=lauf, formular=form, kommentar=make(out, load_cfg(p, lauf))))
            elif u.path == "/api/messung" and not q.get("pfad"):   # no folder chosen: runs of all folders
                from .finden import all_measurements
                ms = [d for d, _ in all_measurements(False, log=lambda *x: None)]
                self._json(dict(kopf={}, laeufe=[r for d in ms for r in runs_of(d)], filter_menu=EXOCLOCK_FILTERS, upload=[], alle=True))
            elif u.path == "/api/messung":
                p = os.path.abspath(q["pfad"])
                if not listable(p):
                    raise ValueError(f"kein Messordner: {p}")
                self._json(dict(kopf=header_guess(p), laeufe=runs_of(p), filter_menu=EXOCLOCK_FILTERS,
                                upload=sorted(os.path.basename(f) for f in glob.glob(os.path.join(p, "RESULT", "*_exoclock_JDUTC.txt")))))
            elif u.path == "/api/plan":                    # last observing suggestion (transit plan)
                from .plan import PLAN_DIR
                fp = os.path.join(PLAN_DIR, "plan.json")
                self._json(json.load(open(fp, encoding="utf-8")) if os.path.exists(fp) else {})
            elif u.path == "/api/kandidaten":
                self._json(candidates(os.path.abspath(q["pfad"]), q["lauf"]))
            elif u.path == "/datei":
                p = q.get("pfad", "")
                if not allowed_file(p):
                    self.send_error(403, "nur Dateien unter RESULT")
                    return
                b = open(p, "rb").read()
                self.send_response(200)
                text = os.path.splitext(p)[1].lower() in (".log", ".txt", ".md", ".csv", ".toml", ".json")
                self.send_header("Content-Type", "text/plain; charset=utf-8" if text else mimetypes.guess_type(p)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
            else:
                self.send_error(404)
        except (Exception, SystemExit) as e:               # SystemExit (e.g. Measurement) would drop the connection unanswered
            self._json(dict(fehler=str(e)), 500)

    def do_POST(self):
        if self.headers.get(TOKEN_HEADER) != "1":
            self.send_error(403); return
        q = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        try:
            if self.path == "/api/start":
                self._json(start_run(q))
            elif self.path == "/api/start2":
                self._json(start_neu(q))
            elif self.path == "/api/vorschau":
                self._json(preview(q))
            elif self.path == "/api/start_hand":
                self._json(start_hand(q))
            elif self.path == "/api/abbrechen":
                self._json(stop_neu(q))
            elif self.path == "/api/gaia_wechsel":
                self._json(switch_gaia(q))
            elif self.path == "/api/hochgeladen":
                self._json(mark_uploaded(q))
            elif self.path == "/api/verstecken":
                self._json(mark_hidden(q))
            elif self.path == "/api/ordner":
                p = unwrap(os.path.normpath(pick_folder() or "."))
                if p in ("", "."):
                    self._json(dict(pfad=""))
                elif not listable(p):
                    self._json(dict(fehler=f"{p}: keine Lights gefunden (LIGHT, LIGHTS, LIGHT work, orig, _orig, _work oder FITS direkt im Ordner)"))
                else:
                    self._json(overview(p))
            elif self.path == "/api/ordner_oeffnen":
                d = os.path.join(os.path.abspath(q["messordner"]), "RESULT", *([os.path.basename(q["lauf"])] if q.get("lauf") else []))
                if not os.path.isdir(d):
                    raise ValueError(f"{d} fehlt")
                os.startfile(d)
                self._json(dict(ok=True))
            elif self.path == "/api/plan":
                args = ["plan", "--naechte", str(int(q.get("naechte") or 3)), "--top", str(int(q.get("top") or 10))]
                if not q.get("wetter", True):
                    args.append("--ohne-wetter")
                if q.get("vergleich"):
                    args += ["--vergleich", "5"]
                r = run_cli(args)
                from .plan import PLAN_DIR
                fp = os.path.join(PLAN_DIR, "plan.json")
                if r["ok"] and os.path.exists(fp):
                    r["plan"] = json.load(open(fp, encoding="utf-8"))
                self._json(r)
            elif self.path == "/api/gueltig":
                self._json(run_cli(["logbuch", q["messordner"], "--gueltig", q["lauf"]]))
            elif self.path == "/api/aij":
                self._json(run_cli(["aij", q["messordner"], "--lauf", q["lauf"], "--oeffnen"]))
            elif self.path == "/api/stop":
                j = JOBS.get((os.path.normcase(os.path.abspath(q["messordner"])), q["lauf"]))
                if j and j.poll() is None:
                    j.terminate()
                self._json(dict(ok=True))
            else:
                self.send_error(404)
        except (Exception, SystemExit) as e:
            self._json(dict(ok=False, fehler=str(e)), 400)


def cmd_gui(a):
    url = f"http://127.0.0.1:{a.port}/" + ("klassisch" if getattr(a, "klassisch", False) else "")
    import socket
    try:                                    # already running (second double-click)? Windows would let us bind twice
        socket.create_connection(("127.0.0.1", a.port), timeout=0.5).close()
        running = True
    except OSError:
        running = False
    if running:
        print(f"transit gui laeuft bereits auf {url} - oeffne nur den Browser")
        if not a.kein_browser:
            webbrowser.open(url)
        return 0
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), H)
    print(f"transit gui laeuft auf {url}  (beenden: Strg+C)")
    print(f"  neue Oberflaeche: http://127.0.0.1:{a.port}/   klassische Oberflaeche: http://127.0.0.1:{a.port}/klassisch")
    if not a.kein_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


# ------------------------------------------------------------------ page (plain HTML/CSS/JS, German)
PAGE = r"""<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>transit</title>
<style>
:root{--bg:#f6f7f9;--fg:#1d232b;--mut:#5d6773;--card:#fff;--line:#d8dde3;--acc:#1f5fbf;--ok:#2e8b57;--warn:#c98a00;--bad:#c0392b}
@media (prefers-color-scheme:dark){:root{--bg:#14181d;--fg:#e6e9ed;--mut:#9aa4af;--card:#1c2228;--line:#2f3841;--acc:#6aa3ff}}
body{margin:0;font:15px/1.45 system-ui,Segoe UI,sans-serif;background:var(--bg);color:var(--fg)}
header{padding:14px 20px;border-bottom:1px solid var(--line);display:flex;gap:16px;align-items:baseline}
header h1{margin:0;font-size:20px} header span{color:var(--mut)}
main{max-width:1200px;margin:0 auto;padding:16px 20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px 16px;margin-bottom:14px}
.row{display:flex;flex-wrap:wrap;gap:12px;align-items:flex-end}
label{display:flex;flex-direction:column;font-size:13px;color:var(--mut);gap:3px}
input,select{font:inherit;padding:5px 7px;border:1px solid var(--line);border-radius:5px;background:var(--card);color:var(--fg);min-width:90px}
button{font:inherit;padding:6px 12px;border-radius:5px;border:1px solid var(--acc);background:var(--acc);color:#fff;cursor:pointer}
button.sec{background:transparent;color:var(--acc)} button:disabled{opacity:.5;cursor:default}
.help{font-size:12px;color:var(--mut);max-width:260px}
details summary{cursor:pointer;font-weight:600;margin:6px 0}
table{border-collapse:collapse;width:100%;font-size:13px} th,td{border-bottom:1px solid var(--line);padding:5px 6px;text-align:left;vertical-align:top}
th{color:var(--mut);font-weight:600}
.pill{display:inline-block;padding:1px 7px;border-radius:9px;font-size:12px;color:#fff}
.g{background:var(--ok)}.y{background:var(--warn)}.r{background:var(--bad)}.n{background:#8a939c}
.bar{height:8px;background:var(--line);border-radius:4px;overflow:hidden;width:160px;display:inline-block;vertical-align:middle}
.bar>i{display:block;height:100%;background:var(--acc)}
img.blatt{max-width:100%;border:1px solid var(--line);border-radius:6px}
.mono{font-family:Consolas,monospace;font-size:12px;white-space:pre-wrap}
</style></head><body>
<header><h1>transit</h1><span>Transit-Auswertung bis zur ExoClock-Datei</span></header>
<main>
<div class="card"><details id="plandet" ontoggle="if(this.open&&!window.PLAN)planLaden()"><summary>Beobachtungsvorschlag (naechste Naechte, mit Wetter)</summary>
 <div class="row" style="margin-top:8px">
  <label>Naechte<input id="pl_n" type="number" value="3" min="1" max="7" style="width:60px"></label>
  <label>pro Nacht<input id="pl_top" type="number" value="10" min="1" max="50" style="width:60px"></label>
  <label style="flex-direction:row;align-items:center;gap:6px"><input id="pl_wx" type="checkbox" checked style="min-width:0">Wetter (Open-Meteo)</label>
  <label style="flex-direction:row;align-items:center;gap:6px"><input id="pl_gaia" type="checkbox" style="min-width:0">Vergleichssterne zaehlen (Gaia, langsamer)</label>
  <button id="pl_btn" onclick="planRechnen()">Berechnen</button><span id="pl_msg" class="help"></span>
 </div>
 <div class="help" style="max-width:none;margin-top:6px">Transits aus der ExoClock-Datenbank, vollstaendig in der Dunkelheit ueber der Mindesthoehe ([planning] in der Konfiguration),
  tief genug fuer das Teleskop. Score = Prioritaet x erwartete Genauigkeit x Wetter x Abzuege fuer Hinweise. Zeiten lokal.</div>
 <div id="plan"></div></details></div>
<div class="card">
 <div class="row">
  <label>Messordner<select id="mess" onchange="lade()"></select></label>
  <button class="sec" onclick="init(1)" title="Liste neu einlesen (lokal und NAS)">Aktualisieren</button>
  <button class="sec" onclick="ordnerWaehlen()">Ordner waehlen&hellip;</button>
  <label>suchen<input id="such" placeholder="z. B. KELT-7b" style="width:130px" onkeydown="if(event.key==='Enter')suche()"></label>
  <button class="sec" onclick="suche()">Suchen</button>
  <span id="suchbox"></span>
  <span class="help">Ordner mit LIGHT / LIGHTS / _work / _orig. Die Originale werden nur gelesen (Pruefsummen vor und nach jedem Schritt).</span>
 </div>
 <div class="row" style="margin-top:10px">
  <label>Planet<input id="planet" placeholder="z. B. HAT-P-42b"></label>
  <span class="help">Vorschlag aus dem FITS-Header (OBJECT). In ExoClock-Schreibweise, z. B. TOI-628b.</span>
  <label>Filter (ExoClock-Menue)<select id="filter"></select></label>
  <span class="help">Genau so steht er im ExoClock-Upload-Formular. Vorschlag aus dem FITS-Header (FILTER).</span>
 </div>
 <div class="row" style="margin-top:10px">
  <label>Kalibrierung<select id="mode"><option value="f">nur Flat (f)</option><option value="bf">Bias + Flat (bf)</option><option value="bfd">Bias + Flat + Dark (bfd)</option><option value="raw">keine (raw)</option></select></label>
  <span class="help">Empfohlen: f oder bf. Varianten nebeneinander rechnen und nach Datenqualitaet waehlen.</span>
  <label>Laufname<input id="lauf" placeholder="automatisch"></label>
  <label>Photometrie uebernehmen von<select id="basis"><option value="">- neu messen -</option></select></label>
  <span class="help">Spart Minuten: Cube und Kandidaten eines vorhandenen Laufs mit gleicher Kalibrierung verwenden.</span>
  <label>Prozesse<input id="workers" type="number" min="1" max="64" placeholder="auto" style="width:80px"></label>
  <button id="startbtn" onclick="start()">Start</button>
 </div>
 <details style="margin-top:10px"><summary>Erweitert</summary>
  <div class="row">
   <label>Flat (Pfad, leer = automatisch)<input id="flat" size="50"></label>
   <label>Bias<input id="bias" size="40"></label><label>Dark<input id="dark" size="40"></label>
   <span class="help">Leer: passende Master aus der Kalibrierbibliothek (Kamera, Groesse, Filter; gebinnte Lights werden unterstuetzt).</span>
  </div>
  <div class="row" style="margin-top:8px">
   <label>Gaia-Quelle<select id="gaia_quelle"><option value="">VizieR (Standard)</option><option value="esa">ESA-Gaia-Archiv</option></select></label>
   <label>Farbkamera<select id="farbkamera"><option value="">automatisch (BAYERPAT)</option><option value="ja">ja: 2x2-Superpixel</option><option value="nein">nein: wie Mono</option></select></label>
   <span class="help">Gaia DR3 kommt standardmaessig ueber VizieR (CDS); das ESA-Archiv ist die Alternative, wenn VizieR nicht antwortet. Farbkamera: Bayer-Bilder (Header BAYERPAT) werden vor der Photometrie zu 2x2-Superpixeln zusammengefasst, sonst stoert das R/G/B-Muster die Himmelsbestimmung.</span>
  </div>
  <div class="row" style="margin-top:8px">
   <label>Helligkeit hell (dG)<input id="dmag_bright" type="number" step="0.1" placeholder="-0.5" style="width:80px"></label>
   <label>Helligkeit schwach (dG)<input id="dmag_faint" type="number" step="0.1" placeholder="2.0" style="width:80px"></label>
   <label>Mindestabstand Nachbar (px)<input id="neighbour_px" type="number" placeholder="40" style="width:80px"></label>
   <label>Mindestabstand Rand (px)<input id="edge_px" type="number" placeholder="80" style="width:80px"></label>
   <span class="help">Fenster fuer Gaia-Vergleichssterne relativ zum Ziel.</span>
  </div>
  <div class="row" style="margin-top:8px">
   <label>Aperturmodus<select id="ap_mode"><option value="">beides (Standard)</option><option value="fest">fest</option><option value="variabel">mitwachsend</option></select></label>
   <label>Apertur von (x FWHM)<input id="ap_min" type="number" step="0.5" placeholder="1.5" style="width:80px"></label>
   <label>bis (x FWHM)<input id="ap_max" type="number" step="0.5" placeholder="4" style="width:80px"></label>
   <label>Hintergrundring innen/aussen (px)<input id="annulus" placeholder="25,40" style="width:90px"></label>
   <span class="help">Fest: ein Radius fuer die ganze Nacht. Mitwachsend: Radius = k x FWHM in jedem Bild, gleich fuer Ziel und Vergleichssterne - haelt den eingefangenen Lichtanteil bei wechselndem Seeing konstant; die Tiefe wird dadurch nicht verzerrt, solange kein Nachbarstern hineinwaechst (Blend-Pruefung auf dem Blatt). Bei "beides" treten feste Radien und k-Werte gegeneinander an; gewaehlt wird blind nach dem Rauschen ausserhalb des Transits.</span>
  </div>
  <div class="row" style="margin-top:8px">
   <label>Detrending<select id="airmass_order"><option value="">linear (Standard)</option><option value="2">quadratisch</option></select></label>
   <label>Airmass-Grenze<input id="airmass_max" type="number" step="0.1" placeholder="keine" style="width:80px"></label>
   <label>Meridian-Flip<select id="flip"><option value="">Prior aus Vergleichssternen</option><option value="free">frei</option><option value="none">ignorieren</option></select></label>
   <label>Geometrie<select id="fix_geometry"><option value="">fest (ExoClock)</option><option value="false">frei</option></select></label>
   <label>MCMC-Schritte<input id="mcmc_steps" type="number" step="1000" placeholder="30000" style="width:90px"></label>
   <label>Symmetrie-Gewicht<input id="symmetry_weight" type="number" step="0.5" placeholder="0" style="width:80px"></label>
   <label title="Jeder Vergleichsstern allein gegen das Ziel: Sterne, deren Transittiefe allein um mehr als so viele Sigma vom Median aller Sterne und vom Literaturwert abweicht, kommen nicht in die Ensemble-Suche. Standard: nur anzeigen (Tabelle im Ergebnisblatt).">Einzelstern-Grenze<select id="einzel_tiefe_sigma"><option value="">nur anzeigen (Standard)</option><option value="4">verwerfen &gt; 4 sigma</option><option value="3">verwerfen &gt; 3 sigma</option></select></label>
   <label title="0 = Ensemble mit der kleinsten Streuung ausserhalb des Transits (wie bisher). Groesser 0: unter den besten Ensembles gewinnt eher eines, dessen Rp/R* zum erwarteten Wert passt (Streuung x (1 + Gewicht x (Abweichung/3 sigma)^2)). Nach einer Rueckweisung wegen O-C mit 1 probieren.">Tiefen-Gewicht<input id="tiefen_gewicht" type="number" step="0.5" min="0" placeholder="0" style="width:80px"></label>
   <label>Ausreisser entfernen<select id="ausreisser_sigma"><option value="">aus (Standard)</option><option value="4">wenige (&gt; 4 sigma)</option><option value="3">normal (&gt; 3 sigma)</option><option value="2.5">viele (&gt; 2,5 sigma)</option></select></label>
   <span class="help">Ausreisser: Bilder, die mehr als die gewaehlte Zahl Standardabweichungen vom Transit-Fit abweichen (Wolken, Flugzeug, Wind), werden entfernt und der Fit wiederholt; die Liste steht in summary.md und ausreisser.json. Quadratisch nur, wenn der BIC besser wird. Airmass-Grenze schneidet Randpunkte (Baseline vor Ingress >= 30 min lassen).</span>
  </div>
  <div style="margin-top:10px"><b>Vergleichssterne</b> <span class="help">Haken weg = Stern ausschliessen. Ampel: RUWE &gt; 1,4 (Doppelstern?), Gaia VARIABLE, Transitfenster-Test &gt; 3 sigma. Daten aus dem gewaehlten Basislauf.</span>
   <div class="row" style="align-items:flex-start;margin-top:6px">
    <div style="flex:1;min-width:320px"><table id="kand"><tr><td class="help">Basislauf waehlen, um Kandidaten zu sehen.</td></tr></table></div>
    <div style="flex:1;min-width:320px"><img id="feld" class="blatt" alt=""></div>
   </div>
  </div>
 </details>
 <div id="startmsg" class="mono"></div>
</div>
<div class="card"><h3 style="margin-top:0">Laeufe</h3><table id="laeufe"></table>
 <div class="help">Gueltig = die Messung dieser Nacht fuer O-C und Upload. Die Upload-Datei liegt dann direkt unter RESULT\. Variante nur nach Datenqualitaet waehlen (OOT-RMS, beta, Flip-Prior, Pruefungen), nie nach der Literatur-Tiefe.</div>
 <div id="upload" class="mono" style="margin-top:8px"></div></div>
<div class="card" id="upcard" style="display:none"><h3 style="margin-top:0">ExoClock-Upload <span id="uplauf" class="help"></span></h3>
 <div class="help">Formularwerte genau so eintragen. Der Kommentar wird aus den Daten des gueltigen Laufs erzeugt (Konsole: .	ransit kommentar &lt;Messordner&gt;).</div>
 <pre id="upform" class="mono" style="white-space:pre-wrap;margin:8px 0"></pre>
 <textarea id="upkom" rows="6" style="width:100%;font:13px/1.4 monospace"></textarea>
 <div class="row" style="margin-top:6px"><button onclick="kopiere()">Kommentar kopieren</button>
  <button class="sec" onclick="oeffneUpload()">Upload-Ordner oeffnen</button><span id="upmsg" class="help"></span></div></div>
<div class="card" id="blattcard" style="display:none"><h3 style="margin-top:0" id="blatttitel"></h3><img id="blatt" class="blatt"><img id="blatt2" class="blatt" style="margin-top:10px"></div>
</main>
<script>
const H={'Content-Type':'application/json','X-Transit':'1'};
let M=null, timer=null;
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function init(neu){
  const alt=$('mess').value;
  if(neu) $('suchbox').textContent='lese Liste neu (lokal und NAS) ...';
  const ms=await (await fetch('/api/messungen'+(neu?'?neu=1':''))).json();
  if(neu) $('suchbox').textContent='';
  $('mess').innerHTML='<option value="">(alle Messordner)</option>'+ms.map(m=>`<option value="${esc(m.pfad)}">${esc(eintrag(m))}</option>`).join('');
  const first=!window.GELADEN; window.GELADEN=true;           // first load: all folders; refresh: keep the choice
  $('mess').value=first?'':([...$('mess').options].some(o=>o.value===alt)?alt:'');   // start and folder gone: all folders
  lade();
}
function eintrag(m){ const r=m.ausgewertet?`ausgewertet [${m.ort}]`+(m.gueltig?`, gueltig: ${m.gueltig}`:`, ${m.ausgewertet} Laeufe`)+(m.auch?` (auch ${m.auch}, aelter)`:''):'noch nicht ausgewertet';
  return `${m.name} - ${r} - Lights: `+(m.n_lights?`${m.n_lights} [${m.lights_ort}]`:'keine'); }
async function ordnerWaehlen(){ $('startmsg').textContent='Ordnerdialog offen (evtl. hinter dem Browser) ...';
  const r=await (await fetch('/api/ordner',{method:'POST',headers:H,body:'{}'})).json();
  if(r.fehler){ $('startmsg').textContent=r.fehler; return; }
  if(!r.pfad){ $('startmsg').textContent=''; return; }
  if(![...$('mess').options].some(o=>o.value===r.pfad)) $('mess').add(new Option(eintrag(r),r.pfad));
  $('mess').value=r.pfad; $('startmsg').textContent=''; lade(); }
function waehle(p,lab){ if(![...$('mess').options].some(o=>o.value===p)) $('mess').add(new Option(lab||p,p)); $('mess').value=p; $('suchbox').innerHTML=''; lade(); }
async function suche(){ const n=$('such').value.trim(); if(!n)return;
  $('suchbox').textContent='suche lokal und am NAS ...';
  const r=await (await fetch('/api/suche?name='+encodeURIComponent(n))).json();
  const lab=t=>eintrag(t);
  if(r.treffer.length===1){ waehle(r.treffer[0].pfad, lab(r.treffer[0])); $('startmsg').textContent='gefunden: '+r.treffer[0].pfad; return; }
  if(r.treffer.length>1){ $('suchbox').innerHTML=r.treffer.map(t=>`<button class="sec" onclick="waehle(this.dataset.p,this.textContent)" data-p="${esc(t.pfad)}" title="${esc(t.pfad)}">${esc(lab(t))}</button>`).join(' '); return; }
  $('suchbox').textContent='nichts gefunden (lokal und NAS)'+(r.hinweis?' - '+r.hinweis:''); }
async function lade(){
  const p=$('mess').value;
  M=await (await fetch('/api/messung?pfad='+encodeURIComponent(p))).json();
  $('startbtn').disabled=!!M.alle; $('startbtn').title=M.alle?'erst Messordner waehlen':'';
  if(M.alle){ $('startmsg').textContent='Start: erst Messordner waehlen'; zeigeLaeufe(); $('upcard').style.display='none'; $('upload').textContent='Alle Messordner - fuer Start und Upload einen Ordner waehlen.';
    clearInterval(timer); timer=setInterval(aktualisiere,5000); return; }
  $('planet').value=M.kopf.planet||'';
  $('filter').innerHTML=M.filter_menu.map(f=>`<option ${f===M.kopf.filter_exoclock?'selected':''}>${esc(f)}</option>`).join('');
  const done=M.laeufe.filter(l=>l.oc!==undefined);
  $('basis').innerHTML='<option value="">- neu messen -</option>'+M.laeufe.map(l=>`<option>${esc(l.lauf)}</option>`).join('');
  $('basis').onchange=kand;
  zeigeLaeufe();
  ladeUpload();
  $('upload').textContent=M.upload.length?('Upload-Datei unter RESULT\\: '+M.upload.join(', ')):'Noch keine gueltige Upload-Datei.';
  clearInterval(timer); timer=setInterval(aktualisiere,5000);
}
async function aktualisiere(){ M=await (await fetch('/api/messung?pfad='+encodeURIComponent($('mess').value))).json(); zeigeLaeufe(); }
function ampel(v,g,y){ if(v===null||v===undefined||v==='')return '<span class="pill n">-</span>'; const a=Math.abs(+v); return `<span class="pill ${a<g?'g':a<y?'y':'r'}">${(+v).toFixed(2)}</span>`; }
async function ladeUpload(){ const g=(M.laeufe||[]).find(l=>l.status==='gueltig');
  if(!g){ $('upcard').style.display='none'; return; }
  const r=await (await fetch('/api/upload?pfad='+encodeURIComponent($('mess').value)+'&lauf='+encodeURIComponent(g.lauf))).json();
  if(r.fehler){ $('upcard').style.display='none'; return; }
  $('uplauf').textContent='(gueltiger Lauf '+r.lauf+')'; $('upform').textContent=r.formular; $('upkom').value=r.kommentar; $('upmsg').textContent='';
  $('upcard').style.display=''; }
async function kopiere(){ try{ await navigator.clipboard.writeText($('upkom').value); $('upmsg').textContent='kopiert'; }
  catch(e){ $('upkom').select(); document.execCommand('copy'); $('upmsg').textContent='kopiert'; } }
async function oeffneUpload(){ const r=await (await fetch('/api/ordner_oeffnen',{method:'POST',headers:H,body:JSON.stringify({messordner:$('mess').value})})).json();
  $('upmsg').textContent=r.fehler||''; }
function zeigeLaeufe(){
  const rows=M.laeufe.map(l=>{
    const prog=l.zustand==='laeuft'?`<div class="bar"><i style="width:${l.prozent||0}%"></i></div> ${esc(l.schritt||'')} ${l.task?'/ '+esc(l.task):''} ${l.prozent!=null?Math.round(l.prozent)+'%':''} ${l.eta?'fertig ~'+esc(l.eta):''} ${l.heartbeat_alter>120?'<span class="pill r">haengt?</span>':''}`
             :(l.zustand==='fehler'?`<span class="pill r">Fehler</span> ${esc(l.fehler||'')}`:esc(l.zustand||''));
    return `<tr><td>${M.alle?esc(l.mess)+' / ':''}<b>${esc(l.lauf)}</b> ${l.status==='gueltig'?'<span class="pill g">gueltig</span>':''}</td><td>${prog}</td>
      <td>${l.oc!==undefined?`${l.oc>=0?'+':''}${l.oc} &plusmn; ${l.oc_err} min`:''}</td><td>${l.rp?(+l.rp).toFixed(4)+' &plusmn; '+(+l.rp_err).toFixed(4):''}</td>
      <td>${l.oc!==undefined?ampel(l.drift,2,3):''}</td><td>${l.oot_rms??''}</td><td>${l.beta??''}</td>
      <td>${l.flip_prior?('&plusmn;'+l.flip_prior[1]):''}</td><td>${l.radius??''}</td><td class="help">${esc(l.ensemble||'')}${l.ausgeschlossen?'<br>ohne '+esc(l.ausgeschlossen):''}</td>
      <td>${l.blatt?`<button class="sec" onclick="blatt('${esc(l.lauf)}',this.dataset.p)" data-p="${esc(l.pfad)}">Blatt</button>`:''}
          ${l.oc!==undefined&&l.status!=='gueltig'?`<button class="sec" onclick="gueltig('${esc(l.lauf)}',this.dataset.p)" data-p="${esc(l.pfad)}">Gueltig</button>`:''}
          ${l.oc!==undefined?`<button class="sec" onclick="aij('${esc(l.lauf)}',this.dataset.p)" data-p="${esc(l.pfad)}">In AIJ oeffnen</button>`:''}</td></tr>`;}).join('');
  $('laeufe').innerHTML='<tr><th>Lauf</th><th>Fortschritt</th><th>O-C</th><th>Rp/Rs</th><th title="ExoClock-Kriterium: gruen < 2, gelb 2-3, rot >= 3">Drift</th><th title="Rauschen ausserhalb des Transits">OOT-RMS ppt</th><th title="rotes Rauschen, 1 = weiss">beta</th><th title="Unsicherheit der Flip-Stufe">Flip ppt</th><th>r px</th><th>Ensemble</th><th></th></tr>'+rows;
}
async function kand(){
  const b=$('basis').value; if(!b){$('kand').innerHTML='';$('feld').src='';return;}
  $('kand').innerHTML='<tr><td class="help">lade Kandidaten (Gaia-Abfrage beim ersten Mal) ...</td></tr>';
  const K=await (await fetch(`/api/kandidaten?pfad=${encodeURIComponent($('mess').value)}&lauf=${encodeURIComponent(b)}`)).json();
  if(K.fehler){$('kand').innerHTML=`<tr><td>${esc(K.fehler)}</td></tr>`;return;}
  window.KAND=K;
  $('kand').innerHTML='<tr><th>an</th><th>Stern</th><th>G</th><th>BP-RP</th><th>RUWE</th><th>Gaia</th><th>Ruhe</th><th>Transitfenster</th></tr>'+K.kandidaten.filter(k=>!k.ziel).map(k=>{
    const rh=k.ruhe==null?'<span class="pill n">-</span>':`<span class="pill ${k.variabel||k.verworfen?'r':k.ruhe>2?'y':'g'}" title="${esc(k.verworfen||('Streuung der 10-min-Mittel '+k.bin_ppt+' ppt, beta '+k.beta))}">${(+k.ruhe).toFixed(1)}${k.variabel?' VAR':''}</span>`;
    const ru=k.ruwe==null?'<span class="pill n">-</span>':`<span class="pill ${k.ruwe>1.4?'y':'g'}">${(+k.ruwe).toFixed(2)}</span>`;
    const va=k.var&&k.var.toUpperCase().startsWith('VARIABLE')?'<span class="pill r">VARIABLE</span>':'<span class="pill g">ok</span>';
    const tw=k.tw==null?'<span class="help">nur Ensemble</span>':`<span class="pill ${k.tw_flag?'r':'g'}">${(+k.tw).toFixed(1)} &plusmn; ${(+k.tw_e).toFixed(1)}</span>`;
    const off=k.ausgeschlossen||(k.var&&k.var.toUpperCase().startsWith('VARIABLE'))||k.tw_flag||k.variabel;
    return `<tr><td><input type="checkbox" class="kcb" value="${esc(k.name)}" ${off?'':'checked'}></td><td>${esc(k.name)}${k.im_ensemble?' *':''}</td><td>${k.G}</td><td>${k.bp_rp}</td><td>${ru}</td><td>${va}</td><td>${rh}</td><td>${tw}</td></tr>`;}).join('')+
    '<tr><td colspan="8" class="help">* im Ensemble des Basislaufs. Ruhe = Streuung des Sterns gegen die uebrigen (10-min-Mittel) / Median, 1 = typisch. Vorschlag: VARIABLE (Gaia oder eigene Lichtkurve) und Transitfenster &gt; 3 sigma sind abgewaehlt.'+
    (K.lcbild?` <a target="_blank" href="/datei?pfad=${encodeURIComponent($('mess').value+'/RESULT/'+b+'/vergleichssterne_lc.png')}">Lichtkurven der Vergleichssterne</a>`:'')+'</td></tr>';
  const p=$('mess').value+'\\RESULT\\'+b+'\\ergebnisblatt_feld.png';
  $('feld').src=K.feldbild?('/datei?pfad='+encodeURIComponent(p)):'';
}
function num(id){const v=$(id).value;return v===''?null:+v;}
async function start(){
  const er={flat:$('flat').value||null,bias:$('bias').value||null,dark:$('dark').value||null,
    dmag_bright:num('dmag_bright'),dmag_faint:num('dmag_faint'),neighbour_px:num('neighbour_px'),edge_px:num('edge_px'),
    airmass_order:num('airmass_order'),airmass_max:num('airmass_max'),flip:$('flip').value||null,
    fix_geometry:$('fix_geometry').value===''?null:false,mcmc_steps:num('mcmc_steps'),symmetry_weight:num('symmetry_weight'),einzel_tiefe_sigma:num('einzel_tiefe_sigma'),tiefen_gewicht:num('tiefen_gewicht'),
    gaia_quelle:$('gaia_quelle').value||null,farbkamera:$('farbkamera').value||null,ausreisser_sigma:num('ausreisser_sigma')};
  if($('annulus').value){er.annulus=$('annulus').value.split(',').map(Number);}
  const cbs=[...document.querySelectorAll('.kcb')]; if(cbs.length){er.exclude_stars=cbs.filter(c=>!c.checked).map(c=>c.value);}
  const amin=num('ap_min'),amax=num('ap_max');
  if(amin&&amax){ const K=window.KAND||{}; const fw=K.fwhm||5; const rr=(K.radii&&K.radii.length)?K.radii:[8,10,12,14,16,18,20,22,24];
    er.radii=rr.filter(r=>r>=amin*fw&&r<=amax*fw); if(!er.radii.length)er.radii=null;
    er.k_fwhm=[]; for(let k=amin;k<=amax+1e-9;k+=0.5) er.k_fwhm.push(+k.toFixed(2));
    $('startmsg').textContent='feste Aperturen '+(er.radii||[]).join(', ')+' px (FWHM '+fw.toFixed(1)+' px), mitwachsend k = '+er.k_fwhm.join(', '); }
  if($('ap_mode').value) er.aperture_mode=$('ap_mode').value;
  const body={messordner:$('mess').value,planet:$('planet').value,filter:$('filter').value,mode:$('mode').value,
    lauf:$('lauf').value,basis:$('basis').value||null,workers:num('workers'),erweitert:er};
  const r=await (await fetch('/api/start',{method:'POST',headers:H,body:JSON.stringify(body)})).json();
  $('startmsg').textContent=r.ok?('gestartet: '+r.lauf+(r.pfad?' in '+r.pfad:'')+'\n'+r.befehl):('Fehler: '+r.fehler);
  aktualisiere();
}
async function gueltig(l,p){ p=p||$('mess').value; if(!confirm('Lauf '+l+' als gueltige Messung dieser Nacht setzen? Die Upload-Datei unter RESULT\\ wird ersetzt.'))return;
  const r=await (await fetch('/api/gueltig',{method:'POST',headers:H,body:JSON.stringify({messordner:p,lauf:l})})).json();
  $('startmsg').textContent=r.ausgabe||r.fehler; lade(); }
async function aij(l,p){ p=p||$('mess').value; const r=await (await fetch('/api/aij',{method:'POST',headers:H,body:JSON.stringify({messordner:p,lauf:l})})).json(); $('startmsg').textContent=r.ausgabe||r.fehler; }
function blatt(l,p){ const b=(p||$('mess').value)+'\\RESULT\\'+l+'\\'; $('blattcard').style.display=''; $('blatttitel').textContent='Ergebnisblatt '+l;
  $('blatt').src='/datei?pfad='+encodeURIComponent(b+'ergebnisblatt.png')+'&t='+Date.now(); $('blatt2').src='/datei?pfad='+encodeURIComponent(b+'ergebnisblatt_feld.png')+'&t='+Date.now();
  $('blattcard').scrollIntoView({behavior:'smooth'}); }
const PLC=['#1f5fbf','#c0392b','#2e8b57','#c98a00','#7d3cb5','#138d90','#8a5a2b','#d6338a'];
const hhmm=s=>s?new Date(s).toLocaleTimeString('de-AT',{hour:'2-digit',minute:'2-digit'}):'';
const AMP={gruen:'g',gelb:'y',rot:'r'}; const r0=v=>v==null?'?':Math.round(v);
async function planLaden(){ const r=await (await fetch('/api/plan')).json(); if(r.naechte){window.PLAN=r; planZeigen(r);} else $('plan').innerHTML='<p class="help">Noch kein Vorschlag berechnet.</p>'; }
async function planRechnen(){ $('pl_btn').disabled=true; $('pl_msg').textContent='rechne ... (ExoClock, Sichtbarkeit'+($('pl_wx').checked?', Wetter':'')+')';
  try{ const r=await (await fetch('/api/plan',{method:'POST',headers:H,body:JSON.stringify({naechte:+$('pl_n').value,top:+$('pl_top').value,wetter:$('pl_wx').checked,vergleich:$('pl_gaia').checked})})).json();
    if(r.plan){window.PLAN=r.plan; planZeigen(r.plan); $('pl_msg').textContent='';} else $('pl_msg').textContent='Fehler: '+(r.ausgabe||r.fehler||'');
  } finally { $('pl_btn').disabled=false; } }
function planKurve(n){ // altitude curves of the suggestions; thick = observing window, grey band = dark, dashed = minimum altitude
  const S=n.sonne, t0=new Date(S.t0).getTime(), dt=S.schritt_min*60000, N=S.hoehe.length, W=640, Hh=170, L=30, B=20;
  const x=t=>L+(t-t0)/(dt*(N-1))*(W-L-6), y=a=>6+(90-Math.max(0,Math.min(90,a)))/90*(Hh-B-6);
  let g=`<svg viewBox="0 0 ${W} ${Hh}" style="width:100%;max-width:${W}px;font-size:10px">`;
  const d0=new Date(n.dunkel[0]).getTime(), d1=new Date(n.dunkel[1]).getTime();
  g+=`<rect x="${x(d0)}" y="6" width="${x(d1)-x(d0)}" height="${Hh-B-6}" fill="var(--line)" opacity=".45"/>`;
  for(const a of [0,30,60,90]) g+=`<line x1="${L}" x2="${W-6}" y1="${y(a)}" y2="${y(a)}" stroke="var(--line)"/><text x="2" y="${y(a)+3}" fill="var(--mut)">${a}&deg;</text>`;
  const am=window.PLAN.parameter.alt_min; g+=`<line x1="${L}" x2="${W-6}" y1="${y(am)}" y2="${y(am)}" stroke="var(--bad)" stroke-dasharray="4 3"/>`;
  for(let i=0;i<N;i+=6){ const t=t0+i*dt; g+=`<text x="${x(t)-12}" y="${Hh-5}" fill="var(--mut)">${hhmm(new Date(t).toISOString())}</text>`; }
  if(n.mond){ g+=`<polyline fill="none" stroke="var(--mut)" stroke-dasharray="2 3" points="${n.mond.map((a,i)=>x(t0+i*dt)+','+y(a)).join(' ')}"/>`; }
  n.vorschlaege.slice(0,8).forEach((s,j)=>{ const K=s.kurve, k0=new Date(K.t0).getTime(), kd=K.schritt_min*60000, c=PLC[j%PLC.length];
    const pts=K.hoehe.map((a,i)=>[k0+i*kd,a]); const s0=new Date(s.start).getTime(), s1=new Date(s.ende).getTime();
    g+=`<polyline fill="none" stroke="${c}" stroke-width="1" opacity=".5" points="${pts.map(p=>x(p[0])+','+y(p[1])).join(' ')}"/>`;
    g+=`<polyline fill="none" stroke="${c}" stroke-width="3" points="${pts.filter(p=>p[0]>=s0&&p[0]<=s1).map(p=>x(p[0])+','+y(p[1])).join(' ')}"><title>${esc(s.planet)}</title></polyline>`; });
  return g+'</svg>'; }
function planZeigen(P){
  const fmt=d=>new Date(d+'T12:00').toLocaleDateString('de-AT',{weekday:'short',day:'2-digit',month:'2-digit'});
  let h=`<p class="help" style="max-width:none">Erstellt ${new Date(P.erstellt).toLocaleString('de-AT')} &middot; ${P.instrument.oeffnung_cm} cm, Feld ${P.instrument.feld_arcmin[0]}'x${P.instrument.feld_arcmin[1]}' &middot; Mindesthoehe ${P.parameter.alt_min}&deg;`+(P.parameter.wetter?'':' &middot; <b>ohne Wetter</b>')+'</p>';
  for(const n of P.naechte){
    if(!n.dunkel){ h+=`<h3>${fmt(n.datum)}</h3><p class="help">${esc(n.hinweis||'keine Transits')}</p>`; continue; }
    const w=n.wetter; h+=`<h3 style="margin-bottom:2px">${fmt(n.datum)} &rarr; dunkel ${hhmm(n.dunkel[0])}&ndash;${hhmm(n.dunkel[1])}</h3>
      <div class="help" style="max-width:none">Mond ${n.mond_beleuchtung} % &middot; `+(w?`Bewoelkung im Mittel <span class="pill ${AMP[n.ampel]||'n'}">${Math.round(w.wolken)} %</span> (max. tief ${r0(w.tief)} / mittel ${r0(w.mittel)} / hoch ${r0(w.hoch)} %)`:'Wetter: keine Vorhersage')+` &middot; ${n.anzahl} beobachtbare Transits</div>`;
    if(!n.vorschlaege.length){ h+='<p class="help">Kein passender Transit.</p>'; continue; }
    h+=planKurve(n);
    h+=`<table><tr><th></th><th>Score</th><th>Planet</th><th>Prio</th><th>mag</th><th>Tiefe ppt</th><th>SNR</th><th>Beobachten</th><th>Ingress / Tc / Egress</th><th>X max</th><th>Wolken</th><th>RA / Dec</th><th>Hinweise</th></tr>`+
      n.vorschlaege.map((s,j)=>`<tr><td><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${j<8?PLC[j%PLC.length]:'transparent'}"></span></td>
        <td>${Math.round(s.score)}</td><td style="white-space:nowrap"><b>${esc(s.planet)}</b></td><td>${esc(s.prio)}</td><td>${s.mag!=null?s.mag.toFixed(1):''}</td><td>${s.tiefe_ppt.toFixed(1)}</td><td>${s.snr??''}</td>
        <td style="white-space:nowrap">${hhmm(s.start)}&ndash;${hhmm(s.ende)}</td><td>${hhmm(s.ingress)} / ${hhmm(s.tc)} &plusmn;${s.tc_err_min} min / ${hhmm(s.egress)}</td><td>${s.airmass_max}</td>
        <td>${s.wetter?`<span class="pill ${AMP[s.ampel]||'n'}">${Math.round(s.wetter.wolken)} %</span>`:'?'}</td><td class="mono">${esc(s.ra)}<br>${esc(s.dec)}</td>
        <td>${esc(s.warnungen.concat(s.vergleichssterne!=null?[s.vergleichssterne+' Vergleichssterne']:[]).join('; '))}</td></tr>`).join('')+'</table>';
  }
  $('plan').innerHTML=h; }
init();
</script></body></html>"""
