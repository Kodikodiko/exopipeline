"""Command line: transit <befehl> <messordner> [optionen].  'transit hilfe' fuer die deutsche Hilfe."""
import argparse
import csv
import json
import os
import subprocess
import sys
import time

import numpy as np

from . import progress, safety
from .config import Measurement, write_measurement_toml

LOG = []


def log(*a):
    s = " ".join(str(x) for x in a)
    LOG.append(s)
    progress.clear_line()
    print(s, flush=True)
    progress.runlog(s)


def jdump(obj, path):
    def conv(o):
        if isinstance(o, (np.floating, np.integer)):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
        return str(o)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, default=conv, ensure_ascii=False)


def jload(m, name):
    p = m.path(name)
    if not os.path.exists(p):
        raise SystemExit(f"{name} fehlt - zuerst den vorherigen Schritt ausfuehren (transit hilfe ablauf)")
    return json.load(open(p, encoding="utf-8"))


# ------------------------------------------------------------------ common context
def context(m):
    from .frames import read_headers, times, target_coord
    from .ephem import planet_params, predict
    hd = read_headers(m)
    if not hd:
        raise SystemExit("Keine FITS-Dateien im Light-Ordner")
    tm = times(m, hd)
    planet = m.cfg.get("target", {}).get("planet") or str(hd[0]["header"].get("OBJECT", "")).strip()
    par = planet_params(planet)
    pred = predict(par, float(np.mean(tm["bjd_tdb"])))
    return hd, tm, par, pred, target_coord(m, hd[0]["header"])


