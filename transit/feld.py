"""Page 2 of the Ergebnisblatt: stretched field image (north up, east left) with target and ensemble, and the
comparison-star table with Gaia parameters and the reason each star was used.  Display only (see ergebnisblatt.py)."""
import csv
import json
import math
import os

import numpy as np
from matplotlib.patches import Circle

from .export import dms, hms


# ------------------------------------------------------------------ Gaia quality flags (cached per run)
def gaia_details(m, ids, log=print, netz=True):
    """RUWE, phot_variable_flag, non_single_star for the given Gaia DR3 source_ids; cache RESULT\\<lauf>\\gaia_details.json.
    Taken from the run's gaia_field.csv when it carries these columns, else queried ([gaia] quelle: VizieR or ESA).
    netz=False: only cache and gaia_field.csv, never the network (the GUI must answer at once)."""
    from . import gaia
    cache = m.path("gaia_details.json")
    d = json.load(open(cache, encoding="utf-8")) if os.path.exists(cache) else {}
    todo = [str(int(i)) for i in ids if str(i) not in d]
    if not todo:
        return d
    import time
    offline = d.get("_offline", 0)
    put = lambda sid, row: d.__setitem__(sid, dict(zip(("ruwe", "var", "nss"), gaia.flags(row))))
    fp = m.path("gaia_field.csv")
    if os.path.exists(fp):
        from astropy.table import Table
        t = gaia._lower(Table.read(fp))
        if "ruwe" in t.colnames:                                  # field cache written by this version: no network needed
            for row in t:
                if str(int(row["source_id"])) in todo:
                    put(str(int(row["source_id"])), row)
            todo = [i for i in todo if i not in d]
    if todo and not netz:
        todo = []
    if todo and time.time() - offline < 6 * 3600:            # failed a short while ago: do not wait for the timeouts again
        log("  Gaia-Details: letzte Abfrage fehlgeschlagen, neuer Versuch fruehestens 6 h danach")
        todo = []
    if todo:
        try:
            src, timeout = gaia.settings(m.cfg)
            if src == "esa":
                import socket
                from astroquery.gaia import Gaia
                q = ("SELECT source_id, ruwe, phot_variable_flag, non_single_star FROM gaiadr3.gaia_source WHERE source_id IN ("
                     + ",".join(todo) + ")")
                old = socket.getdefaulttimeout()
                socket.setdefaulttimeout(timeout)
                try:
                    r = gaia._lower(Gaia.launch_job(q).get_results())
                finally:
                    socket.setdefaulttimeout(old)
            else:                                                 # VizieR: one cone over the candidates
                cand = {str(x.get("source_id", "")): x for x in csv.DictReader(open(m.path("candidates.csv"), encoding="utf-8"))}
                pts = [(float(cand[i]["ra"]), float(cand[i]["dec"])) for i in todo if i in cand]
                if not pts:
                    raise RuntimeError("keine Koordinaten in candidates.csv")
                ra = np.array([p[0] for p in pts]); de = np.array([p[1] for p in pts])
                ra0, de0 = float(np.mean(ra)), float(np.mean(de))
                rad = float(np.max(np.hypot((ra - ra0) * np.cos(np.radians(de0)), de - de0))) + 0.01
                r = gaia.cone(m.cfg, ra0, de0, rad)
            for row in r:
                sid = str(int(row["source_id"]))
                if sid in todo:
                    put(sid, row)
            d.pop("_offline", None)
        except Exception as e:
            d["_offline"] = time.time()
            log(f"  Gaia ({gaia.name(m.cfg)}) nicht erreichbar ({e}) - RUWE/Variabilitaet bleiben leer")
    json.dump(d, open(cache, "w", encoding="utf-8"), indent=1)
    return d


