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


def plot_comp_lcs(m, n, pred, ensemble=(), log=None, name="vergleichssterne_lc.png"):
    """HOPS-style check of the comparison stars: one panel per candidate, its flux against the sum of the other
    candidates, detrended (airmass, flip), all on the same scale.  Red = left out (variable/noisy), blue = in the
    ensemble of the best combination, black = usable.  Needs n.prefilter() first (n.comp_lc)."""
    cl = getattr(n, "comp_lc", None)
    if not cl or not len(cl["stars"]):
        return None
    st, lc, t = cl["stars"], cl["lc"] * 1e3, cl["t"]
    pre = {p["name"]: p for p in getattr(n, "prefilter_table", [])}
    off = float(np.floor(t.min()))
    h = (t - off) * 24
    nb = np.floor((t - t.min()) / (cl["bin_min"] / 1440)).astype(int)
    ub = [b for b in np.unique(nb) if (nb == b).sum() >= 3]
    hb = np.array([h[nb == b].mean() for b in ub])
    med = float(np.nanmedian([d["rms_ppt"] for d in st]))
    lim = max(4 * med, 2.0)
    N = len(st); nc = 4 if N > 6 else min(N, 3); nr = -(-N // nc)
    fig, axs = plt.subplots(nr, nc, figsize=(3.6 * nc, 2.3 * nr + 0.9), sharex=True, sharey=True, squeeze=False)
    for k, (d, y) in enumerate(zip(st, lc)):
        a = axs[k // nc][k % nc]
        p = pre.get(d["name"], {})
        rej, ens = bool(p.get("rejected")), d["name"] in ensemble
        col = "C3" if rej else "C0" if ens else "0.15"
        a.plot(h, np.clip(y, -lim * 0.98, lim * 0.98), ".", color="0.65", ms=2)
        a.plot(hb, [y[nb == b].mean() for b in ub], "o-", color=col, ms=3, lw=1)
        if pred:
            a.axvspan((pred["ingress"] - off) * 24, (pred["egress"] - off) * 24, color="0.92", zorder=0)
        a.axhline(0, color="0.5", lw=.6)
        a.set_ylim(-lim, lim)
        tag = "VARIABEL" if p.get("variabel") else "verworfen" if rej else "Ensemble" if ens else ""
        a.set_title(f"{d['name']}{'  ' + tag if tag else ''}\nRMS {d['rms_ppt']:.1f} | {cl['bin_min']:.0f}-min {d['bin_ppt']:.2f} ppt"
                    f" | Ruhe {d['ruhe']:.1f} | beta {d['beta']:.1f}", fontsize=7.5, color=col)
        for sp in a.spines.values():
            sp.set_edgecolor(col); sp.set_linewidth(1.6 if (rej or ens) else .8)
    for k in range(N, nr * nc):
        axs[k // nc][k % nc].axis("off")
    for a in axs[-1]:
        a.set_xlabel(f"BJD_TDB - {off:.0f} [h]", fontsize=8)
    for row in axs:
        row[0].set_ylabel("ppt", fontsize=8)
    fig.suptitle(f"Vergleichssterne einzeln: Stern / Summe der uebrigen, Airmass/Flip detrendet ({n.r_text(cl['radius'])}). "
                 f"Grau = Transitfenster. Ruhe = Streuung der {cl['bin_min']:.0f}-min-Mittel / Median aller; "
                 f"VARIABEL ab Ruhe > {cl['sigma']:g} und beta > {cl['beta']:g}", fontsize=8.5)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(m.path(name), dpi=110); plt.close(fig)
    if log:
        log(f"Vergleichssterne einzeln: {name}")
    return name


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
    try:
        plot_comp_lcs(m, n, pred, best["comps"])
    except Exception as e:
        log(f"  [WARN] vergleichssterne_lc.png nicht erstellt: {e}")
    try:                                    # prepare the GUI's comparison-star table: Gaia details of ALL candidates now
        import csv as _csv
        from .feld import gaia_details
        gaia_details(m, [r["source_id"] for r in _csv.DictReader(open(m.path("candidates.csv"), encoding="utf-8"))], log)
    except Exception as e:
        log(f"  [WARN] Gaia-Details fuer die Kandidatenliste nicht vorbereitet: {e}")
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
    cl = getattr(n, "comp_lc", None)
    if cl:
        md += ["", f"## Vergleichssterne einzeln (Stern / Summe der uebrigen, {cl['bin_min']:.0f}-min-Mittel)", "",
               "| Stern | RMS [ppt] | Mittel-Streuung [ppt] | Ruhe | beta | Status |", "|---|---|---|---|---|---|"] + [
            f"| {d['name']} | {d['rms_ppt']:.2f} | {d['bin_ppt']:.2f} | {d['ruhe']:.1f} | {d['beta']:.2f} | "
            f"{p['grund'] or ('Ensemble' if d['name'] in best['comps'] else 'ok')} |"
            for d, p in zip(cl["stars"], n.prefilter_table)]
    md += ["", "Plots: lightcurve.png, tc_hist.png, linearity.png, flip_offset.png, vergleichssterne_lc.png. "
               "Daten: fit.json, top50.csv, compsearch.json."]
    md += ["", "Ergebnisblatt: ergebnisblatt.png / .pdf / .html (auch in exoclock_paket\\)."]
    with open(m.path("summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    log("Bericht: summary.md, lightcurve.png, tc_hist.png, linearity.png, flip_offset.png, vergleichssterne_lc.png")
    from .ergebnisblatt import make_sheet
    make_sheet(m, n, c, log)