# ------------------------------------------------------------------ inventory
def cmd_inventory(m, a):
    from .frames import read_headers, KEYS
    from .checks import night_checks
    from astropy.coordinates import SkyCoord
    import astropy.units as u
    st = safety.record(m, full=a.full)
    log(f"Pruefsummen fuer {len(st)} Light-Dateien gespeichert ({'voll' if a.full else 'schnell'})")
    hd = read_headers(m)
    with open(m.path("headers.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh); w.writerow(["file", "size", "solved"] + KEYS)
        for x in hd:
            w.writerow([os.path.basename(x["file"]), x["size"], x["solved"]] + [x["header"].get(k, "") for k in KEYS])
    h0 = hd[0]["header"]
    if not os.path.exists(m.cfg_path):
        name = str(m.cfg.get("target", {}).get("planet") or h0.get("OBJECT", "")).strip()   # e.g. set by the GUI in lauf.toml
        c = SkyCoord(h0["OBJCTRA"], h0["OBJCTDEC"], unit=(u.hourangle, u.deg))
        from .ephem import planet_params
        try:
            p = planet_params(name)
            c = SkyCoord(p["ra"], p["dec"], unit=(u.hourangle, u.deg))
            log(f"Zielkoordinaten aus ExoClock ({p['name']})")
        except SystemExit:
            log("Planet nicht im Katalog - Zielkoordinaten aus OBJCTRA/OBJCTDEC (bitte pruefen)")
        write_measurement_toml(m, name, round(c.ra.deg, 7), round(c.dec.deg, 7), name)
        m.__init__(m.root, os.path.basename(m.out))
        log(f"Konfiguration angelegt: {m.cfg_path}")
    hd, tm, par, pred, tgt = context(m)
    inv = dict(n_frames=len(hd), n_solved=sum(x["solved"] for x in hd), sizes=sorted({x["size"] for x in hd}),
               filters=sorted({str(x["header"].get("FILTER")) for x in hd}),
               exptimes=sorted({float(x["header"].get("EXPTIME", 0)) for x in hd}),
               ccd_temp=[float(np.nanmin(tm_ := [x["header"].get("CCD-TEMP", np.nan) for x in hd])), float(np.nanmax(tm_))],
               date_first=hd[0]["header"]["DATE-OBS"], date_last=hd[-1]["header"]["DATE-OBS"], target=str(tgt.to_string("hmsdms")),
               ephemeris=pred, planet=par, checks=night_checks(m, hd, tm, pred))
    jdump(inv, m.path("inventory.json"))
    log(f"{inv['n_frames']} Frames, {inv['n_solved']} mit WCS, Filter {inv['filters']}, Belichtung {inv['exptimes']} s, "
        f"CCD {inv['ccd_temp'][0]:.1f}..{inv['ccd_temp'][1]:.1f} C")
    log(f"Ephemeride {pred['source']}: Tc {pred['Tc']:.5f} +- {pred['Tc_err']:.5f} BJD_TDB, "
        f"Ingress {pred['ingress']:.5f}, Egress {pred['egress']:.5f}")
    for c in inv["checks"]:
        log(f"  [{c['level']}] {c['text']}" + (f"\n         -> {c['fix']}" if c.get("fix") else ""))


# ------------------------------------------------------------------ solve
def cmd_solve(m, a):
    from .frames import read_headers
    import shutil
    hd = read_headers(m)
    todo = [x for x in hd if not x["solved"]]
    if not todo:
        log("Alle Frames haben bereits WCS."); return
    out = m.dir("SOLVED")
    exe = m.cfg["paths"]["astap"]
    if not os.path.exists(exe):
        raise SystemExit(f"ASTAP nicht gefunden: {exe} ([paths] astap)")
    ok = 0
    bar = progress.task("ASTAP", len(todo), "Frames")
    for x in todo:
        dst = safety.guard_write(m, os.path.join(out, os.path.basename(x["file"])))
        shutil.copy2(x["file"], dst)
        cmd = [exe, "-f", dst, "-r", str(a.radius), "-update"]
        hh = x["header"]
        foc = hh.get("FOCALLEN") or m.cfg["camera"].get("focal_mm")
        pix = hh.get("XPIXSZ") or m.cfg["camera"].get("pixel_um", 3.76) * (hh.get("XBINNING") or 1)   # binned pixel [um]
        if foc:
            cmd += ["-fov", f"{hh['NAXIS2'] * pix * 1e-3 / foc * 57.2958:.3f}"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        from astropy.io import fits
        solved = "CTYPE1" in fits.getheader(dst)
        ok += solved
        log(f"  {os.path.basename(dst)}: {'geloest' if solved else 'NICHT geloest'} ({r.returncode})")
        if not solved and not a.keep_failed:
            os.remove(dst)
        bar.update()
    bar.done()
    log(f"{ok}/{len(todo)} Frames geloest -> {out}")


# ------------------------------------------------------------------ calibrate
def cmd_calibrate(m, a):
    from .calib import scan_library, match, estimate_dark_scale
    from .frames import read_headers
    from datetime import datetime
    hd = read_headers(m)
    h0 = hd[0]["header"]
    night = datetime.strptime(h0["DATE-OBS"][:10], "%Y-%m-%d")
    lib = m.cfg["calib"]["library"]
    if m.cfg["calib"].get("master_dir"):
        lib = m.cfg["calib"]["master_dir"]
    rows = scan_library(lib)
    mt = match(rows, h0, night)
    # masters inside the measurement's own light folder belong to this camera/night: use them (size must match;
    # gain/offset/instrument are often missing in their headers)
    exp0 = float(h0.get("EXPTIME", 0) or 0)
    own = [r for r in scan_library(m.lights) if r["master"] and r["kind"] and r["nx"] == h0.get("NAXIS1") and r["ny"] == h0.get("NAXIS2")]
    for k in ("bias", "flat", "dark"):
        c_ = sorted([r for r in own if r["kind"] == k.upper()], key=lambda r: abs(r["exptime"] - exp0) if k == "dark" else 0)
        if c_ and not m.cfg["calib"].get(k):
            mt[k] = c_[0]
            log(f"  {k:5s}: Master aus dem Messordner: {os.path.basename(c_[0]['path'])}")
    for k in ("bias", "flat", "dark"):                 # explicit master paths in [calib] win
        p = m.cfg["calib"].get(k, "")
        if p:
            r = next((x for x in rows if os.path.normcase(x["path"]) == os.path.normcase(p)), None)
            mt[k] = r or dict(path=p, kind=k.upper(), master=True, instr="", gain=None, offset=None, xbin=1, nx=None, ny=None,
                              filter="", exptime=0.0, ccd_temp=None, date=None, nstack=None)
    from .calib import effective_mode
    want = a.mode or m.cfg["calib"]["mode"]
    eff, notes = effective_mode(want, mt)
    res = dict(library=lib, n_files=len(rows), n_masters=sum(r["master"] for r in rows), mode=want, mode_effektiv=eff,
               gesucht=dict(filter=str(h0.get("FILTER", "")), binning=h0.get("XBINNING"), groesse=f"{h0.get('NAXIS1')}x{h0.get('NAXIS2')}",
                            kamera=str(h0.get("INSTRUME", "")), gain=h0.get("GAIN"), offset=h0.get("OFFSET"), belichtung=exp0),
               warnungen=notes)
    for t in notes:
        log(f"  WARNUNG: {t}. Gesucht: Filter '{res['gesucht']['filter']}', Binning {res['gesucht']['binning']}, "
            f"{res['gesucht']['groesse']}, Kamera {res['gesucht']['kamera']}, Gain {res['gesucht']['gain']}, Offset {res['gesucht']['offset']}; "
            f"Bibliothek {lib}: {res['n_masters']} Master")
    for k, v in mt.items():
        res[k] = None if v is None else {kk: (str(vv) if kk == "date" else vv) for kk, vv in v.items()}
        log(f"  {k:5s}: " + ("-- nicht gefunden" if v is None else
                             f"{v['path']} ({v['date'] and f'{v['date']:%Y-%m-%d}'}, {v['exptime']:g} s, {v['filter']}, {v['ccd_temp']} C)"))
    ct = [float(x["header"].get("CCD-TEMP", np.nan)) for x in hd]
    if mt["dark"] and mt["dark"].get("ccd_temp") is not None and np.nanmax(np.abs(np.array(ct) - float(mt["dark"]["ccd_temp"]))) > 3:
        log(f"  WARNUNG: Dark bei {mt['dark']['ccd_temp']} C, Lights bei {np.nanmin(ct):.1f}..{np.nanmax(ct):.1f} C -> Dark nur skaliert verwendbar")
        if mt["bias"]:
            ks = estimate_dark_scale(m, [x["file"] for x in hd if x["solved"]], mt)
            res["dark_scale"] = ks
            log(f"  Dark-Skalierung (Hot-Pixel): k = {ks['k_night']:.2f} ({ks['k_min']:.2f}..{ks['k_max']:.2f})")
    jdump(res, m.path("calib.json"))
    if a.write:
        from .calib import Calibrator
        from .frames import read_data
        from astropy.io import fits
        cal = Calibrator(res["mode"], mt, res.get("dark_scale", {}).get("k_night", 1.0), m.cfg["calib"].get("crop", [0, 0]))
        out = m.dir("CALIBRATED")
        bar = progress.task("Kalibrieren", len(hd), "Frames")
        for x in hd:
            dst = safety.guard_write(m, os.path.join(out, os.path.basename(x["file"])))
            hh = x["header"].copy(); hh["HISTORY"] = f"transit calibrate mode={res['mode']}"
            for k in ("BZERO", "BSCALE"):
                hh.remove(k, ignore_missing=True)
            fits.writeto(dst, cal(read_data(x["file"])).astype(np.float32), hh, overwrite=True)
            bar.update()
        bar.done()
        log(f"Kalibrierte Frames (float32) -> {out}")


# ------------------------------------------------------------------ cube
def cmd_cube(m, a):
    from .stars import select, load
    from .photometry import build_cube
    from .calib import Calibrator
    from astropy.time import Time
    hd, tm, par, pred, tgt = context(m)
    mode = a.mode or m.cfg["calib"]["mode"]
    if a.new_stars or not os.path.exists(m.path("candidates.csv")):
        sel, info = select(m, hd, float(Time(hd[0]["header"]["DATE-OBS"]).jyear), tgt)
        log(f"Gaia: {info['n_gaia']} Sterne, {info['n_window']} im Helligkeitsfenster, {info['n_ok']} erfuellen alle Kriterien; "
            f"{len(sel) - 1} Kandidaten")
    else:
        sel = load(m)
        log(f"{len(sel) - 1} Kandidaten aus candidates.csv")
    if mode == "raw":
        cal_args = ("raw", {})
    else:
        cj = jload(m, "calib.json")
        k = cj.get("dark_scale", {}).get("k_night", 1.0) if mode == "bfd" else 1.0
        cal_args = (mode, cj, k, m.cfg["calib"].get("crop", [0, 0]))
    cal = Calibrator(*cal_args)
    for t in cal.notes:
        log(f"  WARNUNG: {t}")
    from . import parallel
    w = parallel.n_workers(m, a, "cube_workers")
    log(f"Photometrie ({mode}) ...")
    cube = build_cube(m, hd, sel, tm, cal, log, workers=w, cal_args=cal_args)
    np.savez_compressed(m.path(f"cube_{mode}.npz"), **cube)
    log(f"Cube {cube['flux'].shape} -> cube_{mode}.npz ({cube['runtime_s']:.0f} s)")


# ------------------------------------------------------------------ search + fit helpers
def night_from(m, a):
    from .analysis import Night
    from .ephem import planet_params
    mode = getattr(a, "mode", None) or m.cfg["calib"]["mode"]
    p = m.path(f"cube_{mode}.npz")
    if not os.path.exists(p):
        raise SystemExit(f"cube_{mode}.npz fehlt - zuerst transit cube")
    c = dict(np.load(p))
    from .apertur import add_variable, search_radii
    m.cfg["search"]["radii"] = search_radii(m.cfg, add_variable(c, m.cfg, log))   # fixed / growing / both
    hp = m.path("headers.csv")
    if os.path.exists(hp):                                 # exposure per frame (noise model, fit.weights)
        import csv
        ex = {r["file"]: float(r["EXPTIME"]) for r in csv.DictReader(open(hp, encoding="utf-8")) if r.get("EXPTIME")}
        if all(str(f) in ex for f in c["frame_file"]):
            c["exptime"] = np.array([ex[str(f)] for f in c["frame_file"]])
    inv = jload(m, "inventory.json")
    pred = inv["ephemeris"]
    par = inv["planet"]
    geom = (par["ars"], par["inc"])
    excl = list(m.cfg["search"].get("exclude_frames", []))
    at = m.cfg["search"].get("aij_table", "")
    if at:
        at = at if os.path.isabs(at) else os.path.join(m.root, at)
        keepf = {l.split("\t")[0] for l in open(at).readlines()[1:]}
        excl += [f for f in c["frame_file"] if f not in keepf]
    n = Night(c, m.cfg, pred, geom, excl, log)
    return n, c, pred, par


def cmd_compsearch(m, a):
    n, c, pred, par = night_from(m, a)
    rej = n.prefilter()
    log(f"Frames: {n.info['frames_used']} von {n.info['frames_total']} (Liste {n.info['excluded_list']}, "
        f"Saettigung {n.info['excluded_saturation']}); OOT {n.info['n_oot']} ({n.info['n_oot_pre']} vor / {n.info['n_oot_post']} nach)")
    log(f"Gesaettigte Vergleichssterne entfernt: {n.dropped_saturating}; Vorfilter verworfen: {rej}; Pool {len(n.pool)}")
    fl = n.flip_offsets()
    if fl:
        log(f"Flip-Versatz Ziel (Vorhersage aus {fl['n_stars']} Sternen): {fl['target_pred_ppt']:+.2f} +- {fl['scatter_ppt']:.2f} ppt")
    allc, bests = {}, {}
    radii = m.cfg["search"]["radii"]
    est = max(1, len(n.pool) * max(1, m.cfg["search"]["n_max"] - m.cfg["search"]["n_min"] - 1))   # rough evaluations per radius
    bar = progress.task("Ensemble-Suche", len(radii) * est, "Bewertungen")
    for ri, r in enumerate(radii):
        seen, be, bs = n.greedy(r, tick=lambda k, ri=ri: bar.update(n=ri * est + min(k, est - 1)))
        bar.update(n=(ri + 1) * est)
        progress.debug(f"r={r}: {len(seen)} Ensembles bewertet")
        bests[r] = ([n.names[j] for j in be], bs)
        allc.update({(r, k): v for k, v in seen.items()})
        log(f"  r={r}: bestes Ensemble {bests[r][0]}  OOT-RMS {bs:.3f} ppt")
    bar.done()
    top = sorted(allc.items(), key=lambda kv: kv[1])[:m.cfg["search"]["top"]]
    res = dict(info=n.info, prefilter=n.prefilter_table, flip=fl, greedy={str(r): dict(comps=v[0], oot_rms_ppt=v[1]) for r, v in bests.items()},
               top=[dict(radius=r, comps=[n.names[j] for j in e], score=v, oot_rms_ppt=n.oot_rms(n.ir(r), list(e)),
                         asym=n.asym(list(e), n.ir(r))) for (r, e), v in top])
    jdump(res, m.path("compsearch.json"))
    log(f"Top {len(top)} Kombinationen -> compsearch.json")


def mcmc_step_cost(n, r, ens, pred, reps=5):
    """Seconds per MCMC step (one model evaluation + linear solve), measured on this night's data."""
    from .model import model
    ir = n.ir(r)
    f, pr = n.rel(ir, ens), n.flip_prior(ens, ir)
    t0 = time.time()
    for _ in range(reps):
        mm = model(n.t, pred["Tc"], pred["P"], 0.1, n.geom[0], n.geom[1], *n.u)
        n.lin_solve(f, mm, n.X, pr)
    return (time.time() - t0) / reps


def cmd_fit(m, a):
    from . import parallel
    from .analysis import summarize_chains
    n, c, pred, par = night_from(m, a)
    cs = jload(m, "compsearch.json")
    n.prefilter()
    n.flip_offsets()
    idx = {nm: i for i, nm in enumerate(n.names)}
    best = cs["top"][0]; r = best["radius"]; ens = [idx[s] for s in best["comps"]]
    free_mc = not m.cfg["fit"]["fix_geometry"]
    W = parallel.n_workers(m, a)
    steps = a.mcmc_steps or m.cfg["fit"]["mcmc_steps"]
    k_ch, L = parallel.chain_plan(steps, W, m.cfg["fit"].get("mcmc_chains", 0))
    cost = mcmc_step_cost(n, r, ens, pred)
    mc_s = cost * L * -(-k_ch // W)
    progress.debug(f"MCMC-Schritt ~{cost * 1e3:.0f} ms -> MCMC ~{progress.dur(mc_s)} ({k_ch} Ketten x {L} Schritte)")

    jobs = [(("combo", i), parallel.fit_combo, (t["radius"], [idx[s] for s in t["comps"]])) for i, t in enumerate(cs["top"])]
    for j in ens:
        e2 = [k for k in ens if k != j]
        if len(e2) >= 2:
            jobs.append((("jk", n.names[j]), parallel.fit_one, (r, e2)))
    nopre = n.t > pred["ingress"] + m.cfg["search"]["oot_margin_min"] / 1440
    tests_def = (("alle_fest", None, False), ("alle_frei", None, True), ("ohne_vor_ingress_fest", nopre, False),
                 ("ohne_vor_ingress_frei", nopre, True))
    jobs += [(("test", lab), parallel.fit_one, (r, ens, mk, fr)) for lab, mk, fr in tests_def]
    weight = lambda key: 2 if key[0] == "combo" else 1
    bar = progress.task("Fits Top-Kombinationen", sum(weight(j[0]) for j in jobs), "Fits", then_s=mc_s, then="MCMC")

    def done(key, res):
        bar.update(weight(key))
        if key[0] == "combo":
            t = cs["top"][key[1]]
            progress.debug(f"r={t['radius']} {' '.join(t['comps'])}: O-C fest {(res[0]['Tc'] - pred['Tc']) * 1440:+.1f} min, "
                           f"frei {(res[1]['Tc'] - pred['Tc']) * 1440:+.1f} min")
    log(f"Fits: {len(jobs)} Auftraege, " + (f"{W} Prozesse" if W > 1 else "seriell"))
    chain_jobs = [(("chain", i), parallel.mcmc_chain, (r, ens, free_mc, L, 1 + i, 0.0 if i == 0 else 3.0)) for i in range(k_ch)]
    if W > 1:
        ctr = parallel.counter()
        with parallel.executor(min(W, max(len(jobs), k_ch)), parallel.init_night, (n, ctr)) as ex:
            out = parallel.run_jobs(ex, jobs, on_done=done)
            bar.done()
            log(f"MCMC ({k_ch} Ketten x {L} Schritte = {k_ch * L}) ...")
            bar = progress.task("MCMC", k_ch * L, "Schritte")
            out.update(parallel.run_jobs(ex, chain_jobs, poll=lambda: bar.update(n=ctr.value)))
    else:
        parallel.init_night(n)
        out = {}
        for key, fn, args in jobs:
            out[key] = fn(*args); done(key, out[key])
        bar.done()
        log(f"MCMC ({k_ch} Ketten x {L} Schritte) ...")
        bar = progress.task("MCMC", k_ch * L, "Schritte")
        for i, (key, fn, args) in enumerate(chain_jobs):
            out[key] = n.mcmc_chain(*args[:5], tick=lambda s, acc, i=i: bar.update(n=i * L + s), jitter=args[5])
    bar.done()

    rows = []
    for i, t in enumerate(cs["top"]):
        f1, f2 = out[("combo", i)]
        rows.append(dict(radius=t["radius"], comps=" ".join(t["comps"]), oot_rms_ppt=t["oot_rms_ppt"],
                         Tc_fix=f1["Tc"], Tc_err_fix_min=f1["Tc_err"] * 1440, OC_fix_min=(f1["Tc"] - pred["Tc"]) * 1440,
                         depth_fix_ppt=f1["depth_ppt"], flip_ppt=f1["flip_ppt"], Tc_free=f2["Tc"],
                         OC_free_min=(f2["Tc"] - pred["Tc"]) * 1440, depth_free_ppt=f2["depth_ppt"], ars_free=f2["ars"],
                         inc_free=f2["inc"], fit_rms_ppt=f1["rms_ppt"]))
    with open(m.path("top50.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    pc = lambda k: np.percentile([r_[k] for r_ in rows], [16, 50, 84]).tolist()
    log(f"Beste Kombination: r={r}, {best['comps']}")
    jk = [dict(drop=key[1], OC_min=(f["Tc"] - pred["Tc"]) * 1440, depth_ppt=f["depth_ppt"])
          for key, f in out.items() if key[0] == "jk"]
    jk.sort(key=lambda d: [n.names[j] for j in ens].index(d["drop"]))
    tests = {}
    for lab, _, _ in tests_def:
        f = out[("test", lab)]
        tests[lab] = dict(OC_min=(f["Tc"] - pred["Tc"]) * 1440, Tc_err_min=f["Tc_err"] * 1440, depth_ppt=f["depth_ppt"],
                          ars=f["ars"], inc=f["inc"], rms_ppt=f["rms_ppt"], flip_ppt=f["flip_ppt"])
    mc = summarize_chains([out[("chain", i)] for i in range(k_ch)], free_mc)
    mc["OC_min"] = (mc["Tc"][1] - pred["Tc"]) * 1440
    mc["steps_per_chain"] = L
    res = dict(best=dict(radius=r, comps=best["comps"], gaia=[str(c["star_gaia"][idx[s]]) for s in best["comps"]],
                         oot_rms_ppt=best["oot_rms_ppt"], asym=n.asym(ens, n.ir(r))),
               top_summary=dict(OC_fix_min=pc("OC_fix_min"), OC_free_min=pc("OC_free_min"), Tc_fix=pc("Tc_fix"),
                                Tc_free=pc("Tc_free"), depth_fix_ppt=pc("depth_fix_ppt"), depth_free_ppt=pc("depth_free_ppt")),
               jackknife=jk, tests=tests, mcmc=mc, ephemeris=pred, geometry=dict(ars=par["ars"], inc=par["inc"]),
               flip_target=n.flip_target, info=n.info, workers=W)
    jdump(res, m.path("fit.json"))
    t = mc["Tc"]
    log(f"Tc = {t[1]:.5f} +{(t[2] - t[1]) * 1440:.1f}/-{(t[1] - t[0]) * 1440:.1f} min BJD_TDB, O-C {mc['OC_min']:+.1f} min, "
        f"Tiefe {mc['depth_ppt'][1]:.2f} ppt, beta {mc['beta']:.2f}")
    if mc.get("rhat"):
        rh = mc["rhat_max"]
        log(f"MCMC: {k_ch} Ketten, R-hat " + ", ".join(f"{k} {v:.3f}" for k, v in mc["rhat"].items())
            + ("  ok (< 1.05)" if rh < 1.05 else "  WARNUNG: >= 1.05, mehr Schritte (--mcmc-steps) verwenden"))
    log(f"Top-{len(rows)}: O-C (fest) {res['top_summary']['OC_fix_min'][0]:+.1f}/{res['top_summary']['OC_fix_min'][1]:+.1f}/"
        f"{res['top_summary']['OC_fix_min'][2]:+.1f} min; Jackknife " + ", ".join(f"{d['drop']} {d['OC_min']:+.1f}" for d in jk))


# ------------------------------------------------------------------ export / report
def cmd_export(m, a):
    from .export import export_all
    n, c, pred, par = night_from(m, a)
    n.prefilter(); n.flip_offsets()
    export_all(m, n, c, jload(m, "fit.json"), jload(m, "inventory.json"), log)


def cmd_report(m, a):
    from .report import make_report
    n, c, pred, par = night_from(m, a)
    n.prefilter(); n.flip_offsets()
    make_report(m, n, c, log)


STEPS = ("inventory", "calibrate", "cube", "compsearch", "fit", "export", "report")


def step_outputs(step, mode):
    """Files whose presence marks a step as finished (all must exist)."""
    return dict(inventory=["inventory.json", "headers.csv"], calibrate=["calib.json"], cube=[f"cube_{mode}.npz", "candidates.csv"],
                compsearch=["compsearch.json"], fit=["fit.json", "top50.csv"], export=["exoclock_formular.txt"],
                report=["summary.md", "ergebnisblatt.pdf"])[step]


def step_params(step, a, mode):
    return dict(inventory={}, calibrate=dict(mode=mode), cube=dict(mode=mode), compsearch=dict(mode=mode),
                fit=dict(mode=mode, mcmc_steps=a.mcmc_steps), export=dict(mode=mode), report=dict(mode=mode))[step]


def step_status(m, step, a, mode, prev_mtime):
    """(finished?, reason, mtime).  Finished = outputs exist, not older than the previous step, same parameters/config."""
    outs = [m.path(f) for f in step_outputs(step, mode)]
    missing = [os.path.basename(f) for f in outs if not os.path.exists(f)]
    if missing:
        return False, "fehlt: " + ", ".join(missing), None
    mt = os.path.getmtime(outs[0])          # main product decides the order (candidates.csv may be shared and older)
    if prev_mtime is not None and mt + 1 < prev_mtime:
        return False, "aelter als der vorherige Schritt", mt
    if step == "cube" and a.new_stars:
        return False, "--new-stars", mt
    if step == "calibrate" and a.write:
        return False, "--write", mt
    st = progress.load_state(m).get(step)
    if st:
        want = step_params(step, a, mode)
        if step == "fit" and want.get("mcmc_steps") is None:
            want["mcmc_steps"] = st["params"].get("mcmc_steps")
        if st.get("params") != want:
            return False, f"andere Parameter ({st.get('params')} -> {want})", mt
        if st.get("cfg") != progress.cfg_hash(m.cfg, progress.CFG_DEPS[step]):
            return False, "Einstellungen geaendert ([" + "], [".join(progress.CFG_DEPS[step]) + "])", mt
    return True, "fertig " + time.strftime("%Y-%m-%d %H:%M", time.localtime(mt)) + ("" if st else ", Dateien vorhanden"), mt


def cmd_run(m, a):
    mode = a.mode or m.cfg["calib"]["mode"]
    fns = dict(inventory=cmd_inventory, calibrate=cmd_calibrate, cube=cmd_cube, compsearch=cmd_compsearch, fit=cmd_fit,
               export=cmd_export, report=cmd_report)
    progress.plan(STEPS)
    redo, prev = bool(a.force), None
    redo_from = STEPS.index(a.from_step) if a.from_step else len(STEPS)
    for i, st in enumerate(STEPS):
        if st == "calibrate":                              # frames without WCS: plate-solve first (ASTAP, copies in SOLVED\)
            from .frames import read_headers
            n_un = sum(not x["solved"] for x in read_headers(m))
            if n_un:
                log(f"===== solve =====  ({n_un} Frames ohne WCS)")
                cmd_solve(m, a)
                prev = time.time()
        ok, why, mt = step_status(m, st, a, mode, prev)
        if i >= redo_from and not redo:
            redo, why = True, f"--from {a.from_step}"
        if ok and not redo:
            log(f"===== {st}: uebersprungen ({why})")
            progress.step_skip(st, why)
            prev = mt
            continue
        log(f"===== {st} =====" + ("" if redo else f"  ({why})"))
        redo = True                                    # everything after a re-run step is re-run too
        run_step(m, a, st, fns[st], mode)
        prev = time.time()


def run_step(m, a, st, fn, mode):
    progress.step_begin(st)
    t0 = time.time()
    try:
        fn(m, a)
    except BaseException:
        progress.step_end(st, "fehler")
        raise
    progress.step_end(st)
    progress.mark_done(m, st, step_params(st, a, mode), dict(files=step_outputs(st, mode), seconds=round(time.time() - t0, 1)))


def cmd_status(a):
    import glob
    root = os.path.abspath(a.messordner)
    res = os.path.join(root, "RESULT")
    if not os.path.isdir(res):
        raise SystemExit(f"Kein RESULT-Ordner in {root}")
    now = time.time()
    rows = []
    for d in sorted(glob.glob(os.path.join(res, "*", ""))):
        run = os.path.basename(os.path.dirname(d))
        sp = os.path.join(d, progress.STATUS)
        if os.path.exists(sp):
            try:
                s = json.load(open(sp, encoding="utf-8"))
            except (OSError, ValueError):
                rows.append([run, "?", "status.json unlesbar", "", "", "", ""]); continue
            age = now - s.get("heartbeat_unix", 0)
            alive = progress.pid_alive(s.get("pid"))
            state = s.get("state", "?")
            flag = "-"
            if state == "laeuft":
                if alive is False:
                    flag, state = "JA (Prozess beendet)", "abgebrochen"
                elif age > progress.HANG_S:
                    flag = f"JA (kein Lebenszeichen seit {progress.dur(age)})"
                elif now - s.get("last_progress_unix", now) > progress.STALL_S:
                    flag = f"steht? (kein Fortschritt seit {progress.dur(now - s['last_progress_unix'])})"
                else:
                    flag = "nein"
            step = s.get("step") or s.get("command", "")
            if s.get("n_steps", 1) > 1:
                step = f"{step} ({s['step_no']}/{s['n_steps']})"
            task = s.get("task", "")
            pct = "100%" if state == "fertig" else (f"{s['percent']:.0f}%" if s.get("percent") is not None else "")
            eta = (s.get("eta_local") or "-") if state == "laeuft" else "-"
            rows.append([run, state, f"{s.get('command', '')}: {step}" + (f" / {task}" if task else ""), pct, eta,
                         progress.clock(s.get("heartbeat_unix"), with_date=True), flag])
            if s.get("error"):
                rows.append(["", "", "   Fehler: " + str(s["error"])[:90], "", "", "", ""])
            if a.verbose:
                for x in s.get("steps", []):
                    rows.append(["", "", f"   {x['name']}: {x['state']}" + (f" {progress.dur(x['duration_s'])}" if x.get("duration_s") else ""),
                                 "", "", "", ""])
        else:
            done = [f for f in ("inventory.json", "calib.json", "compsearch.json", "fit.json", "summary.md") if os.path.exists(os.path.join(d, f))]
            if not done and not glob.glob(os.path.join(d, "cube_*.npz")):
                continue
            last = max(os.path.getmtime(os.path.join(d, f)) for f in os.listdir(d))
            rows.append([run, "kein Status", "letzte Datei: " + (done[-1] if done else "cube_*.npz"), "", "-",
                         progress.clock(last, with_date=True), "-"])
    if not rows:
        print("Keine Laeufe gefunden."); return
    head = ["Lauf", "Zustand", "Schritt", "%", "fertig ca.", "letztes Lebenszeichen", "haengt?"]
    w = [max(len(str(r[i])) for r in rows + [head]) for i in range(len(head))]
    for r in [head, ["-" * x for x in w]] + rows:
        print("  ".join(str(c).ljust(x) for c, x in zip(r, w)).rstrip())


def summary(m, a, t0, ok, err):
    """Final console block: duration, steps, key result, new files."""
    lines = ["", "=" * 70, f"transit {a.cmd}: {'FERTIG' if ok else 'FEHLER'} nach {progress.dur(time.time() - t0)}"
             f"  ({progress.clock(time.time())})"]
    for s in progress.steps():
        if s["state"] != "offen":
            lines.append(f"  {s['name']:11s} {s['state']:14s} " + (progress.dur(s["duration_s"]) if s.get("duration_s") else s.get("note", "")))
    res = None
    fp = os.path.join(m.out, "fit.json")
    if ok and os.path.exists(fp) and os.path.getmtime(fp) >= t0 - 1:
        try:
            mc = json.load(open(fp, encoding="utf-8"))["mcmc"]; t = mc["Tc"]
            res = (f"Tc {t[1]:.5f} +{(t[2] - t[1]) * 1440:.1f}/-{(t[1] - t[0]) * 1440:.1f} min BJD_TDB, O-C {mc['OC_min']:+.1f} min, "
                   f"Tiefe {mc['depth_ppt'][1]:.2f} ppt")
            lines.append("  Ergebnis: " + res)
        except (KeyError, ValueError, TypeError):
            pass
    if not ok:
        lines.append(f"  Fehler: {err}")
    skip = (progress.STATUS, progress.STATE, progress.RUNLOG, "transit.log")
    new = sorted(f for f in os.listdir(m.out) if f not in skip and not f.endswith(".tmp")
                 and os.path.getmtime(os.path.join(m.out, f)) >= t0 - 1)
    if new:
        lines.append(f"  Geschrieben in {m.out}:")
        lines += [f"    {f}" for f in new]
    lines.append("=" * 70)
    progress.clear_line()
    print("\n".join(lines), flush=True)
    progress.runlog("\n".join(lines[1:]))
    return res


def cmd_logbuch(a):
    from .ergebnisblatt import LOGBOOK, VALID, logbook_backfill, logbook_read, logbook_set_valid
    root = os.path.abspath(a.messordner)
    if a.archiv:                                           # measurement moved by hand: record where it is now
        from .ergebnisblatt import logbook_set_archive
        tgt = os.path.abspath(a.archiv)
        if not os.path.isdir(os.path.join(tgt, "RESULT")):
            raise SystemExit(f"{tgt}\\RESULT nicht gefunden")
        print(f"Archivpfad {tgt} bei {logbook_set_archive(root, tgt)} Lauf/Laeufen eingetragen")
    if a.nachtragen:
        logbook_backfill(root)
    if a.gueltig:
        me = logbook_set_valid(root, a.gueltig)
        print(f"{me['planet']} {me['nacht']}: gueltig ist jetzt {a.gueltig}, alle anderen Laeufe dieser Nacht sind Varianten.")
        from .ergebnisblatt import refresh_packages
        refresh_packages(me["planet"], me["nacht"], print)
        print("Upload-Pakete angepasst (Varianten: NICHT_HOCHLADEN_...). Die O-C-Grafik der Ergebnisblaetter aendert sich "
              "erst beim naechsten transit report.")
    rows = [r for r in logbook_read() if os.path.normcase(root) in (os.path.normcase(r["messordner"]), os.path.normcase(r.get("archiv") or "-"))]
    if not rows:
        print(f"Keine Eintraege fuer {root} in {LOGBOOK}"); return
    print(f"{'Planet':10s} {'Nacht':10s} {'Status':9s} {'Lauf':34s} {'O-C min':>14s} {'Tiefe ppt':>14s} {'Rp/R*':>8s}")
    for r in rows:
        print(f"{r['planet']:10s} {r['nacht']:10s} {r['status']:9s} {r['lauf']:34s} {float(r['oc_min']):+7.2f} +-{float(r['oc_err_min']):5.2f} "
              f"{float(r['tiefe_ppt']):7.2f} +-{float(r['tiefe_err_ppt']):5.2f} {float(r['rp_rs']):8.4f}"
              + (f"  Archiv: {r['archiv']}" if r.get("archiv") else ""))
    print(f"(*) {VALID} = die Messung dieser Nacht fuer O-C/Upload; aendern mit: transit logbuch <Messung> --gueltig <lauf>")


def cmd_hilfe(a):
    from .hilfe import show
    show(a.thema)


def main(argv=None):
    p = argparse.ArgumentParser(prog="transit", description="Transit-Photometrie: vom Light-Ordner bis zur ExoClock-Datei. "
                                "Deutsche Hilfe: transit hilfe [thema]")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, helptext, extra=None):
        s = sub.add_parser(name, help=helptext, description=helptext)
        s.add_argument("messordner", help="Ordner der Messung (enthaelt LIGHTS/ oder _work/)")
        s.add_argument("--nas", action="store_true", help="nicht gefunden: ohne Rueckfrage am NAS suchen ([paths] archiv_wurzel)")
        s.add_argument("--out", default="pipeline", help="Unterordner in RESULT fuer die Ergebnisse (Standard: pipeline)")
        s.add_argument("--verbose", "-v", action="store_true", help="Debug-Ausgaben (Konsole und run.log)")
        s.add_argument("--workers", "-j", type=int, help="parallele Prozesse (Standard [run] workers, 0 = Kerne - 2; 1 = seriell)")
        s.add_argument("--toast", action="store_true", help="Windows-Benachrichtigung am Ende (oder [progress] toast = true)")
        if extra:
            extra(s)
        s.set_defaults(func=fn)
    mode = lambda s: s.add_argument("--mode", choices=["raw", "f", "bf", "bfd"], help="Kalibrierung (Standard aus config: calib.mode)")
    add("inventory", cmd_inventory, "Header lesen, Pruefsummen speichern, Ephemeride, Planungs-Checks",
        lambda s: s.add_argument("--full", action="store_true", help="volle SHA-256-Pruefsummen (langsam)"))
    add("solve", cmd_solve, "Frames ohne WCS mit ASTAP loesen (Kopien in SOLVED/)",
        lambda s: (s.add_argument("--radius", type=float, default=5, help="Suchradius in Grad (Standard 5)"),
                   s.add_argument("--keep-failed", action="store_true", help="ungeloeste Kopien behalten")))
    add("calibrate", cmd_calibrate, "Passende Master suchen, Dark-Skalierung schaetzen (optional kalibrierte Frames schreiben)",
        lambda s: (mode(s), s.add_argument("--write", action="store_true", help="kalibrierte FITS nach CALIBRATED/ schreiben")))
    add("cube", cmd_cube, "Vergleichsstern-Kandidaten (Gaia) + Photometrie-Cube",
        lambda s: (mode(s), s.add_argument("--new-stars", action="store_true", help="Kandidaten neu aus Gaia bestimmen")))
    add("compsearch", cmd_compsearch, "Vorfilter, Flip-Versatz, gierige Ensemble-Suche ueber die Radien", mode)
    add("fit", cmd_fit, "Transit-Fits der Top-Kombinationen, Jackknife, Tests, MCMC",
        lambda s: (mode(s), s.add_argument("--mcmc-steps", type=int, help="Schritte der MCMC")))
    add("export", cmd_export, "ExoClock-Datei, Formularwerte, AIJ-radec, detrendete Lichtkurve", mode)
    add("report", cmd_report, "Plots und summary.md", mode)
    add("run", cmd_run, "Alles nacheinander: inventory, calibrate, cube, compsearch, fit, export, report",
        lambda s: (mode(s), s.add_argument("--full", action="store_true"), s.add_argument("--write", action="store_true"),
                   s.add_argument("--new-stars", action="store_true"), s.add_argument("--mcmc-steps", type=int),
                   s.add_argument("--force", action="store_true", help="alle Schritte neu rechnen, auch fertige"),
                   s.add_argument("--from", dest="from_step", choices=STEPS, help="ab diesem Schritt neu rechnen")))
    st = sub.add_parser("status", help="Fortschritt aller Laeufe einer Messung (Schritt, %%, Ende, haengt?)",
                        description="Fortschritt aller Laeufe einer Messung (RESULT\\*\\status.json): Schritt, Prozent, "
                                    "voraussichtliches Ende, haengt?")
    st.add_argument("messordner", help="Ordner der Messung")
    st.add_argument("--nas", action="store_true", help="nicht gefunden: ohne Rueckfrage am NAS suchen ([paths] archiv_wurzel)")
    st.add_argument("--verbose", "-v", action="store_true", help="auch die einzelnen Schritte zeigen")
    lg = sub.add_parser("logbuch", help="Logbuch-Eintraege einer Messung zeigen; --gueltig LAUF waehlt die gueltige Messung der Nacht",
                        description="Logbuch (_pipeline\\logbuch.csv): pro Planet und Nacht ist genau ein Lauf gueltig, die anderen sind Varianten.")
    lg.add_argument("messordner", help="Ordner der Messung")
    lg.add_argument("--nas", action="store_true", help="nicht gefunden: ohne Rueckfrage am NAS suchen ([paths] archiv_wurzel)")
    lg.add_argument("--gueltig", metavar="LAUF", help="diesen Lauf (Unterordner in RESULT) als gueltige Messung der Nacht markieren")
    lg.add_argument("--archiv", metavar="PFAD", help="Messordner wurde von Hand verschoben: neuen Ort im Logbuch eintragen")
    lg.add_argument("--nachtragen", action="store_true", help="neuere Spalten (Fehler, Drift, Ephemeride, Upload-Datei) aus fit.json fuellen")
    gu = sub.add_parser("gui", help="Bedienoberflaeche im Browser (lokal, http://127.0.0.1:8765)",
                        description="Startet eine lokale Bedienoberflaeche im Browser. Sie ruft die normalen transit-Befehle auf.")
    gu.add_argument("--port", type=int, default=8765)
    gu.add_argument("--kein-browser", dest="kein_browser", action="store_true", help="Browser nicht automatisch oeffnen")
    ko = sub.add_parser("kommentar", help="Englischer Kommentar fuer den ExoClock-Upload (Ausgabe + Zwischenablage)",
                        description="Erzeugt den Kommentar fuer das ExoClock-Formular aus den Daten des Laufs und kopiert ihn in die Zwischenablage.")
    ko.add_argument("messordner", help="Ordner der Messung")
    ko.add_argument("--nas", action="store_true", help="nicht gefunden: ohne Rueckfrage am NAS suchen")
    ko.add_argument("--lauf", help="Unterordner in RESULT (Standard: gueltiger Lauf)")
    aj = sub.add_parser("aij", help="AstroImageJ-Dateien (Messtabelle + Multi-Plot-Konfiguration) erzeugen / in AIJ oeffnen",
                        description="Schreibt RESULT\\<lauf>\\aij\\ (Messtabelle im AIJ-Format, gleichnamige .plotcfg, Makro, LIESMICH). "
                                    "Ohne --lauf: der gueltige Lauf aus dem Logbuch.")
    aj.add_argument("messordner", help="Ordner der Messung")
    aj.add_argument("--nas", action="store_true", help="nicht gefunden: ohne Rueckfrage am NAS suchen ([paths] archiv_wurzel)")
    aj.add_argument("--lauf", help="Unterordner in RESULT (Standard: gueltiger Lauf)")
    aj.add_argument("--neu", action="store_true", help="Dateien neu erzeugen, auch wenn sie schon da sind")
    aj.add_argument("--oeffnen", action="store_true", help="AstroImageJ starten und Tabelle + Konfiguration laden")
    ar = sub.add_parser("archiv", help="Messordner aufs NAS kopieren, Pruefsummen pruefen, im Logbuch eintragen (loeschen nur mit --loeschen)",
                        description="Kopiert den ganzen Messordner nach <ziel>\\<Ordnername>, prueft SHA-256 jeder Datei am Ziel, "
                                    "traegt den Archivpfad im Logbuch ein. Das Original bleibt, ausser --loeschen und alle Pruefsummen stimmen.")
    ar.add_argument("messordner", help="Ordner der Messung")
    ar.add_argument("--nas", action="store_true", help="nicht gefunden: ohne Rueckfrage am NAS suchen ([paths] archiv_wurzel)")
    ar.add_argument("--ziel", required=True, help="Archiv-Ordner, z. B. \\\\NAS\\astro\\messungen (der Messordner kommt als Unterordner hinein)")
    ar.add_argument("--probe", action="store_true", help="Trockenlauf: nur anzeigen, nichts kopieren oder aendern")
    ar.add_argument("--loeschen", action="store_true", help="nach erfolgreicher Pruefung das lokale Original loeschen")
    h = sub.add_parser("hilfe", help="Deutsche Hilfe zu einem Thema (ohne Thema: Themenliste)")
    h.add_argument("thema", nargs="?", default="")
    h.set_defaults(func=None)
    a = p.parse_args(argv)
    if a.cmd == "hilfe":
        return cmd_hilfe(a)
    if getattr(a, "messordner", None) and not (a.cmd == "logbuch" and a.archiv):   # --archiv: old place may be gone
        from .finden import resolve
        a.messordner = resolve(a.messordner, a.nas)
    if a.cmd == "status":
        return cmd_status(a)
    if a.cmd == "logbuch":
        return cmd_logbuch(a)
    if a.cmd == "kommentar":
        from .kommentar import cmd_kommentar
        return cmd_kommentar(a)
    if a.cmd == "gui":
        from .gui import cmd_gui
        return cmd_gui(a)
    if a.cmd == "aij":
        from .aij import cmd_aij
        return cmd_aij(a)
    if a.cmd == "archiv":
        from .archiv import cmd_archiv
        return cmd_archiv(a)
    for k, v in (("mode", None), ("full", False), ("write", False), ("new_stars", False), ("mcmc_steps", None), ("radius", 5),
                 ("keep_failed", False), ("force", False), ("from_step", None), ("workers", None)):
        if not hasattr(a, k):
            setattr(a, k, v)
    m = Measurement(a.messordner, a.out)
    os.makedirs(m.out, exist_ok=True)
    t0 = time.time()
    progress.start(m, a.cmd, a.verbose)
    ok, err = False, None
    try:
        if a.cmd != "inventory":
            log(f"Light-Pruefsummen vorher: {safety.verify(m, 'vorher')}")
        if a.cmd == "run":
            a.func(m, a)
        else:
            progress.plan([a.cmd])
            if a.cmd in STEPS:
                run_step(m, a, a.cmd, a.func, a.mode or m.cfg["calib"]["mode"])
            else:
                progress.step_begin(a.cmd); a.func(m, a); progress.step_end(a.cmd)
        ok = True
    except KeyboardInterrupt:
        err = "abgebrochen (Strg+C)"
        raise
    except BaseException as e:
        err = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
        raise
    finally:
        try:
            log(f"Light-Pruefsummen nachher: {safety.verify(m, 'nachher')}  ({time.time() - t0:.0f} s)")
        except safety.ReadOnlyViolation as e:
            ok, err = False, str(e)
            raise
        finally:
            with open(m.path("transit.log"), "a", encoding="utf-8") as fh:
                fh.write(f"\n### {time.strftime('%Y-%m-%d %H:%M:%S')} transit {' '.join(sys.argv[1:])}\n" + "\n".join(LOG) + "\n")
            res = summary(m, a, t0, ok, err)
            progress.finish(ok, err, res)
            if a.toast or m.cfg.get("progress", {}).get("toast", False):
                progress.toast(f"transit {a.cmd} {'fertig' if ok else 'FEHLER'}: {os.path.basename(m.root)}",
                               (res or err or f"{a.out}: {progress.dur(time.time() - t0)}")[:200])


if __name__ == "__main__":
    main()
