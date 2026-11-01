"""English comment for the ExoClock upload form, generated from the files of one run (no recomputation).

transit kommentar <Messordner> [--lauf L]   prints it and copies it to the clipboard (valid run by default).
Also appended to exoclock_formular.txt by transit export.  Extra fixed text: [export] kommentar_zusatz.
"""
import csv
import json
import os
import subprocess
from datetime import datetime

import numpy as np

MAXLEN = 300


def _j(out, name):
    p = os.path.join(out, name)
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def valid_run(root):
    from .ergebnisblatt import VALID, logbook_read
    rows = [r for r in logbook_read() if os.path.normcase(root) in (os.path.normcase(r["messordner"]), os.path.normcase(r.get("archiv") or "-"))
            and r["status"] == VALID]
    if not rows:
        raise SystemExit("Kein gueltiger Lauf im Logbuch - --lauf <name> angeben")
    return rows[0]["lauf"]


def make(out, cfg=None):
    """Short remark (1-2 sentences, ~300 chars) with only what ExoClock cannot see in the data; "No special remarks." else.
    Frame count, exposure, time format, own fit values and the standard method are deliberately left out."""
    fr, cj, inv = _j(out, "fit.json"), _j(out, "calib.json"), _j(out, "inventory.json")
    if not fr:
        raise SystemExit(f"{out}: keine fit.json - Lauf nicht fertig")
    hp = os.path.join(out, "headers.csv")
    hdr = list(csv.DictReader(open(hp, encoding="utf-8"))) if os.path.exists(hp) else []
    hdr = [h for h in hdr if not any(w in str(h.get("IMAGETYP", "")).upper() for w in ("BIAS", "DARK", "FLAT", "MASTER"))]
    info, mc, pred = fr["info"], fr["mcmc"], fr["ephemeris"]
    cfg = cfg or {}
    r = []                                                 # in order of importance
    checks = json.dumps(inv.get("checks", []))
    if info.get("flip_mode", "none") != "none" and "im/nahe am Transit" in checks:
        r.append("Meridian flip during the transit; the flux step was corrected with a prior measured on the comparison stars.")
    r.append(clipping_text(out, cfg))                     # reviewers ask for it: always stated
    if info.get("ensemble_fest"):
        r.append(f"Comparison stars selected manually ({', '.join(info['ensemble_fest'])}).")
    comps = comps_text(out, info, fr)
    if comps:
        r.append(comps)
    tc = fr.get("tc_check") or {}
    if tc.get("ampel") in ("gelb", "rot"):
        r.append("Tc profile shows a second, almost equal minimum: the timing may be ambiguous."
                 if tc.get("taeler") else "Tc shifts when the depth is fixed to the literature value: timing depends on the depth.")
    want, eff = cj.get("mode"), cj.get("mode_effektiv") or cj.get("mode")
    if eff in ("raw", "b"):
        r.append("No flat-field correction (no matching flat available).")
    elif cj.get("flat") and cj["flat"].get("date") and hdr:
        age = (datetime.fromisoformat(hdr[0]["DATE-OBS"][:19]) - datetime.fromisoformat(str(cj["flat"]["date"])[:19])).days
        if abs(age) > 60:
            r.append(f"Flat field {abs(age)} days {'older' if age > 0 else 'newer'} than the observations.")
    exps = sorted({float(h["EXPTIME"]) for h in hdr if h.get("EXPTIME")})
    if len(exps) > 1 and sum(float(h["EXPTIME"]) != exps[-1] for h in hdr) > 1:
        r.append(f"Alternating exposures {' / '.join(f'{e:g}' for e in exps)} s; the form shows the median.")
    terr = (mc["Tc"][2] - mc["Tc"][0]) / 2 * 1440
    if exps and max(exps) < 10:
        r.append("Very short exposures: scintillation-limited, hence the large timing uncertainty.")
    elif terr > 5:
        r.append("Low timing precision (noisy data).")
    t = sorted(datetime.fromisoformat(h["DATE-OBS"][:19]).timestamp() for h in hdr if h.get("DATE-OBS"))
    if len(t) > 3:
        g = np.diff(t); cad = np.median(g)
        big = [(i, d) for i, d in enumerate(g) if d > max(5 * cad, 600)]
        if big:
            r.append(f"Data gap(s) of {', '.join(f'{d / 60:.0f}' for _, d in big[:3])} min (clouds/interruption).")
    if cfg.get("export", {}).get("filter") and not any(h.get("FILTER") for h in hdr):
        r.append("Filter not in the FITS header; taken from the observer's notes.")
    extra = str(cfg.get("export", {}).get("kommentar_zusatz", "") or "").strip()
    if extra:
        r.insert(0, extra)
    text = ""
    for x in r:                                            # keep the most important remarks within ~300 characters
        if len(text) + len(x) + 1 > MAXLEN:
            break
        text = (text + " " + x).strip()
    return text or "No special remarks."


