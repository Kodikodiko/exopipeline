"""Known variable stars from catalogues: AAVSO VSX (VizieR B/vsx/vsx) for the comparison-star selection.

The Gaia DR3 flag phot_variable_flag (already in gaia_field.csv) covers the stars Gaia classified; VSX adds the
variables found by ASAS-SN, ZTF, ATLAS, TESS, Hipparcos, GCVS and others.  Both are incomplete for low amplitudes
(a few mmag), so the light-curve check in compsearch (Night.comp_check) stays necessary.

[comps] katalog_variable = true, vsx_radius_arcsec = 5.  Network as for Gaia: CDS, then the Harvard mirror, with
[gaia] timeout_s; result cached per run in vsx_field.csv (also taken over from another run of the same measurement).
"""
import glob
import os
import shutil

import numpy as np
from astropy.table import Table

from .gaia import CONNECT_S, VIZIER_SERVERS, settings

VSX_CAT = "B/vsx/vsx"
COLS = ("Name", "V", "RAJ2000", "DEJ2000", "Type", "max", "min", "Period")
NOT_VARIABLE = {2, 3}       # VSX V flag: 0 variable, 1 suspected, 2 constant or non-existing, 3 possible duplicate


def _query(ra, dec, radius_deg, timeout, server):
    from astroquery.vizier import Vizier
    import astropy.units as u
    from astropy.coordinates import SkyCoord
    v = Vizier(columns=list(COLS), row_limit=-1, timeout=(min(CONNECT_S, timeout), timeout), vizier_server=server)
    r = v.query_region(SkyCoord(ra, dec, unit="deg"), radius=radius_deg * u.deg, catalog=VSX_CAT)
    return r[0] if len(r) else Table(names=list(COLS), dtype=[str, int, float, float, str, float, float, float])


def vsx_field(m, ra, dec, radius_deg, log=None):
    """VSX entries in the field (cached in vsx_field.csv); None if no server answered (selection goes on without)."""
    cache = m.path("vsx_field.csv")
    if not os.path.exists(cache):
        old = sorted(glob.glob(os.path.join(os.path.dirname(m.out), "*", "vsx_field.csv")), key=os.path.getmtime, reverse=True)
        if old:
            shutil.copy2(old[0], cache)
            if log:
                log(f"  VSX-Feld aus Lauf {os.path.basename(os.path.dirname(old[0]))} uebernommen (keine Netzabfrage)")
    if os.path.exists(cache):
        return Table.read(cache, format="ascii.csv")
    _, timeout = settings(m.cfg)
    for h in VIZIER_SERVERS:
        if log:
            log(f"  VSX (veraenderliche Sterne): frage VizieR {h} an (Zeitlimit {timeout:g} s) ...")
        try:
            t = _query(float(ra), float(dec), float(radius_deg), timeout, h)
        except Exception as e:
            if log:
                log(f"  VSX ueber {h} nicht erreichbar ({type(e).__name__})")
            continue
        keep = [c for c in COLS if c in t.colnames]
        t = Table(t[keep])
        for c in t.colnames:                                    # plain columns for the CSV cache
            if hasattr(t[c], "filled"):
                t[c] = t[c].filled("" if t[c].dtype.kind in "US" else np.nan)
        t.write(cache, format="ascii.csv", overwrite=True)
        if log:
            log(f"  VSX: {len(t)} Eintraege im Feld")
        return t
    if log:
        log("  [WARN] VSX nicht erreichbar - Vergleichssterne nur mit dem Gaia-Flag auf bekannte Veraenderliche geprueft")
    return None


def _txt(x):
    s = "" if x is None or np.ma.is_masked(x) else str(x).strip()
    return "" if s in ("--", "nan") else s


def match(vsx, ra, dec, radius_arcsec):
    """Per star (ra, dec arrays, deg): reason text of the nearest real VSX variable within radius_arcsec, else ""."""
    out = [""] * len(ra)
    if vsx is None or not len(vsx):
        return out
    flag = np.array([int(float(_txt(v) or 0)) for v in vsx["V"]]) if "V" in vsx.colnames else np.zeros(len(vsx), int)
    ok = ~np.isin(flag, list(NOT_VARIABLE))
    if not ok.any():
        return out
    t = vsx[ok]; fl = flag[ok]
    vra, vde = np.array(t["RAJ2000"], float), np.array(t["DEJ2000"], float)
    for i, (r, d) in enumerate(zip(ra, dec)):
        sep = np.hypot((vra - r) * np.cos(np.radians(d)), vde - d) * 3600
        k = int(np.argmin(sep))
        if sep[k] > radius_arcsec:
            continue
        row = t[k]
        typ = _txt(row["Type"]) if "Type" in t.colnames else ""
        mx = _txt(row["max"]) if "max" in t.colnames else ""
        mn = _txt(row["min"]) if "min" in t.colnames else ""
        per = _txt(row["Period"]) if "Period" in t.colnames else ""
        info = ", ".join(x for x in (typ, f"{mx}-{mn} mag" if mx and mn else "", f"P {float(per):.4g} d" if per else "") if x)
        out[i] = f"VSX {'verdaechtig ' if fl[k] == 1 else ''}{_txt(row['Name'])}" + (f" ({info})" if info else "") + f", {sep[k]:.1f}\""
    return out
