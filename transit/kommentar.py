"""English comment for the ExoClock upload form, generated from the files of one run (no recomputation).

transit kommentar <Messordner> [--lauf L]   prints it and copies it to the clipboard (valid run by default).
Also appended to exoclock_formular.txt by transit export.  Extra fixed text: [export] kommentar_zusatz.
After the remarks: the comparison-star ensemble (Gaia DR3 ID, G, BP-RP, distance to the target), switch
[export] kommentar_sterne = false; whole comment at most [export] kommentar_max characters (default 1400).
"""
import csv
import glob
import json
import os
import subprocess
from datetime import datetime

import numpy as np

MAXLEN_ALLES = 1400   # whole comment incl. the comparison-star list ([export] kommentar_max)
STERN_PLATZ = 350     # room kept free for the comparison-star list


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
    """Comment for the ExoClock reviewers, most important facts first (whatever does not fit in [export] kommentar_max
    falls away from the end): coverage of the contacts and baselines, every gap in the uploaded data with cause and
    position, frames used/removed per reason, meridian flip and detrending, comparison-star decisions, timing doubts,
    calibration, sigma clipping, camera/exposure/filter notes, then the comparison-star list with a legend."""
    fr, cj = _j(out, "fit.json"), _j(out, "calib.json")
    if not fr:
        raise SystemExit(f"{out}: keine fit.json - Lauf nicht fertig")
    hp = os.path.join(out, "headers.csv")
    hdr = list(csv.DictReader(open(hp, encoding="utf-8"))) if os.path.exists(hp) else []
    hdr = [h for h in hdr if not any(w in str(h.get("IMAGETYP", "")).upper() for w in ("BIAS", "DARK", "FLAT", "MASTER"))]
    info, pred = fr["info"], fr["ephemeris"]
    cfg = cfg or {}
    ex = cfg.get("export", {})
    r = []                                                 # in order of importance for the reviewer
    extra = str(ex.get("kommentar_zusatz", "") or "").strip()
    if extra:
        r.append(extra)
    st = frame_status(out, fr, cfg)
    if st is not None:
        r += coverage_text(st, pred)
        r.append(frames_text(st, hdr, _j(out, "inventory.json")))
    fl = flip_text(out, info, pred, hdr, fr.get("tests"), fr.get("flip_target"), fr.get("best"))
    r.append(fl or "Uploaded fluxes are not detrended (airmass left to the ExoClock fit).")
    if info.get("ensemble_fest"):
        r.append(f"Comparison stars selected manually ({', '.join(info['ensemble_fest'])}).")
    comps = comps_text(out, info, fr)
    if comps:
        r.append(comps)
    tc = fr.get("tc_check") or {}
    if tc.get("ampel") in ("gelb", "rot"):
        r.append("Tc profile shows a second, almost equal minimum: the timing may be ambiguous."
                 if tc.get("taeler") else "Tc shifts when the depth is fixed to the literature value: timing depends on the depth.")
    ca = calib_text(cj, hdr)
    if ca:
        r.append(ca)
    r.append(clipping_text(out, cfg))
    osc = colour_text(out)
    if osc:
        r.append(osc)
    exps = sorted({float(h["EXPTIME"]) for h in hdr if h.get("EXPTIME")})
    if len(exps) > 1 and sum(float(h["EXPTIME"]) != exps[-1] for h in hdr) > 1:
        r.append(f"Alternating exposures {' / '.join(f'{e:g}' for e in exps)} s; the form shows the median.")
    if exps and max(exps) < 10:
        r.append("Very short exposures: scintillation-limited, hence the large timing uncertainty.")
    if ex.get("filter") and not any(h.get("FILTER") for h in hdr):
        r.append("Filter not in the FITS header; taken from the observer's notes.")
    lim = int(ex.get("kommentar_max") or MAXLEN_ALLES)
    sterne = ex.get("kommentar_sterne", True)
    budget = lim - (STERN_PLATZ if sterne else 0)
    text = ""
    for x in r:                                            # most important first; what does not fit is left out
        if len(text) + len(x) + 1 <= budget:
            text = (text + " " + x).strip()
    text = text or "No special remarks."
    if sterne:
        st_ = ensemble_text(out, fr, lim - len(text) - 1)
        if st_:
            text += " " + st_
    return text


