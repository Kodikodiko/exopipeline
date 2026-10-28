"""Growing aperture: radius per frame r_i = k x FWHM_i, the same r_i for the target and all comparison stars.

Built from the fixed-radius photometry in the cube (photometry.radii), no second pass over the lights: the flux at
r_i is interpolated linearly between the two neighbouring fixed radii (curve of growth), flux errors likewise.
FWHM_i is the median FWHM of the comparison stars in frame i (target left out, so the transit cannot leak in),
smoothed with a running median over photometry.fwhm_smooth frames.  Lower limit 1.5 x median FWHM.  The background
annulus stays fixed (photometry.annulus).  A k is skipped when its radius leaves the measured radius grid in more
than 5 % of the frames.

Variable apertures appear next to the fixed radii under labels like "k2.5" (cube["radii"], search.radii, fit.json).
"""
import numpy as np

MODES = ("fest", "variabel", "beides")


def label(k):
    return f"k{k:g}"


def is_variable(r):
    return isinstance(r, str) and r.startswith("k")


def frame_fwhm(c, nsmooth=5):
    f = np.nanmedian(np.asarray(c["fwhm_star"], float)[:, 1:], axis=1)
    order = np.argsort(c["bjd_tdb"])
    g, h = f[order], max(0, int(nsmooth) // 2)
    sm = np.array([np.nanmedian(g[max(0, i - h):i + h + 1]) for i in range(len(g))])
    out = np.empty_like(f)
    out[order] = sm
    out[~np.isfinite(out)] = np.nanmedian(out)
    return out


def add_variable(c, cfg, log=print):
    """Append the variable apertures to the cube (flux, flux_err, radii); returns their labels."""
    ph = cfg["photometry"]
    mode = ph.get("aperture_mode", "fest")
    if mode not in MODES:
        raise SystemExit(f"photometry.aperture_mode = '{mode}' unbekannt ({' | '.join(MODES)})")
    if mode == "fest" or "vap" in c:
        return list(c.get("vap", {}))
    radii = np.asarray(c["radii"], float)
    fw = frame_fwhm(c, ph.get("fwhm_smooth", 5))
    rmin = 1.5 * float(np.nanmedian(fw))
    F, E = c["flux"], c["flux_err"]
    nf = F.shape[0]
    rows = np.arange(nf)
    newF, newE, info = [], [], {}
    for k in ph.get("k_fwhm", [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]):
        want = np.maximum(k * fw, rmin)
        out = int(((want < radii[0] - 1) | (want > radii[-1] + 1)).sum())     # up to 1 px outside: clipped
        if out > 0.05 * nf:
            log(f"[INFO] mitwachsende Apertur k={k:g}: Radius {want.min():.1f}-{want.max():.1f} px liegt in {out} Bildern "
                f"ausserhalb der gemessenen Radien {radii[0]:g}-{radii[-1]:g} px - uebersprungen (photometry.radii erweitern)")
            continue
        r = np.clip(want, radii[0], radii[-1])
        j = np.clip(np.searchsorted(radii, r) - 1, 0, len(radii) - 2)
        w = ((r - radii[j]) / (radii[j + 1] - radii[j]))[:, None]
        newF.append(F[rows, :, j] * (1 - w) + F[rows, :, j + 1] * w)
        newE.append(E[rows, :, j] * (1 - w) + E[rows, :, j + 1] * w)
        info[label(k)] = dict(k=float(k), r=r)
    if newF:
        c["flux"] = np.concatenate([F, np.stack(newF, axis=2)], axis=2)
        c["flux_err"] = np.concatenate([E, np.stack(newE, axis=2)], axis=2)
    c["radii"] = [float(x) for x in radii] + list(info)
    c["vap"], c["fwhm_frame"] = info, fw
    return list(info)


def search_radii(cfg, labels):
    """Radii for the combination search: fixed ones (search.radii), variable ones, or both."""
    mode = cfg["photometry"].get("aperture_mode", "fest")
    fixed = [r for r in cfg["search"]["radii"] if not is_variable(r)]
    return ([] if mode == "variabel" else fixed) + (labels if mode != "fest" else [])


def px(c, r, sel=None):
    """(median, min, max) radius in px."""
    v = c.get("vap", {}).get(r)
    if v is None:
        return float(r), float(r), float(r)
    a = v["r"] if sel is None else v["r"][sel]
    return float(np.median(a)), float(a.min()), float(a.max())


def text(c, r, sel=None):
    if not is_variable(r):
        return f"r={float(r):g} px (fest)"
    med, lo, hi = px(c, r, sel)
    return f"mitwachsend k={c['vap'][r]['k']:g} x FWHM (r {lo:.1f}-{hi:.1f} px)"
