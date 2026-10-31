"""Gaia DR3 queries: VizieR (I/355/gaiadr3, default) or the ESA Gaia archive, with a timeout.

[gaia] quelle = "vizier" | "esa", timeout_s = 60.  All functions return astropy tables with the ESA column names
in lower case (source_id, ra, dec, pmra, pmdec, phot_g_mean_mag, bp_rp, ruwe, phot_variable_flag, non_single_star),
whichever service answered.  ra/dec are the Gaia positions at epoch 2016.0 in both cases.
"""
import socket

import numpy as np
from astropy.table import Table

VIZIER_CAT = "I/355/gaiadr3"
# VizieR column -> ESA column
VIZ = {"Source": "source_id", "RA_ICRS": "ra", "DE_ICRS": "dec", "pmRA": "pmra", "pmDE": "pmdec", "Gmag": "phot_g_mean_mag",
       "BP-RP": "bp_rp", "RUWE": "ruwe", "VarFlag": "phot_variable_flag", "NSS": "non_single_star"}
COLS = list(VIZ.values())


def settings(cfg):
    g = (cfg or {}).get("gaia", {})
    q = str(g.get("quelle", "vizier")).strip().lower()
    return ("esa" if q in ("esa", "gaia", "archiv", "archive") else "vizier"), float(g.get("timeout_s", 60) or 60)


def name(cfg):
    return "ESA-Gaia-Archiv" if settings(cfg)[0] == "esa" else "VizieR (I/355/gaiadr3)"


def _lower(t):
    for n in t.colnames:
        if n != n.lower():
            t.rename_column(n, n.lower())
    return t


def _vizier(ra, dec, radius_deg, gmin, gmax, timeout):
    from astroquery.vizier import Vizier
    import astropy.units as u
    from astropy.coordinates import SkyCoord
    filt = {}
    if gmin is not None and gmax is not None:
        filt["Gmag"] = f"{gmin:.3f}..{gmax:.3f}"
    elif gmax is not None:
        filt["Gmag"] = f"<{gmax:.3f}"
    v = Vizier(columns=list(VIZ), column_filters=filt, row_limit=-1, timeout=timeout)
    r = v.query_region(SkyCoord(ra, dec, unit="deg"), radius=radius_deg * u.deg, catalog=VIZIER_CAT)
    t = r[0] if len(r) else Table(names=list(VIZ))
    for k, n in VIZ.items():
        if k in t.colnames:
            t.rename_column(k, n)
    return t


def _esa(ra, dec, radius_deg, gmin, gmax, timeout):
    from astroquery.gaia import Gaia
    Gaia.ROW_LIMIT = -1
    w = []
    if gmax is not None:
        w.append(f"phot_g_mean_mag < {gmax}" if gmin is None else f"phot_g_mean_mag BETWEEN {gmin} AND {gmax}")
    q = (f"SELECT {', '.join(COLS)} FROM gaiadr3.gaia_source "
         f"WHERE 1=CONTAINS(POINT(ra,dec), CIRCLE({ra},{dec},{radius_deg}))" + "".join(f" AND {x}" for x in w))
    old = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)                     # astroquery's Gaia TAP client has no timeout of its own
    try:
        return _lower(Table(Gaia.launch_job(q).get_results()))
    finally:
        socket.setdefaulttimeout(old)


def cone(cfg, ra, dec, radius_deg, gmax=None, gmin=None, log=None):
    """Gaia DR3 stars within radius_deg around (ra, dec), optionally limited in G.  Raises RuntimeError with a
    readable text on timeout / no connection."""
    src, timeout = settings(cfg)
    fn = _esa if src == "esa" else _vizier
    try:
        t = fn(float(ra), float(dec), float(radius_deg), gmin, gmax, timeout)
    except Exception as e:
        other = "esa" if src == "vizier" else "vizier"
        raise RuntimeError(f"Gaia-Abfrage ueber {name(cfg)} fehlgeschlagen ({type(e).__name__}: {e}). "
                           f"Netz pruefen oder unter Erweitert die Gaia-Quelle auf '{other}' stellen "
                           f"([gaia] quelle = \"{other}\").") from e
    t = _lower(t)
    for n in COLS:                                        # same columns whatever the service returned
        if n not in t.colnames:
            t[n] = np.full(len(t), "" if n == "phot_variable_flag" else np.nan, dtype=object if n == "phot_variable_flag" else float)
    if log:
        log(f"  Gaia DR3 ueber {name(cfg)}: {len(t)} Sterne")
    return t


def flags(row):
    """(ruwe, variable flag text, non_single_star) of one table row; masked/empty values -> None, "", 0."""
    def val(k, cast, empty):
        try:
            x = row[k]
        except (KeyError, IndexError):
            return empty
        if np.ma.is_masked(x) or x is None or (isinstance(x, float) and not np.isfinite(x)) or str(x).strip() in ("", "--", "nan"):
            return empty
        try:
            return cast(x)
        except (TypeError, ValueError):
            return empty
    var = val("phot_variable_flag", str, "").strip()
    return val("ruwe", float, None), var, int(val("non_single_star", float, 0))