def _cube(out):
    p = sorted(glob.glob(os.path.join(out, "cube_*.npz")))
    if not p:
        return None
    with np.load(p[0]) as z:
        return {k: z[k] for k in z.files}


def _hm(jd):
    from astropy.time import Time
    return Time(float(jd) + 30 / 86400, format="jd").datetime.strftime("%H:%M")    # rounded to the minute


def frame_status(out, fr, cfg):
    """Per frame of the cube: why it is not in the uploaded light curve ('' = used).  Same rules as analysis.Night
    (frame list, airmass cut, clouds, saturation, missing flux, sigma clipping); 'used' itself is taken from the
    exported ExoClock file when it exists, so the comment describes exactly what ExoClock gets."""
    c = _cube(out)
    if c is None:
        return None
    info = fr.get("info") or {}
    nf = len(c["jd_start"])
    names = [str(x) for x in c["star_name"]]
    why = np.array([""] * nf, dtype=object)
    se = cfg.get("search") or {}
    ff = np.array([str(x) for x in c["frame_file"]]) if "frame_file" in c else np.array([""] * nf)
    ar = {d.get("frame") for d in _j(out, "ausreisser.json").get("frames", [])}
    why[np.isin(ff, list(ar))] = "clip"
    why[np.isin(ff, list(se.get("exclude_frames") or []))] = "list"
    amax = float(se.get("airmass_max") or 0)
    if amax and "airmass_calc" in c:
        why[(why == "") & (c["airmass_calc"] > amax)] = "airmass"
    skip = set(info.get("dropped_saturating") or []) | set(info.get("excluded_stars") or [])
    cand = [j for j in range(1, len(names)) if names[j] not in skip]
    if info.get("excluded_clouds") and cand:
        from .analysis import cloud_frames
        rad = list(c["radii"])
        ir = rad.index(16) if 16 in rad else len(rad) // 2
        csum = np.where(why == "", np.nansum(c["flux"][:, cand, ir], axis=1), np.nan)
        why[(why == "") & cloud_frames(csum, float(info.get("wolken_schwelle", 0.5)))[1]] = "cloud"
    sat = float((cfg.get("camera") or {}).get("saturation_adu") or 0)
    if sat:
        why[(why == "") & np.any(c["peak_raw"][:, [0] + cand] > sat, axis=1)] = "sat"
    why[(why == "") & ~np.all(np.isfinite(c["flux"][:, [0] + cand, :]).reshape(nf, -1), axis=1)] = "nan"
    used = why == ""
    ex = glob.glob(os.path.join(out, "*_exoclock_JDUTC.txt"))
    if ex:
        try:
            jd = np.loadtxt(ex[0], comments="#", usecols=0, ndmin=1)
            jd = np.sort(jd)
            k = np.clip(np.searchsorted(jd, c["jd_start"]), 1, max(len(jd) - 1, 1))
            near = np.minimum(abs(c["jd_start"] - jd[k - 1]), abs(c["jd_start"] - jd[np.minimum(k, len(jd) - 1)]))
            used = near < 2 / 86400                          # same frame (export writes 7 decimals)
            why[used] = ""
            why[~used & (why == "")] = "other"
        except Exception:
            pass
    return dict(jd=c.get("jd_utc_mid", c["jd_start"]), bjd=c["bjd_tdb"], east=c.get("east"), why=why, used=used)