# ------------------------------------------------------------------ orientation: rotate/flip so that north is up, east left
def _orient(N, E):
    """Best of the 8 rot90/fliplr combinations: (flip, k) with N up and E left (display origin lower)."""
    best = None
    for flip in (False, True):
        for k in range(4):
            n_, e_ = np.array(N, float), np.array(E, float)
            if flip:
                n_[0] *= -1; e_[0] *= -1
            for _ in range(k):
                n_ = np.array([n_[1], -n_[0]]); e_ = np.array([e_[1], -e_[0]])
            sc = n_[1] / np.linalg.norm(n_) - e_[0] / np.linalg.norm(e_)
            if best is None or sc > best[0]:
                best = (sc, flip, k, n_, e_)
    return best[1:]


def _apply(img, xy, flip, k):
    """Transform image and point coordinates (x = column, y = row) the same way."""
    xy = [np.array(p, float) for p in xy]
    if flip:
        nx = img.shape[1]
        img = img[:, ::-1]
        for p in xy:
            p[..., 0] = nx - 1 - p[..., 0]
    for _ in range(k):
        nx = img.shape[1]
        img = np.rot90(img)
        for p in xy:
            x, y = p[..., 0].copy(), p[..., 1].copy()
            p[..., 0], p[..., 1] = y, nx - 1 - x
    return img, xy


# ------------------------------------------------------------------ does a comparison star change during the transit?
def transit_window_signal(n, c, ens, ir, pred):
    """Per ensemble star: mean of star/(other ensemble stars) inside the predicted transit window minus outside, after the
    same airmass/flip baseline as the fit, in ppt with error.  Data only (no literature depth): a star that brightens or fades
    exactly in the window changes the measured depth by about share x signal."""
    F = c["flux"][n.sel][:, :, ir]
    intr = ((n.t > pred["ingress"]) & (n.t < pred["egress"])).astype(float)
    A = np.c_[n.X, intr]
    out = {}
    for j in ens:
        others = [k for k in ens if k != j]
        if not others:
            continue
        y = F[:, j] / F[:, others].sum(1)
        y = y / np.median(y[n.oot])
        co, *_ = np.linalg.lstsq(A, y, rcond=None)
        r = y - A @ co
        cov = np.linalg.inv(A.T @ A) * r.var(ddof=A.shape[1])
        out[j] = (float(co[-1] * 1e3), float(np.sqrt(cov[-1, -1]) * 1e3))
    return out


