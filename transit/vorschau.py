"""Quick preview for a hand-made choice of comparison stars (GUI, tab Vergleichssterne).

transit vorschau <Messordner> --out <lauf> --sterne G03,G08,G12 [--radius 14]

One least-squares transit fit (fixed geometry, no MCMC) on the photometry cube of the run, for the chosen stars and,
for comparison, for the ensemble of the run.  Writes RESULT\\<lauf>\\vorschau.png and prints one line
"VORSCHAU_JSON {...}".  Changes nothing else in the run (no status.json, no logbook).
"""
import glob
import json
import os
import types

import numpy as np

MARK = "VORSCHAU_JSON "


def _mode(out):
    try:
        mo = json.load(open(os.path.join(out, "calib.json"), encoding="utf-8")).get("mode")
        if mo and os.path.exists(os.path.join(out, f"cube_{mo}.npz")):
            return mo
    except Exception:
        pass
    cubes = sorted(glob.glob(os.path.join(out, "cube_*.npz")))
    if not cubes:
        raise SystemExit("kein Photometrie-Cube in diesem Lauf - Vorschau nicht moeglich")
    return os.path.basename(cubes[0])[5:-4]


def kennzahlen(n, r, ens, pred, rp_lit):
    from .analysis import beta_factor
    f = n.fit(r, ens)
    z = (f["rp"] - rp_lit) / f["rp_err"] if rp_lit and f["rp_err"] else None
    return dict(sterne=[n.names[j] for j in ens], radius=r, oc_min=(f["Tc"] - pred["Tc"]) * 1440, oc_err_min=f["Tc_err"] * 1440,
                rp=f["rp"], rp_err=f["rp_err"], rp_lit=rp_lit, rp_dev_sigma=z, tiefe_ppt=f["depth_ppt"],
                oot_rms_ppt=n.oot_rms(n.ir(r), list(ens)), beta=beta_factor(f["res"])), f


def plot(path, pred, fits, labels):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(8, 3.6), dpi=110)
    off = 0.0
    for (f, lab, col) in zip(fits, labels, ("#9aa3ad", "#1f5fbf")):
        t = (f["t"] - pred["Tc"]) * 24
        y = f["f"] / f["base"] - off
        ax.plot(t, y, ".", ms=2.5, color=col, alpha=0.35)
        nb = max(1, len(t) // 40)
        k = len(t) // nb * nb
        if k:
            ax.plot(t[:k].reshape(-1, nb).mean(1), y[:k].reshape(-1, nb).mean(1), "o", ms=4, color=col, label=lab)
        o = np.argsort(t)
        ax.plot(t[o], f["model"][o] - off, "-", color="#d0453a", lw=1.2)
        off += 0.02
    for x in ((pred["ingress"] - pred["Tc"]) * 24, 0, (pred["egress"] - pred["Tc"]) * 24):
        ax.axvline(x, color="#888", lw=0.8, ls=":" if x else "--")
    ax.set_xlabel("Stunden zur vorhergesagten Mitte")
    ax.set_ylabel("rel. Fluss (versetzt)")
    ax.legend(loc="lower left", fontsize=8, frameon=False)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def cmd_vorschau(a):
    from . import cli
    from .config import Measurement
    cli.log = lambda *x, **k: None                        # quiet: only the JSON line goes to stdout
    m = Measurement(a.messordner, a.out)
    out = m.out
    fr = json.load(open(os.path.join(out, "fit.json"), encoding="utf-8")) if os.path.exists(os.path.join(out, "fit.json")) else {}
    want = [s.strip() for s in (a.sterne or "").split(",") if s.strip()]
    if not want:
        raise SystemExit("keine Sterne gewaehlt")
    n, c, pred, par = cli.night_from(m, types.SimpleNamespace(mode=_mode(out)), outliers=True)
    n.prefilter()
    n.flip_offsets()
    idx = {nm: i for i, nm in enumerate(n.names)}
    miss = [s for s in want if s not in idx]
    if miss:
        raise SystemExit(f"nicht im Cube: {', '.join(miss)}")
    best = fr.get("best") or {}
    r = a.radius or best.get("radius") or m.cfg["search"]["radii"][len(m.cfg["search"]["radii"]) // 2]
    rp_lit = par.get("rp")
    neu, fn = kennzahlen(n, r, [idx[s] for s in want], pred, rp_lit)
    res = dict(neu=neu, radius=r)
    fits, labels = [fn], ["Auswahl"]
    if best.get("comps") and all(s in idx for s in best["comps"]):
        ref, fref = kennzahlen(n, best.get("radius", r), [idx[s] for s in best["comps"]], pred, rp_lit)
        ref["mcmc_oc_min"] = (fr.get("mcmc") or {}).get("OC_min")
        res["lauf"] = ref
        fits, labels = [fref, fn], ["Lauf", "Auswahl"]
    try:
        plot(os.path.join(out, "vorschau.png"), pred, fits, labels)
        res["bild"] = "vorschau.png"
    except Exception as e:                                 # the numbers matter more than the picture
        res["bild_fehler"] = str(e)
    print(MARK + json.dumps(res, default=float), flush=True)
