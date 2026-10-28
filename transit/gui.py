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
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import FITS_EXT, PIPE_DIR, find_lights, unwrap
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
    return is_measurement(p) or os.path.isdir(os.path.join(p, "RESULT"))


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
    from .finden import all_measurements
    for e in grouped(all_measurements(False, log=lambda *x: None)):
        if os.path.normcase(p) in {os.path.normcase(x) for x in e["alle"]} and e["n_lights"]:
            return e["lights_pfad"]
    return p


def pick_folder():
    """Local folder dialog (tkinter, standard library); runs on this computer only."""
    import tkinter
    from tkinter import filedialog
    root = tkinter.Tk(); root.withdraw(); root.attributes("-topmost", True)
    try:
        return filedialog.askdirectory(parent=root, initialdir=BASE_DEFAULT, title="Messordner waehlen") or ""
    finally:
        root.destroy()


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


def candidates(p, lauf):
    """Candidates with Gaia flags (cached Gaia query) and, for the run's ensemble, the transit-window test."""
    d = os.path.join(p, "RESULT", lauf)
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
        det = gaia_details(Measurement(p, lauf), [r["source_id"] for r in rows], print)
    except Exception as e:
        print("Gaia:", e)
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
                        tw_flag=c.get("tw_flag"), ausgeschlossen=r["name"] in excl, ziel=r["role"] == "target"))
    fwhm, radii = None, []
    cubes = glob.glob(os.path.join(d, "cube_*.npz"))
    if cubes:
        import numpy as np
        z = np.load(cubes[0])
        fwhm, radii = float(np.nanmedian(z["fwhm"])), [float(x) for x in z["radii"]]
    return dict(kandidaten=out, feldbild=os.path.exists(os.path.join(d, "ergebnisblatt_feld.png")), fwhm=fwhm, radii=radii)


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