# ------------------------------------------------------------------ comparison-star table
def comp_rows(m, n, c, fr, cs, ens, ir, log=print):
    cand = {r["name"]: r for r in csv.DictReader(open(m.path("candidates.csv"), encoding="utf-8"))}
    pre = {p["name"]: p for p in cs.get("prefilter", [])}
    ranked = sorted([p for p in cs.get("prefilter", []) if not p["rejected"]], key=lambda p: p["rms_ppt"])
    rank = {p["name"]: i + 1 for i, p in enumerate(ranked)}
    gf = list(csv.DictReader(open(m.path("gaia_field.csv")))) if os.path.exists(m.path("gaia_field.csv")) else []
    for g in gf:
        for k_ in list(g):
            if k_ != k_.lower():
                g[k_.lower()] = g.pop(k_)
    gra = np.array([float(g["ra"]) for g in gf]); gde = np.array([float(g["dec"]) for g in gf])
    gid = np.array([str(g.get("source_id", "")) for g in gf])
    ids = [str(c["star_gaia"][j]) for j in [0] + ens]
    det = gaia_details(m, ids, log)
    ra0, de0, G0 = float(c["star_ra"][0]), float(c["star_dec"][0]), float(c["star_G"][0])
    col0 = float(cand.get("T1", {}).get("bp_rp") or "nan")
    flux = np.nanmedian(c["flux"][n.sel][:, ens, ir], axis=0)
    share = flux / flux.sum()
    mc = fr["mcmc"]
    jk = {d["drop"]: d["OC_min"] - mc["OC_min"] for d in fr["jackknife"]}
    pk = np.nanmax(c["peak_raw"][n.sel], axis=0)
    tw = transit_window_signal(n, c, ens, ir, fr["ephemeris"])
    rows = []
    for q, j in enumerate([0] + ens):
        nm = n.names[j]
        ra, de = float(c["star_ra"][j]), float(c["star_dec"][j])
        dist = math.hypot((ra - ra0) * math.cos(math.radians(de0)), de - de0) * 60
        cd = cand.get(nm, {})
        col = float(cd.get("bp_rp") or "nan")
        sep = np.hypot((gra - ra) * math.cos(math.radians(de)), gde - de) * 3600 if len(gf) else np.array([])
        nb = int(((gid != ids[q]) & (sep < 10)).sum()) if len(gf) else 0     # the star itself excluded by its Gaia id
        gd = det.get(ids[q], {})
        ruwe, var = gd.get("ruwe"), gd.get("var", "")
        dG, dc = float(c["star_G"][j]) - G0, col - col0
        warn = []
        if ruwe and ruwe > 1.4:
            warn.append(f"RUWE {ruwe:.1f} (evtl. Doppelstern)")
        if var and var.upper().startswith("VARIABLE"):
            warn.append("Gaia: VARIABLE")
        if nb:
            warn.append(f"{nb} Nachbar(n) < 10\"")
        sig = tw.get(j)
        if sig and abs(sig[0]) > 3 * sig[1]:
            warn.append(f"im Transitfenster {sig[0]:+.1f} +- {sig[1]:.1f} ppt veraendert ({abs(sig[0]) / sig[1]:.0f} sigma) - "
                        f"faelscht die Tiefe um ca. {sig[0] * share[ens.index(j)]:+.2f} ppt, ausschliessen ([comps] exclude_stars)")
        if j == 0:
            why = "Zielstern mit dem Exoplaneten"
        else:
            parts = [("aehnlich hell" if abs(dG) < 0.3 else "hell genug" if dG < 0 else "etwas schwaecher") + f" (dG {dG:+.2f})",
                     ("gleiche Farbe" if abs(dc) < 0.15 else "aehnliche Farbe") + f" (d {dc:+.2f})"]
            if nm in rank:
                ru = pre[nm].get("ruhe")
                parts.append(f"ruhig: Streuung Rang {rank[nm]}/{len(ranked)}" + (f", Ruhe {ru:.1f}" if ru is not None and ru == ru else ""))
            parts.append(f"im besten Ensemble ({n.r_text(fr['best']['radius'])})")
            why = "; ".join(parts) + ("; ACHTUNG " + ", ".join(warn) if warn else "")
        rows.append(dict(id="Ziel" if j == 0 else f"C{q}", name=nm, gaia=ids[q], ra=hms(ra), dec=dms(de), dist=dist,
                         G=float(c["star_G"][j]), dG=dG, col=col, dc=dc, peak=float(pk[j]), ruwe=ruwe, var=var or "-",
                         var_s="VAR" if (var or "").upper().startswith("VARIABLE") else "-" if not var or var.upper().startswith("NOT") else var[:8],
                         nb=nb, rms=pre.get(nm, {}).get("rms_ppt"), ruhe=pre.get(nm, {}).get("ruhe"), share=None if j == 0 else float(share[q - 1]) * 100,
                         jk=jk.get(nm), tw=None if sig is None else sig[0], tw_e=None if sig is None else sig[1],
                         tw_flag=bool(sig and abs(sig[0]) > 3 * sig[1]), why=why))
    # rejected candidates (a few lines)
    rej = []
    for p in cs.get("prefilter", []):
        if p["rejected"]:
            rej.append((p["name"], "Vorfilter: " + (p.get("grund") or
                                   f"Streuung {p['rms_ppt']:.1f} ppt / Trend {p['trend_ppt']:.1f} ppt > "
                                   f"{m.cfg['search']['prefilter_sigma']:g}x Median (veraenderlich oder gestoert)")))
    for nm in fr["info"].get("excluded_stars", []):
        rej.insert(0, (nm, "von Hand ausgeschlossen ([comps] exclude_stars in lauf.toml/transit.toml)"))
    for nm in fr["info"].get("dropped_saturating", []):
        rej.append((nm, f"in > 5 % der Frames ueber {m.cfg['camera']['saturation_adu']} ADU (Saettigung)"))
    used = set(n.names[j] for j in ens)
    unused = [nm for nm in pre if not pre[nm]["rejected"] and nm not in used]
    rp = m.path("candidates_rejected.csv")
    if os.path.exists(rp):
        rr = [r for r in csv.DictReader(open(rp, encoding="utf-8")) if float(r["edge_px"]) > 0]
        rr.sort(key=lambda r: abs(float(r["dG"])))
        for r in rr[:6]:
            rej.append((f"Gaia {r['source_id']}", f"G {float(r['G']):.2f}: {r['reasons']}"))
        n_rr = len(rr)
    else:
        n_rr = 0
    return rows, rej, unused, n_rr