def _lage(a, b, I, E, Tc):
    """Where the span a..b (JD) lies relative to the predicted contacts."""
    def p(x):
        if x < I:
            return "before ingress"
        if x > E:
            return "after egress"
        return "first half of the transit" if x < Tc else "second half of the transit"
    pa, pb = p(a), p(b)
    if a < I < b and b < E:
        return "across ingress"
    if I < a < E < b:
        return "across egress"
    if a < I and b > E:
        return "the whole transit"
    if pa == pb and pa in ("before ingress", "after egress"):
        return pa
    if I <= a and b <= E:
        return f"in transit, {(a - Tc) * 1440:+.0f} to {(b - Tc) * 1440:+.0f} min from mid-transit"
    return f"{pa} to {pb}"


WARUM = dict(sat="saturated", cloud="clouds", list="excluded by the observer",
             airmass="above the airmass limit", nan="no valid photometry", clip="sigma clipping", other="not used in the fit")


GRUND = dict(sat="target or a comparison star saturated", cloud="clouds")


def coverage_text(st, pred):
    """Coverage (contacts and baselines in UT) and every gap in the uploaded data with cause and position."""
    jd, used = st["jd"], st["used"]
    if used.sum() < 3:
        return []
    off = float(np.nanmedian(st["bjd"] - jd))                  # BJD_TDB - JD_UTC: predicted contacts in UT
    I, E, Tc = pred["ingress"] - off, pred["egress"] - off, pred["Tc"] - off
    allt = np.sort(jd)
    cad = float(np.median(np.diff(allt))) if len(allt) > 2 else 0.0
    lim = max(10 / 1440, 5 * cad)
    tu = np.sort(jd[used])
    # gaps in the used data; gaps with only a few points between them (< 6 within 20 min) are merged into one
    gaps = [[tu[i], tu[i + 1]] for i in np.where(np.diff(tu) > lim)[0]]
    merged = []
    for g in gaps:
        if merged and g[0] - merged[-1][1] < 20 / 1440 and ((tu > merged[-1][1]) & (tu < g[0])).sum() < 6:
            merged[-1][1] = g[1]
        else:
            merged.append(list(g))
    lines = []
    pre, post = (I - tu[0]) * 1440, (tu[-1] - E) * 1440
    ing = tu[0] < I - 5 / 1440 and not any(a < I + 10 / 1440 and b > I - 10 / 1440 for a, b in merged)
    egr = tu[-1] > E + 5 / 1440 and not any(a < E + 10 / 1440 and b > E - 10 / 1440 for a, b in merged)
    kontakt = ("Ingress and egress observed" if ing and egr else "Ingress observed, egress not covered" if ing
               else "Egress observed, ingress not covered" if egr else "Neither ingress nor egress covered")
    base = []
    base.append(f"{pre:.0f} min before ingress" if pre > 0 else "none before ingress")
    base.append(f"{post:.0f} min after egress" if post > 0 else "none after egress")
    lines.append(f"Coverage {_hm(tu[0])}-{_hm(tu[-1])} UT (predicted ingress {_hm(I)}, egress {_hm(E)} UT): "
                 f"{kontakt}; baseline {' and '.join(base)}.")
    if not merged:
        lines.append("No gaps in the uploaded data.")
        return lines
    parts = []
    for a, b in merged[:3]:
        inn = (jd > a) & (jd < b)
        left = int((used & inn).sum())
        cnt = {}
        for w in st["why"][inn & ~used]:
            cnt[w] = cnt.get(w, 0) + 1
        why = [f"{GRUND.get(w, WARUM.get(w, w))} in {k} frame{'s' if k != 1 else ''}" for w, k in sorted(cnt.items(), key=lambda x: -x[1])]
        ta = np.sort(jd[inn | (jd == a) | (jd == b)])
        e = st.get("east")
        for x, y in zip(ta, ta[1:]):                       # no frames taken: flip pause or interruption
            flip = e is not None and e[np.argmin(abs(jd - x))] != e[np.argmin(abs(jd - y))]
            if flip or y - x > lim:
                why.append(f"{'meridian flip' if flip else 'no frames recorded'} {_hm(x)}-{_hm(y)}")
        s = f"{_hm(a)}-{_hm(b)} UT ({(b - a) * 1440:.0f} min, {_lage(a, b, I, E, Tc)}"
        s += f"; only {left} scattered points left)" if left else ")"
        parts.append(s + (": " + ", ".join(why) if why else ""))
    lines.append(("Gap in the uploaded data: " if len(parts) == 1 else "Gaps in the uploaded data: ") + "; ".join(parts) + ".")
    return lines


