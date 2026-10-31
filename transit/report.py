"""Plots and summary.md for one night."""
import json
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .analysis import linearity
from .model import model


def outlier_lines(m):
    p = m.path("ausreisser.json")
    if not os.path.exists(p):
        return []
    d = json.load(open(p, encoding="utf-8"))
    fr = d.get("frames", [])
    head = f"- Ausreisser entfernt (> {d.get('sigma', 0):g} sigma vom Transit-Fit): {len(fr)} Frames"
    return [head] + [f"  - {x['frame']}  ({(x['bjd_tdb'] % 1) * 24:.2f} h, {x['resid_ppt']:+.1f} ppt, {x['sigma']:+.1f} sigma)" for x in fr]


def make_report(m, n, c, log):
    fr = json.load(open(m.path("fit.json"), encoding="utf-8"))
    inv = json.load(open(m.path("inventory.json"), encoding="utf-8"))
    cs = json.load(open(m.path("compsearch.json"), encoding="utf-8"))
    pred = fr["ephemeris"]; mc = fr["mcmc"]; best = fr["best"]
    idx = {nm: i for i, nm in enumerate(n.names)}
    ens = [idx[s] for s in best["comps"]]
    fb = n.fit(best["radius"], ens)
    # light curve
    off = float(np.floor(fb["t"].min()))
    h = (fb["t"] - off) * 24
    det = fb["f"] / fb["base"]
    fig, ax = plt.subplots(2, 1, figsize=(10, 7), sharex=True, gridspec_kw=dict(height_ratios=[3, 1]))
    ax[0].plot(h, det, ".", color="0.55", ms=5, label=f"{n.r_text(best['radius'])}, {' '.join(best['comps'])}")
    k = len(h) // 5 * 5
    ax[0].plot(h[:k].reshape(-1, 5).mean(1), det[:k].reshape(-1, 5).mean(1), "o", color="C0", ms=5, label="5er-Mittel")
    tm = np.linspace(fb["t"].min(), fb["t"].max(), 1500)
    g = fr["geometry"]
    ax[0].plot((tm - off) * 24, model(tm, mc["Tc"][1], pred["P"], np.sqrt(mc["depth_ppt"][1] / 1e3), g["ars"], g["inc"], *n.u),
               "C3", label=f"MCMC Tc={mc['Tc'][1]:.5f}, Tiefe {mc['depth_ppt'][1]:.2f} ppt")
    for v, ls in ((pred["ingress"], "--"), (pred["Tc"], ":"), (pred["egress"], "--")):
        for a in ax:
            a.axvline((v - off) * 24, color="k", ls=ls, lw=.7)
    if n.east.min() != n.east.max():
        tf = (c["bjd_tdb"][c["east"] != c["east"][0]].min() - off) * 24
        for a in ax:
            a.axvline(tf, color="C2", lw=1)
    ax[0].legend(fontsize=8); ax[0].set_ylabel("rel. Fluss (detrendet)")
    ax[0].set_title(f"{inv['planet']['name']}: O-C {mc['OC_min']:+.1f} min (+{(mc['Tc'][2] - mc['Tc'][1]) * 1440:.0f}/-{(mc['Tc'][1] - mc['Tc'][0]) * 1440:.0f})")
    ax[1].plot(h, fb["res"] * 1e3, ".", color="0.4", ms=4); ax[1].axhline(0, color="C3")
    ax[1].set_xlabel(f"BJD_TDB - {off:.0f} [h]"); ax[1].set_ylabel("Resid. [ppt]")
    fig.tight_layout(); fig.savefig(m.path("lightcurve.png"), dpi=120); plt.close(fig)
    # Tc histogram
    import csv
    rows = list(csv.DictReader(open(m.path("top50.csv"))))
    fig, a = plt.subplots(figsize=(7, 4))
    b = np.arange(-60, 61, 3)
    a.hist([float(r["OC_fix_min"]) for r in rows], b, alpha=.6, label="a/R*, i fest")
    a.hist([float(r["OC_free_min"]) for r in rows], b, alpha=.6, label="Geometrie frei")
    a.axvline(0, color="k"); a.set_xlabel("O-C [min]"); a.set_ylabel("Anzahl"); a.legend()
    fig.tight_layout(); fig.savefig(m.path("tc_hist.png"), dpi=120); plt.close(fig)
    # linearity
    lin = linearity(c, n.keep, n.pool, m.cfg)
    if lin:
        fig, a = plt.subplots(figsize=(7, 4))
        a.plot(lin["points"][:, 0] / 1000, lin["points"][:, 1], ".", ms=3, alpha=.4)
        mids = [float(t["bin"].split("-")[0]) + 2.5 for t in lin["table"]]
        a.errorbar(mids, [t["median_ppt"] for t in lin["table"]], [t["sem_ppt"] for t in lin["table"]], fmt="ks-")
        a.axhspan(-2, 2, color="0.85", zorder=0); a.set_ylim(-25, 25)
        a.axvline(m.cfg["camera"]["saturation_adu"] / 1000, color="C3", ls="--")
        a.set_xlabel("Peak [kADU roh]"); a.set_ylabel("Residuum [ppt]"); a.set_title("Linearitaet (gutes Seeing)")
        fig.tight_layout(); fig.savefig(m.path("linearity.png"), dpi=120); plt.close(fig)
    # flip
    fl = cs.get("flip")
    if fl:
        fig, a = plt.subplots(figsize=(7, 4))
        a.errorbar([s["x"] for s in fl["stars"]], [s["d_ppt"] for s in fl["stars"]], [s["err_ppt"] for s in fl["stars"]], fmt="o")
        a.axhline(0, color="k", lw=.6); a.axvline(np.nanmedian(c["x"][:, 0]), color="C3", ls="--")
        a.set_xlabel("x [px]"); a.set_ylabel("Flip-Versatz Ost-West [ppt]")
        a.set_title(f"Ziel: {fl['target_pred_ppt']:+.1f} +- {fl['scatter_ppt']:.1f} ppt")
        fig.tight_layout(); fig.savefig(m.path("flip_offset.png"), dpi=120); plt.close(fig)
    # FWHM per frame and the aperture radius of the best combination
    fig, a = plt.subplots(figsize=(10, 3.2))
    hh = (c["bjd_tdb"][n.sel] - off) * 24
    fwf = c["fwhm_frame"][n.sel] if "fwhm_frame" in c else np.nanmedian(c["fwhm_star"][n.sel][:, 1:], axis=1)
    a.plot(hh, np.nanmedian(c["fwhm_star"][n.sel][:, 1:], axis=1), ".", color="0.6", ms=3, label="FWHM Vergleichssterne (Median)")
    a.plot(hh, fwf, "-", color="C0", lw=1.2, label="geglaettet")
    a.set_xlabel(f"BJD_TDB - {off:.0f} [h]"); a.set_ylabel("FWHM [px]")
    a2 = a.twinx()
    vap = c.get("vap", {}).get(best["radius"])
    a2.plot(hh, vap["r"][n.sel] if vap else np.full(len(hh), float(best["radius"])), "-", color="C3", lw=1.2)
    a2.set_ylabel("Apertur [px]", color="C3")
    a.set_title(f"FWHM pro Bild (Vergleichssterne) und Apertur des besten Ensembles (rot): {n.r_text(best['radius'])}", fontsize=9)
    a.legend(fontsize=8, loc="upper left")
    fig.tight_layout(); fig.savefig(m.path("fwhm.png"), dpi=120); plt.close(fig)
    ts = fr["top_summary"]
    md = [f"# {inv['planet']['name']} - Nacht {inv['date_first'][:10]}", "",
          f"Erzeugt mit `transit` aus `{m.lights}`. Lights unveraendert (Pruefsummen vor/nach jedem Schritt).", "",
          "## Ergebnis", "",
          f"- **Tc = {mc['Tc'][1]:.5f} BJD_TDB** (+{(mc['Tc'][2] - mc['Tc'][1]) * 1440:.1f} / -{(mc['Tc'][1] - mc['Tc'][0]) * 1440:.1f} min, MCMC, "
          f"{'a/R*, i fest' if m.cfg['fit']['fix_geometry'] else 'Geometrie frei'}, beta {mc['beta']:.2f})",
          f"- Vorhersage {pred['Tc']:.5f} +- {pred['Tc_err']:.5f} ({pred['source']}), **O-C {mc['OC_min']:+.1f} min**",
          f"- Tiefe {mc['depth_ppt'][1]:.2f} ppt ({mc['depth_ppt'][0]:.2f}..{mc['depth_ppt'][2]:.2f})",
          f"- Streuung sigma (Residuen aller Punkte, wie ExoClock): {np.std(fb['f'] - fb['model'] * fb['base']) * 1e3:.2f} ppt",
          f"- Beste Kombination: {n.r_text(best['radius'])}, {', '.join(best['comps'])}, OOT-RMS {best['oot_rms_ppt']:.2f} ppt",
          f"- Top-{len(rows)} O-C (fest) 16/50/84 %: {ts['OC_fix_min'][0]:+.1f} / {ts['OC_fix_min'][1]:+.1f} / {ts['OC_fix_min'][2]:+.1f} min; "
          f"frei: {ts['OC_free_min'][0]:+.1f} / {ts['OC_free_min'][1]:+.1f} / {ts['OC_free_min'][2]:+.1f} min",
          "- Jackknife: " + ", ".join(f"ohne {d['drop']} {d['OC_min']:+.1f} min" for d in fr["jackknife"]),
          "- Tests: " + ", ".join(f"{k} {v['OC_min']:+.1f} min" for k, v in fr["tests"].items()), "",
          "## Daten", "",
          f"- Frames: {fr['info']['frames_used']} von {fr['info']['frames_total']} (ausgeschlossen: Liste {fr['info']['excluded_list']}, "
          f"Saettigung {fr['info']['excluded_saturation']}); OOT {fr['info']['n_oot']} ({fr['info']['n_oot_pre']} vor, {fr['info']['n_oot_post']} nach)",
          f"- Flip-Versatz Ziel (Prior): {fr['flip_target'][0] * 1e3:+.2f} +- {fr['flip_target'][1] * 1e3:.2f} ppt"] + outlier_lines(m) + ["",
          "## Warnungen", ""] + [f"- [{x['level']}] {x['text']}" + (f" -> {x['fix']}" if x.get("fix") else "") for x in inv["checks"]]
    if lin:
        md += ["", "## Linearitaet (helle Vergleichssterne vs. schwaches Ensemble, gutes Seeing)", "",
               "| Peak | n | Median [ppt] | Fehler |", "|---|---|---|---|"] + [
            f"| {t['bin']} | {t['n']} | {t['median_ppt']:+.2f} | {t['sem_ppt']:.2f} |" for t in lin["table"]]
    md += ["", "Plots: lightcurve.png, tc_hist.png, linearity.png, flip_offset.png. Daten: fit.json, top50.csv, compsearch.json."]
    md += ["", "Ergebnisblatt: ergebnisblatt.png / .pdf / .html (auch in exoclock_paket\\)."]
    with open(m.path("summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    log("Bericht: summary.md, lightcurve.png, tc_hist.png, linearity.png, flip_offset.png")
    from .ergebnisblatt import make_sheet
    make_sheet(m, n, c, log)
