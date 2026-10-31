"""Target and comparison-star candidates from Gaia DR3 (+ optional AIJ comparison stars)."""
import csv
import os

import numpy as np
from astropy.coordinates import SkyCoord
from astropy.table import Table
from astropy.wcs import WCS
import astropy.units as u


def gaia_field(m, h0, log=None):
    """Gaia DR3 stars on the frame (cached per run in gaia_field.csv); source per [gaia] quelle (VizieR or ESA)."""
    cache = m.path("gaia_field.csv")
    if not os.path.exists(cache):                      # same night, same field: reuse another run's Gaia query
        import glob
        import shutil
        old = sorted(glob.glob(os.path.join(os.path.dirname(m.out), "*", "gaia_field.csv")), key=os.path.getmtime, reverse=True)
        if old:
            shutil.copy2(old[0], cache)
            if log:
                log(f"  Gaia-Feld aus Lauf {os.path.basename(os.path.dirname(old[0]))} uebernommen (keine Netzabfrage)")
    if os.path.exists(cache):
        g = Table.read(cache)
    else:
        from . import gaia
        w = WCS(h0)
        nx, ny = h0["NAXIS1"], h0["NAXIS2"]
        c = w.pixel_to_world(nx / 2, ny / 2)
        scale = abs(h0.get("CDELT1", 0)) or np.sqrt(abs(np.linalg.det(w.pixel_scale_matrix)))
        rad = 0.5 * np.hypot(nx, ny) * scale + 0.02
        try:
            g = gaia.cone(m.cfg, c.ra.deg, c.dec.deg, rad, gmax=m.cfg["comps"]["gaia_gmax"], log=log)
        except RuntimeError as e:
            raise SystemExit(str(e))
        g.write(cache, overwrite=True)
    for n in g.colnames:                      # Gaia archive 3.15 returns SOURCE_ID in upper case
        if n != n.lower():
            g.rename_column(n, n.lower())
    return g


def aij_comps(path):
    d = {}
    for line in open(path):
        if "=" in line:
            k, v = line.strip().split("=", 1)
            d[k] = v
    ra = [float(x) for x in d[".multiaperture.raapertures"].split(",")]
    de = [float(x) for x in d[".multiaperture.decapertures"].split(",")]
    ref = [x == "true" for x in d.get(".multiaperture.isrefstar", "").split(",")] or [True] * len(ra)
    return [(r, dd) for r, dd, isref in zip(ra, de, ref) if isref]


def select(m, headers, epoch_jyear, target):
    """Write candidates.csv (+ candidates_rejected.csv); returns the selected list (target first)."""
    cc = m.cfg["comps"]
    solved = [x for x in headers if x["solved"]]
    h0 = solved[0]["header"]
    nx, ny = h0["NAXIS1"], h0["NAXIS2"]
    g = gaia_field(m, h0, log=print)
    dt = epoch_jyear - 2016.0
    pmra = np.nan_to_num(np.array(g["pmra"], float)); pmde = np.nan_to_num(np.array(g["pmdec"], float))
    de0 = np.array(g["dec"], float)
    ra = np.array(g["ra"], float) + pmra * dt / 3.6e6 / np.cos(np.radians(de0))
    de = de0 + pmde * dt / 3.6e6
    G = np.array(g["phot_g_mean_mag"], float)
    col = g["bp_rp"]
    bprp = np.array(col.filled(np.nan) if hasattr(col, "filled") else col, float)
    edge = np.full(len(ra), np.inf)
    for x in solved:
        px, py = WCS(x["header"]).world_to_pixel_values(ra, de)
        edge = np.minimum(edge, np.minimum.reduce([px, py, nx - 1 - px, ny - 1 - py]))
    x0, y0 = WCS(h0).world_to_pixel_values(ra, de)
    allc = SkyCoord(ra * u.deg, de * u.deg)
    sep = allc.separation(target).arcsec
    it = int(np.argmin(sep))
    if sep[it] > 5:
        raise SystemExit(f"Kein Gaia-Stern innerhalb 5\" der Zielkoordinaten (naechster {sep[it]:.1f}\")")
    Gt, ct = G[it], bprp[it]
    rows = []
    for i in range(len(ra)):
        if i == it or not (Gt + cc["dmag_bright"] <= G[i] <= Gt + cc["dmag_faint"]):
            continue
        why = []
        if edge[i] < cc["edge_px"]:
            why.append(f"Rand {edge[i]:.0f}px")
        d = np.hypot(x0 - x0[i], y0 - y0[i])
        nb = (d < cc["neighbour_px"]) & (d > 0) & (G < G[i] + cc["neighbour_dmag"])
        if nb.any():
            why.append(f"{nb.sum()} Nachbar(n) innerhalb {d[nb].min():.0f}px")
        if not np.isfinite(bprp[i]) or abs(bprp[i] - ct) > cc["color_tol"]:
            why.append(f"BP-RP {bprp[i]:.2f}")
        rows.append(dict(source_id=int(g["source_id"][i]), ra=ra[i], dec=de[i], G=G[i], bp_rp=bprp[i], dG=G[i] - Gt,
                         edge_px=edge[i], ok=not why, reasons="; ".join(why)))
    sel = [dict(name="T1", role="target", source_id=int(g["source_id"][it]), ra=target.ra.deg, dec=target.dec.deg,
                G=Gt, bp_rp=ct, reasons=f"Ziel, Gaia-Abstand {sep[it]:.2f}\"")]
    ids = {sel[0]["source_id"]}
    apf = cc.get("aij_apertures") or ""
    if apf and not os.path.isabs(apf):
        apf = os.path.join(m.root, apf)
    if apf and os.path.exists(apf):
        for k, (r_, d_) in enumerate(aij_comps(apf)):
            s = allc.separation(SkyCoord(r_, d_, unit="deg")).arcsec
            j = int(np.argmin(s))
            sel.append(dict(name=f"C{k + 2}", role="aij_comp", source_id=int(g["source_id"][j]), ra=r_, dec=d_,
                            G=G[j], bp_rp=bprp[j], reasons=f"AIJ-Vergleichsstern, Gaia {s[j]:.1f}\""))
            ids.add(int(g["source_id"][j]))
    ok = sorted([r for r in rows if r["ok"] and r["source_id"] not in ids], key=lambda r: abs(r["dG"]))[:cc["max_candidates"]]
    for n, r in enumerate(ok, 1):
        sel.append(dict(name=f"G{n:02d}", role="gaia_comp", source_id=r["source_id"], ra=r["ra"], dec=r["dec"], G=r["G"],
                        bp_rp=r["bp_rp"], reasons=f"dG={r['dG']:+.2f}, dFarbe={r['bp_rp'] - ct:+.2f}, Rand {r['edge_px']:.0f}px"))
    with open(m.path("candidates.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(sel[0].keys())); w.writeheader(); w.writerows(sel)
    with open(m.path("candidates_rejected.csv"), "w", newline="") as fh:
        rej = [r for r in rows if not r["ok"]]
        if rej:
            w = csv.DictWriter(fh, fieldnames=list(rej[0].keys())); w.writeheader(); w.writerows(rej)
    return sel, dict(n_gaia=len(ra), n_window=len(rows), n_ok=sum(r["ok"] for r in rows), target_gaia=sel[0]["source_id"])


def load(m):
    with open(m.path("candidates.csv")) as fh:
        sel = list(csv.DictReader(fh))
    for s in sel:
        for k in ("ra", "dec", "G"):
            s[k] = float(s[k])
    return sel