def frames_text(st, hdr, inv):
    """Frames taken / used and the frames removed per reason."""
    n, u = len(st["why"]), int(st["used"].sum())
    exps = sorted({float(h["EXPTIME"]) for h in hdr if h.get("EXPTIME")})
    t = np.sort(st["jd"])
    cad = float(np.median(np.diff(t))) * 86400 if n > 2 else 0
    s = f"{n} frames" + (f" of {exps[0]:g} s" if len(exps) == 1 else "") + (f" (cadence {cad:.0f} s)" if cad else "")
    cnt = {}
    for w in st["why"][~st["used"]]:
        cnt[w] = cnt.get(w, 0) + 1
    rm = [f"{k} {WARUM.get(w, w)}" for w, k in sorted(cnt.items(), key=lambda x: -x[1])]
    d = len((inv or {}).get("defekt") or [])
    if d:
        rm.append(f"{d} unreadable file{'s' if d != 1 else ''} skipped")
    return s + f", {u} used" + (" (removed: " + "; ".join(rm) + ")" if rm else "") + "."


def calib_text(cj, hdr):
    eff = cj.get("mode_effektiv") or cj.get("mode")
    if not eff:
        return ""
    was = {"raw": "none (no calibration frames)", "b": "bias only, no flat field", "f": "flat field only (no bias/dark on the lights)",
           "bf": "bias and flat field", "bfd": "bias, dark and flat field"}.get(eff, eff)
    s = f"Calibration: {was}"
    if eff in ("f", "bf", "bfd") and (cj.get("flat") or {}).get("date") and hdr:
        try:
            age = (datetime.fromisoformat(hdr[0]["DATE-OBS"][:19]) - datetime.fromisoformat(str(cj["flat"]["date"])[:19])).days
            if abs(age) > 60:
                s += f"; flat {abs(age)} days {'older' if age > 0 else 'newer'} than the data"
        except ValueError:
            pass
    return s + "."


def colour_text(out):
    """Colour (Bayer/OSC) camera: photometry on 2x2 superpixels (pixbin in the cube; see photometry.measure)."""
    for p in sorted(glob.glob(os.path.join(out, "cube_*.npz"))):
        try:
            with np.load(p) as z:
                if "pixbin" in z.files and int(z["pixbin"]) > 1:
                    b = int(z["pixbin"])
                    return f"Colour (Bayer) camera: photometry on {b}x{b} superpixels (no debayering)."
        except Exception:
            continue
        return ""
    return ""


def _sep_arcmin(ra1, de1, ra2, de2):
    r1, d1, r2, d2 = map(np.radians, (ra1, de1, ra2, de2))
    c = np.sin(d1) * np.sin(d2) + np.cos(d1) * np.cos(d2) * np.cos(r1 - r2)
    return float(np.degrees(np.arccos(np.clip(c, -1, 1))) * 60)


