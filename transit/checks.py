"""Planning / data-quality checks with German warnings and fixes."""
import numpy as np


def night_checks(m, headers, tm, pred):
    cfg = m.cfg["planning"]
    out = []

    def add(level, text, fix=""):
        out.append(dict(level=level, text=text, fix=fix))
    h0 = headers[0]["header"]
    bj = tm["bjd_tdb"]
    hrs = lambda x: (x - pred["Tc"]) * 24
    # coverage
    if bj.min() > pred["ingress"] or bj.max() < pred["egress"]:
        add("WARN", f"Transit nicht vollstaendig abgedeckt (Daten {hrs(bj.min()):+.2f} h bis {hrs(bj.max()):+.2f} h um Tc)",
            "Laengere Sequenz planen (mind. 1 h vor Ingress bis 1 h nach Egress).")
    pre = (pred["ingress"] - bj.min()) * 24
    post = (bj.max() - pred["egress"]) * 24
    for lab, v in (("vor Ingress", pre), ("nach Egress", post)):
        if v < cfg["baseline_min_h"]:
            add("WARN", f"Baseline {lab} nur {v * 60:.0f} min", f"Mindestens {cfg['baseline_min_h']:.1f} h Baseline {lab} einplanen.")
    am = tm["airmass_calc"]
    post_m = bj > pred["egress"]
    if post_m.any() and np.median(am[post_m]) > cfg["airmass_max_baseline"]:
        add("WARN", f"Baseline nach Egress bei Airmass {am[post_m].min():.1f}-{am[post_m].max():.1f}",
            "Ziel steht zu tief; Naechte waehlen, in denen der Transit nahe Kulmination liegt.")
    # meridian flip
    e = tm["east"]
    if e.min() != e.max():
        i = np.where(np.diff(e) != 0)[0][0]
        tf = 0.5 * (bj[i] + bj[i + 1])
        dt_in = (pred["ingress"] - tf) * 24
        dt_eg = (tf - pred["egress"]) * 24
        if pred["ingress"] - cfg["flip_min_before_ingress_h"] / 24 < tf < pred["egress"] + 0.25 / 24:
            add("CRIT", f"Meridian-Flip {f'{dt_in * 60:.0f} min vor Ingress' if dt_in > 0 else f'{-dt_in * 60:.0f} min nach Ingress'} (im/nahe am Transit)",
                "Flip zeitlich verlegen (vor die Baseline oder nach Egress), Montierung ueber den Meridian nachfuehren lassen. "
                "Auswertung: Flip-Versatz aus Vergleichssternen als Prior (fit.flip = 'prior').")
        else:
            lage = f"{dt_in:.1f} h vor Ingress" if dt_in > 0 else f"{dt_eg:.1f} h nach Egress"
            add("INFO", f"Meridian-Flip ausserhalb des Transits ({lage})")
    # header airmass vs computed
    d = tm["airmass_header"] - am
    if np.nanmax(np.abs(d)) > 0.01:
        add("WARN", f"Header-AIRMASS weicht um bis zu {np.nanmax(np.abs(d)):.3f} von der berechneten ab "
                    f"(Mittel West {np.nanmean(d[e == 0]):+.3f}, Ost {np.nanmean(d[e == 1]):+.3f})",
            "Das Werkzeug benutzt immer die aus den Zielkoordinaten berechnete Airmass.")
    # temperature
    ct = np.array([float(x["header"].get("CCD-TEMP", np.nan)) for x in headers])
    stp = h0.get("SET-TEMP")
    if stp is not None and np.nanmax(np.abs(ct - float(stp))) > 1.5:
        add("WARN", f"Kameratemperatur {np.nanmin(ct):.1f}..{np.nanmax(ct):.1f} C, Soll {stp} C nicht gehalten",
            "Darks bei passender Temperatur fehlen -> Bias+Flat (calib.mode='bf') oder skalierter Dark.")
    # plate solve
    ns = sum(not x["solved"] for x in headers)
    if ns:
        add("WARN", f"{ns} Frames ohne WCS (nicht plate-solved)", "transit solve <Messordner> (schreibt Kopien nach SOLVED\\)")
    return out


def peak_checks(cube, cfg):
    out = []
    sat, warn = cfg["camera"]["saturation_adu"], cfg["camera"]["linearity_warn_adu"]
    pk = cube["peak_raw"][:, 0]
    n_sat, n_warn = int((pk > sat).sum()), int(((pk > warn) & (pk <= sat)).sum())
    if n_sat:
        out.append(dict(level="WARN", text=f"Ziel-Peak > {sat:.0f} ADU in {n_sat} Frames (verworfen)",
                        fix="Kuerzer belichten oder leicht defokussieren."))
    if n_warn:
        out.append(dict(level="INFO", text=f"Ziel-Peak {warn:.0f}-{sat:.0f} ADU in {n_warn} Frames (Linearitaet pruefen: transit report)"))
    return out