# ------------------------------------------------------------------ the page
def draw_page(fig, m, n, c, fr, cs, ens, planet, star, log=print):
    from astropy.io import fits
    from astropy.wcs import WCS
    from .frames import read_data
    best, mc = fr["best"], fr["mcmc"]
    ir = n.ir(best["radius"])
    rows, rej, unused, n_rr = comp_rows(m, n, c, fr, cs, ens, ir, log)
    nr = len(rows) + 1                                     # table rows incl. header
    n_txt = len(rows) + 3 + min(len(rej), 10) + (1 if n_rr > 6 else 0)
    # representative frame: best seeing within +-0.5 h of the measured mid-transit
    t = c["bjd_tdb"]
    near = n.sel & (np.abs(t - mc["Tc"][1]) < 0.5 / 24)
    if not near.any():
        near = n.sel
    fi = int(np.argmin(np.where(near, c["fwhm"], np.inf)))
    fn = str(c["frame_file"][fi])
    path = next(p for p in (os.path.join(m.root, "SOLVED", fn), os.path.join(m.lights, fn)) if os.path.exists(p))
    img = read_data(path).astype(np.float32)
    w = WCS(fits.getheader(path))
    fac = max(1, int(math.ceil(max(img.shape) / 1400)))
    ny, nx = img.shape[0] // fac * fac, img.shape[1] // fac * fac
    sm = img[:ny, :nx].reshape(ny // fac, fac, nx // fac, fac).mean((1, 3))
    # stretch: asinh around the sky; background dark grey, stars not burnt out
    bg = float(np.median(sm)); sd = float(1.4826 * np.median(np.abs(sm - bg)))
    z = np.arcsinh((sm - bg) / max(3 * sd, 1e-3))
    lo, hi = np.arcsinh(-1.5), np.percentile(z, 99.95)
    disp = np.clip((z - lo) / (hi - lo), 0, 1)
    # orientation from the WCS at the target
    ra0, de0 = float(c["star_ra"][0]), float(c["star_dec"][0])
    p0 = np.array(w.world_to_pixel_values(ra0, de0), float)
    pN = np.array(w.world_to_pixel_values(ra0, de0 + 0.05), float)
    pE = np.array(w.world_to_pixel_values(ra0 + 0.05 / math.cos(math.radians(de0)), de0), float)
    flip, k, Nv, Ev = _orient(pN - p0, pE - p0)
    # positions in downsampled pixels: ensemble from the cube, unused candidates and rejected via WCS
    sx, sy = c["x"][fi] / fac, c["y"][fi] / fac
    pts = np.c_[sx, sy]
    rp = m.path("candidates_rejected.csv")
    rejxy = np.zeros((0, 2))
    if os.path.exists(rp):
        rr = [r for r in csv.DictReader(open(rp, encoding="utf-8")) if float(r["edge_px"]) > 0]
        if rr:
            rx, ry = w.world_to_pixel_values(np.array([float(r["ra"]) for r in rr]), np.array([float(r["dec"]) for r in rr]))
            rejxy = np.c_[rx, ry] / fac
    disp, (pts, rejxy) = _apply(disp, [pts, rejxy], flip, k)
    # layout in inches from the real content: header, image (its own aspect), table title, table, text
    W = 11.69
    img_w = 0.93 * W
    img_h = img_w * disp.shape[0] / disp.shape[1]
    Y = {}
    y = 1.4
    Y["img"] = (y, img_h); y += img_h + 1.0
    Y["tab"] = (y, 0.22 * nr); y += 0.22 * nr + 0.3
    Y["txt"] = (y, 0.125 * n_txt + 0.1); y += 0.125 * n_txt + 0.1 + 0.45
    Ht = y
    fig.set_size_inches(W, Ht)
    box = lambda key: [0.05, 1 - (Y[key][0] + Y[key][1]) / Ht, 0.93, Y[key][1] / Ht]
    fig.text(0.05, 1 - 0.3 / Ht, f"Feld und Vergleichssterne  -  {planet}", fontsize=19, weight="bold", va="top")
    ax = fig.add_axes(box("img"))
    ax.imshow(disp, origin="lower", cmap="gray", vmin=0, vmax=1, interpolation="lanczos")
    rad = max(n.r_px(best["radius"]) / fac * 2.5, 7)
    lab = {r["name"]: r["id"] for r in rows}
    for j in range(len(n.names)):
        x_, y_ = pts[j]
        if not np.isfinite(x_):
            continue
        nm = n.names[j]
        if j == 0:
            ax.add_patch(Circle((x_, y_), rad * 1.6, fill=False, color="#ff5a4e", lw=2))
            ax.annotate(f"{star} ({planet[-1]})", (x_, y_), xytext=(x_ + rad * 5, y_ + rad * 5), color="#ff5a4e", fontsize=13,
                        weight="bold", arrowprops=dict(arrowstyle="-", color="#ff5a4e", lw=1.2))
        elif j in ens:
            ax.add_patch(Circle((x_, y_), rad, fill=False, color="#4fc3ff", lw=1.5))
            ax.text(x_ + rad * 1.2, y_ + rad * 1.2, f"{lab[nm]}", color="#4fc3ff", fontsize=10, weight="bold")
        else:
            ax.add_patch(Circle((x_, y_), rad * 0.8, fill=False, color="0.6", lw=0.8, ls="--"))
            ax.text(x_ + rad, y_ - rad * 1.8, nm, color="0.6", fontsize=6.5)
    if len(rejxy):
        ax.plot(rejxy[:, 0], rejxy[:, 1], "x", color="0.45", ms=4, mew=0.8)
    H, W = disp.shape
    ax.set_xlim(0, W); ax.set_ylim(0, H)
    # compass and scale bar
    pix = 3600 * math.sqrt(abs(np.linalg.det(w.pixel_scale_matrix))) * fac      # arcsec per displayed pixel
    cx, cy, L = W * 0.10, H * 0.10, H * 0.07
    for v, t_ in ((Nv, "N"), (Ev, "O")):
        u_ = v / np.linalg.norm(v) * L
        ax.annotate("", (cx + u_[0], cy + u_[1]), (cx, cy), arrowprops=dict(arrowstyle="->", color="w", lw=1.6))
        ax.text(cx + u_[0] * 1.3, cy + u_[1] * 1.3, t_, color="w", fontsize=11, ha="center", va="center", weight="bold")
    bar = 10 * 60 / pix
    ax.plot([W * 0.80, W * 0.80 + bar], [H * 0.05] * 2, color="w", lw=3)
    ax.text(W * 0.80 + bar / 2, H * 0.07, "10'", color="w", ha="center", fontsize=10, weight="bold")
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(f"{fn}  |  bestes Seeing nahe Transitmitte (FWHM {c['fwhm'][fi]:.1f} px)  |  asinh-Stretch, 1:{fac}, Norden oben, Osten links\n"
                 f"rot: Ziel   blau: Vergleichssterne C1... (Kreise {rad * fac / n.r_px(best['radius']):.1f}x Apertur)   "
                 "grau gestrichelt: geeignete, nicht genutzte Kandidaten   x: verworfene", fontsize=8)

    # table
    at = fig.add_axes(box("tab")); at.axis("off")
    f = lambda v, fmt: "-" if v is None or (isinstance(v, float) and not np.isfinite(v)) else fmt.format(v)
    cells, cols = [], []
    for r in rows:
        cells.append([f"{r['id']} ({r['name']})", r["gaia"], f"{r['ra']} {r['dec']}", f(r["dist"], "{:.1f}"),
                      f(r["G"], "{:.2f}"), f(r["dG"], "{:+.2f}"), f(r["col"], "{:.2f}"), f(r["dc"], "{:+.2f}"),
                      f(r["peak"], "{:.0f}"), f(r["ruwe"], "{:.2f}"), r["var_s"], str(r["nb"]), f(r["rms"], "{:.1f}"),
                      f(r["share"], "{:.0f}"), f(r["jk"], "{:+.1f}"),
                      "-" if r["tw"] is None else f"{r['tw']:+.1f}+-{r['tw_e']:.1f}"])
        flag = (r["ruwe"] and r["ruwe"] > 1.4) or r["nb"] or r["var"].upper().startswith("VARIABLE")
        cc = ["#fde3e1" if r["id"] == "Ziel" else ("#fff3c4" if flag else "w")] * 16
        if r["tw_flag"]:
            cc = ["#f6c1bd"] * 16
        cols.append(cc)
    tb = at.table(cellText=cells, cellColours=cols, loc="upper center", cellLoc="left",
                  colLabels=["Kennung", "Gaia DR3", "RA / Dec (J2000)", "Abst. '", "G", "dG", "BP-RP", "dFarbe", "Peak max",
                             "RUWE", "Var.", "Nb.<10\"", "Streu.", "Anteil%", "JK dO-C", "Transitf. ppt"],
                  colWidths=[0.06, 0.13, 0.155, 0.04, 0.04, 0.04, 0.045, 0.05, 0.055, 0.04, 0.035, 0.05, 0.045, 0.05, 0.055, 0.09])
    tb.auto_set_font_size(False); tb.set_fontsize(7.2); tb.scale(1, 1.25)
    for (i, j_), cl in tb.get_celld().items():
        cl.set_edgecolor("0.75")
        if i == 0:
            cl.set_text_props(weight="bold"); cl.set_facecolor("#e3e8f0")
    at.set_title("Vergleichssterne des besten Ensembles   (Streu. = eigene Streuung im Vorfilter, Anteil = Fluss-Anteil im Ensemble,\n"
                 "JK = Aenderung des O-C ohne diesen Stern, Var. = Gaia-Flag, Nachbarn bis G 16, Transitfenster = Stern gegen die uebrigen\n"
                 "im vorhergesagten Transitfenster minus ausserhalb; gelb = Hinweis, rot = Stern veraendert sich im Transit > 3 sigma)",
                 fontsize=8.5, loc="left")
    # reasons + rejected
    ar = fig.add_axes(box("txt")); ar.axis("off")
    txt = ["Warum diese Sterne:"] + [f"  {r['id']:>4s} {r['name']:<4s} {r['why']}" for r in rows[1:]]
    txt += ["", f"Nicht genutzt: {len(unused)} weitere Kandidaten erfuellen alle Kriterien, verbessern das Ensemble aber nicht"
                f" ({', '.join(unused[:12])}{' ...' if len(unused) > 12 else ''}). Verworfen (Auswahl):"]
    txt += [f"  {a}: {b}" for a, b in rej[:10]]
    if n_rr > 6:
        txt.append(f"  ... insgesamt {n_rr} Gaia-Sterne im Feld durch die Kriterien (Helligkeit, Farbe, Rand, Nachbarn) ausgeschlossen")
    assert len(txt) <= n_txt + 1, (len(txt), n_txt)       # layout above counts on this
    ar.text(0, 1, "\n".join(txt), fontsize=6.9, family="monospace", va="top", transform=ar.transAxes)
    return rows, rej, unused, fn