def _f(x):
    try:
        v = float(x)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def ensemble_text(out, fr, room):
    """Target and comparison stars of the final ensemble, with a legend so a reviewer need not guess the format:
    "Target G 8.6, BP-RP 0.67. Comparison ensemble used for the light curve (5 stars), Gaia DR3 ID
    (G mag / BP-RP / separation from target):
    3438063011972005120 (10.0 / 0.63 / 6.5'); ..."  From fit.json (best.comps/gaia) and candidates.csv.
    Fits into `room` characters; stars that do not fit are counted ("+2 more")."""
    best = fr.get("best") or {}
    names, ids = list(best.get("comps") or []), [str(x) for x in (best.get("gaia") or [])]
    if not names:
        return ""
    cp = os.path.join(out, "candidates.csv")
    cand = {r["name"]: r for r in csv.DictReader(open(cp, encoding="utf-8"))} if os.path.exists(cp) else {}
    tg = next((r for r in cand.values() if r.get("role") == "target"), None)
    tpos = tg and None not in (_f(tg.get("ra")), _f(tg.get("dec")))
    ziel = ""
    if tg and _f(tg.get("G")) is not None:
        ziel = f"Target G {_f(tg['G']):.1f}" + (f", BP-RP {_f(tg.get('bp_rp')):.2f}" if _f(tg.get("bp_rp")) is not None else "") + ". "
    legend = "G mag / BP-RP" + (" / separation from target" if tpos else "")
    head = f"{ziel}Comparison ensemble used for the light curve ({len(names)} star{'s' if len(names) != 1 else ''}), Gaia DR3 ID ({legend})"
    items = []
    for k, n in enumerate(names):
        c = cand.get(n, {})
        sid = ids[k] if k < len(ids) else str(c.get("source_id", "") or n)
        g, col = _f(c.get("G")), _f(c.get("bp_rp"))
        val = [f"{g:.1f}" if g is not None else "-", f"{col:.2f}" if col is not None else "-"]
        if tpos:
            ra, de = _f(c.get("ra")), _f(c.get("dec"))
            val.append(f"{_sep_arcmin(ra, de, float(tg['ra']), float(tg['dec'])):.1f}'" if None not in (ra, de) else "-")
        items.append(f"{sid} ({' / '.join(val)})")
    for k in range(len(items), 0, -1):                   # as many stars as fit, the rest counted
        rest = len(items) - k
        text = head + ": " + "; ".join(items[:k]) + (f"; +{rest} more" if rest else "") + "."
        if len(text) <= room:
            return text
    return ""


def flip_text(out, info, pred, hdr, fr_tests=None, flip_target=None, fr_best=None):
    """Where the meridian flip lies relative to the predicted transit, and how the flux step was handled.
    Flip time = middle of the pause between the last frame on one pier side and the first on the other (as in inventory)."""
    mode = info.get("flip_mode", "none")
    tf = (_j(out, "compsearch.json").get("flip") or {}).get("t_flip_bjd")   # first frame after the flip
    if mode == "none" or tf is None:
        return ""
    fr = sorted((datetime.fromisoformat(h["DATE-OBS"][:19]), h.get("PIERSIDE", "")) for h in hdr if h.get("DATE-OBS"))
    for (a, sa), (b, sb) in zip(fr, fr[1:]):
        if sa != sb:
            tf -= (b - a).total_seconds() / 2 / 86400
            break
    if tf < pred["ingress"]:
        lage = f"{(pred['ingress'] - tf) * 1440:.0f} min before ingress"
    elif tf > pred["egress"]:
        lage = f"{(tf - pred['egress']) * 1440:.0f} min after egress"
    else:
        lage = f"during the transit, {(tf - pred['ingress']) * 1440:.0f} min after ingress"
    step = ((fr_tests or {}).get("alle_fest") or {}).get("flip_ppt")
    wert = f": {step:+.1f} ppt," if step is not None else ""
    ft = flip_target if mode == "prior" else None
    fl = _j(out, "compsearch.json").get("flip") or {}
    n = int(fl.get("n_stars") or 0)
    if ft:
        quelle = f"measured on {n} field stars" if n else "measured on the field stars"
        ens = set((fr_best or {}).get("comps") or [])
        drin = len(ens & {s_["name"] for s_ in fl.get("stars", [])})
        if ens and drin == len(ens):
            quelle += " (incl. the comparison stars)"
        elif drin:
            quelle += f" (incl. {drin} of the {len(ens)} comparison stars)"
        how = f"Flux step across the flip{wert} fitted with a prior ({ft[0] * 1e3:+.1f} +/- {ft[1] * 1e3:.1f} ppt) {quelle}"
    else:
        how = f"Flux step across the flip{wert} fitted as a free parameter"
    return f"Meridian flip {lage}. {how}; the uploaded fluxes are corrected for it, otherwise not detrended."


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