def start_run(q):
    """q: messordner, lauf, basis (optional run to reuse photometry from), mode, workers + advanced settings."""
    p = lights_folder(unwrap(os.path.abspath(q["messordner"])))   # results-only folder: run where the lights are
    if not is_measurement(p):
        raise ValueError(f"kein Messordner: {p}")
    ld = find_lights(p)
    if not any(f.lower().endswith(FITS_EXT) for f in os.listdir(ld)):
        raise ValueError(f"In {p} liegen keine Lights mehr (nur Ergebnisse). Liegen sie am NAS? 'Ordner waehlen...' oder 'Suchen' benutzen.")
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
    new_phot = new_stars or a.get("annulus") not in (None, "", []) or any(a.get(k) for k in ("flat", "bias", "dark"))
    if basis:                                              # reuse photometry of an existing run (same mode)
        import shutil
        src = os.path.join(p, "RESULT", basis)
        keep = ["inventory.json", "headers.csv", "gaia_field.csv", "gaia_details.json"]
        if not new_phot:                                   # changed candidates/annulus/masters -> new photometry
            keep += ["calib.json", "candidates.csv", "candidates_rejected.csv", f"cube_{mode}.npz"]
        for f in keep:
            if os.path.exists(os.path.join(src, f)) and not os.path.exists(os.path.join(out, f)):
                shutil.copy2(os.path.join(src, f), out)
    sec = {"target": {"planet": q.get("planet")}, "export": {"filter": q.get("filter")},
           "comps": {"exclude_stars": a.get("exclude_stars"), "dmag_bright": a.get("dmag_bright"), "dmag_faint": a.get("dmag_faint"),
                     "neighbour_px": a.get("neighbour_px"), "edge_px": a.get("edge_px")},
           "photometry": {"annulus": a.get("annulus"), "aperture_mode": a.get("aperture_mode"), "k_fwhm": a.get("k_fwhm")},
           "search": {"radii": a.get("radii"), "airmass_max": a.get("airmass_max"), "symmetry_weight": a.get("symmetry_weight")},
           "fit": {"airmass_order": a.get("airmass_order"), "flip": a.get("flip"), "fix_geometry": a.get("fix_geometry"),
                   "mcmc_steps": a.get("mcmc_steps")},
           "calib": {"flat": a.get("flat"), "bias": a.get("bias"), "dark": a.get("dark")}}
    write_lauf_toml(os.path.join(out, "lauf.toml"), sec, f"Lauf {lauf}" + (f", Photometrie aus {basis}" if basis else ""))
    cmd = [sys.executable, "-m", "transit", "run", p, "--out", lauf, "--mode", mode]
    if q.get("workers"):
        cmd += ["--workers", str(int(q["workers"]))]
    if new_stars:
        cmd += ["--new-stars"]
    log = open(os.path.join(out, "gui_konsole.txt"), "w", encoding="utf-8")
    env = dict(os.environ, PYTHONPATH=PIPE_DIR + os.pathsep + os.environ.get("PYTHONPATH", ""), PYTHONIOENCODING="utf-8")
    JOBS[(os.path.normcase(p), lauf)] = subprocess.Popen(cmd, cwd=PIPE_DIR, stdout=log, stderr=subprocess.STDOUT, env=env,
                                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return dict(ok=True, lauf=lauf, befehl=" ".join(cmd))


def run_cli(args):
    env = dict(os.environ, PYTHONPATH=PIPE_DIR + os.pathsep + os.environ.get("PYTHONPATH", ""), PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, "-m", "transit"] + args, cwd=PIPE_DIR, capture_output=True, text=True, env=env,
                       encoding="utf-8", errors="replace", timeout=600,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return dict(ok=r.returncode == 0, ausgabe=(r.stdout + r.stderr)[-4000:])


def allowed_file(path):
    """Only files inside <measurement>\\RESULT may be served."""
    p = os.path.abspath(path)
    parts = os.path.normcase(p).split(os.sep)
    if "result" not in parts:
        return False
    root = os.sep.join(p.split(os.sep)[:parts.index("result")])
    return listable(root) and os.path.isfile(p)


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
            if u.path == "/":
                b = PAGE.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
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
            elif u.path == "/api/kandidaten":
                self._json(candidates(os.path.abspath(q["pfad"]), q["lauf"]))
            elif u.path == "/datei":
                p = q.get("pfad", "")
                if not allowed_file(p):
                    self.send_error(403, "nur Dateien unter RESULT")
                    return
                b = open(p, "rb").read()
                self.send_response(200)
                self.send_header("Content-Type", mimetypes.guess_type(p)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
            else:
                self.send_error(404)
        except Exception as e:
            self._json(dict(fehler=str(e)), 500)

    def do_POST(self):
        if self.headers.get(TOKEN_HEADER) != "1":
            self.send_error(403); return
        q = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        try:
            if self.path == "/api/start":
                self._json(start_run(q))
            elif self.path == "/api/ordner":
                p = unwrap(os.path.normpath(pick_folder() or "."))
                if p in ("", "."):
                    self._json(dict(pfad=""))
                elif not listable(p):
                    self._json(dict(fehler=f"{p}: keine Lights gefunden (LIGHT, LIGHTS, LIGHT work, orig, _orig, _work oder FITS direkt im Ordner)"))
                else:
                    self._json(overview(p))
            elif self.path == "/api/ordner_oeffnen":
                d = os.path.join(os.path.abspath(q["messordner"]), "RESULT")
                if not os.path.isdir(d):
                    raise ValueError(f"{d} fehlt")
                os.startfile(d)
                self._json(dict(ok=True))
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
        except Exception as e:
            self._json(dict(ok=False, fehler=str(e)), 400)


def cmd_gui(a):
    url = f"http://127.0.0.1:{a.port}/"
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
   <span class="help">Quadratisch nur, wenn der BIC besser wird. Airmass-Grenze schneidet Randpunkte (Baseline vor Ingress >= 30 min lassen).</span>
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
  $('kand').innerHTML='<tr><th>an</th><th>Stern</th><th>G</th><th>BP-RP</th><th>RUWE</th><th>Gaia</th><th>Transitfenster</th></tr>'+K.kandidaten.filter(k=>!k.ziel).map(k=>{
    const ru=k.ruwe==null?'<span class="pill n">-</span>':`<span class="pill ${k.ruwe>1.4?'y':'g'}">${(+k.ruwe).toFixed(2)}</span>`;
    const va=k.var&&k.var.toUpperCase().startsWith('VARIABLE')?'<span class="pill r">VARIABLE</span>':'<span class="pill g">ok</span>';
    const tw=k.tw==null?'<span class="help">nur Ensemble</span>':`<span class="pill ${k.tw_flag?'r':'g'}">${(+k.tw).toFixed(1)} &plusmn; ${(+k.tw_e).toFixed(1)}</span>`;
    const off=k.ausgeschlossen||(k.var&&k.var.toUpperCase().startsWith('VARIABLE'))||k.tw_flag;
    return `<tr><td><input type="checkbox" class="kcb" value="${esc(k.name)}" ${off?'':'checked'}></td><td>${esc(k.name)}${k.im_ensemble?' *':''}</td><td>${k.G}</td><td>${k.bp_rp}</td><td>${ru}</td><td>${va}</td><td>${tw}</td></tr>`;}).join('')+
    '<tr><td colspan="7" class="help">* im Ensemble des Basislaufs. Vorschlag: VARIABLE und Transitfenster &gt; 3 sigma sind abgewaehlt.</td></tr>';
  const p=$('mess').value+'\\RESULT\\'+b+'\\ergebnisblatt_feld.png';
  $('feld').src=K.feldbild?('/datei?pfad='+encodeURIComponent(p)):'';
}
function num(id){const v=$(id).value;return v===''?null:+v;}
async function start(){
  const er={flat:$('flat').value||null,bias:$('bias').value||null,dark:$('dark').value||null,
    dmag_bright:num('dmag_bright'),dmag_faint:num('dmag_faint'),neighbour_px:num('neighbour_px'),edge_px:num('edge_px'),
    airmass_order:num('airmass_order'),airmass_max:num('airmass_max'),flip:$('flip').value||null,
    fix_geometry:$('fix_geometry').value===''?null:false,mcmc_steps:num('mcmc_steps'),symmetry_weight:num('symmetry_weight')};
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
  $('startmsg').textContent=r.ok?('gestartet: '+r.lauf+'\n'+r.befehl):('Fehler: '+r.fehler);
  aktualisiere();
}
async function gueltig(l,p){ p=p||$('mess').value; if(!confirm('Lauf '+l+' als gueltige Messung dieser Nacht setzen? Die Upload-Datei unter RESULT\\ wird ersetzt.'))return;
  const r=await (await fetch('/api/gueltig',{method:'POST',headers:H,body:JSON.stringify({messordner:p,lauf:l})})).json();
  $('startmsg').textContent=r.ausgabe||r.fehler; lade(); }
async function aij(l,p){ p=p||$('mess').value; const r=await (await fetch('/api/aij',{method:'POST',headers:H,body:JSON.stringify({messordner:p,lauf:l})})).json(); $('startmsg').textContent=r.ausgabe||r.fehler; }
function blatt(l,p){ const b=(p||$('mess').value)+'\\RESULT\\'+l+'\\'; $('blattcard').style.display=''; $('blatttitel').textContent='Ergebnisblatt '+l;
  $('blatt').src='/datei?pfad='+encodeURIComponent(b+'ergebnisblatt.png')+'&t='+Date.now(); $('blatt2').src='/datei?pfad='+encodeURIComponent(b+'ergebnisblatt_feld.png')+'&t='+Date.now();
  $('blattcard').scrollIntoView({behavior:'smooth'}); }
init();
</script></body></html>"""