def clipping_text(out, cfg):
    """Sigma clipping against the transit fit, from ausreisser.json (written only when the option was on)."""
    sig = float((cfg.get("fit") or {}).get("ausreisser_sigma") or 0)
    ar = _j(out, "ausreisser.json")
    if not sig or not ar:
        return "No sigma clipping."
    fr = ar.get("frames", [])
    n = len(fr)
    when = ""
    if 0 < n <= 3:
        from astropy.time import Time
        when = " (" + ", ".join(Time(f["bjd_tdb"], format="jd").datetime.strftime("%H:%M") for f in fr) + " UT, approx.)"
    return f"{ar.get('sigma', sig):g}-sigma clipping against the transit fit: {n} point{'s' if n != 1 else ''} removed{when}."


def comps_text(out, info, fr):
    """Comparison stars left out on purpose: by the observer, by the noise/variability pre-filter, by the single-star test."""
    cs = _j(out, "compsearch.json")
    pre = [p["name"] for p in cs.get("prefilter", []) if p.get("rejected")]
    var = [p["name"] for p in cs.get("prefilter", []) if p.get("rejected") and p.get("variabel")]
    ein = [s["name"] for s in (fr.get("einzel") or cs.get("einzel") or {}).get("stars", []) if s.get("verworfen")]
    own = list(info.get("excluded_stars") or [])
    parts = []
    if own:
        parts.append(f"{', '.join(own)} excluded by the observer")
    noisy = [x for x in pre if x not in var]
    if var:
        parts.append(f"{', '.join(var)} rejected as variable")
    if noisy:
        parts.append(f"{', '.join(noisy)} rejected as too noisy")
    if ein:
        parts.append(f"{', '.join(ein)} rejected (depth from that star alone far off)")
    if not parts:
        return ""
    return "Comparison stars: " + "; ".join(parts) + "."


def baseline_min(t, pred, cfg):
    """Minutes from the first frame to the predicted ingress and from the predicted egress to the last frame (BJD_TDB)."""
    try:
        from astropy.coordinates import EarthLocation, SkyCoord
        from astropy.time import Time
        import astropy.units as u
        tg, si = cfg["target"], cfg["site"]
        tt = Time([t[0].isoformat(), t[-1].isoformat()], scale="utc")
        loc = EarthLocation(lat=float(si["lat"]) * u.deg, lon=float(si["lon"]) * u.deg, height=float(si["elev"]) * u.m)
        b = (tt.tdb + tt.light_travel_time(SkyCoord(float(tg["ra"]) * u.deg, float(tg["dec"]) * u.deg), location=loc)).jd
        return (pred["ingress"] - b[0]) * 1440, (b[1] - pred["egress"]) * 1440
    except Exception:
        return float("nan"), float("nan")


def load_cfg(root, lauf):
    import tomllib
    from .config import DEFAULT_TOML, _merge
    cfg = tomllib.load(open(DEFAULT_TOML, "rb"))
    for p in (os.path.join(root, "RESULT", "transit.toml"), os.path.join(root, "RESULT", lauf, "lauf.toml")):
        if os.path.exists(p):
            cfg = _merge(cfg, tomllib.load(open(p, "rb")))
    return cfg


def to_clipboard(text):
    try:
        subprocess.run(["clip"], input=text.encode("utf-16-le"), check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True
    except Exception:
        return False


def cmd_kommentar(a):
    root = os.path.abspath(a.messordner)
    lauf = a.lauf or valid_run(root)
    text = make(os.path.join(root, "RESULT", lauf), load_cfg(root, lauf))
    print(f"Kommentar fuer ExoClock ({lauf}, {len(text)} Zeichen):\n")
    print(text)
    print("\n-> in die Zwischenablage kopiert" if to_clipboard(text) else "\n(Zwischenablage nicht verfuegbar - bitte markieren und kopieren)")
