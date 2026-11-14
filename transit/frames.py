"""Frame list, header info, times (BJD_TDB via astropy) and airmass from the true coordinates."""
import os
import warnings
import numpy as np
from astropy.io import fits
from astropy.time import Time
from astropy.coordinates import SkyCoord, EarthLocation, AltAz
from astropy.wcs import FITSFixedWarning
import astropy.units as u

from .safety import light_files

warnings.simplefilter("ignore", FITSFixedWarning)
KEYS = ["DATE-OBS", "DATE-AVG", "EXPTIME", "FILTER", "IMAGETYP", "NAXIS1", "NAXIS2", "XBINNING", "GAIN", "OFFSET",
        "CCD-TEMP", "SET-TEMP", "PIERSIDE", "OBJECT", "OBJCTRA", "OBJCTDEC", "SITELAT", "SITELONG", "SITEELEV",
        "AIRMASS", "INSTRUME", "TELESCOP", "PLTSOLVD", "CTYPE1"]


_WARNED = set()        # defective lights already reported in this process (read_headers runs in several steps)


def fits_problem(path, h=None):
    """Why a FITS file cannot be used (empty, header unreadable, data cut off), or None if it looks complete.
    Truncated files (e.g. NINA stopped writing) keep a valid header, so the file size is checked against the
    size the header announces."""
    try:
        size = os.path.getsize(path)
    except OSError as e:
        return f"nicht lesbar ({e})"
    if size == 0:
        return "leer (0 Bytes)"
    if h is None:
        try:
            h = fits.getheader(path)
        except Exception as e:
            return f"Header defekt ({type(e).__name__}: {e})"
    try:
        nax = int(h.get("NAXIS", 0))
        npix = int(np.prod([int(h.get(f"NAXIS{i}", 0)) for i in range(1, nax + 1)])) if nax else 0
        need = npix * abs(int(h.get("BITPIX", 16))) // 8
    except (TypeError, ValueError):
        return None
    if need:
        with open(path, "rb") as fh:                         # header length: up to the END card, in 2880-byte blocks
            hlen = 0
            while True:
                blk = fh.read(2880)
                if len(blk) < 2880:
                    return "Header unvollstaendig"
                hlen += 2880
                if any(blk[i:i + 8] == b"END     " for i in range(0, 2880, 80)):
                    break
        if size < hlen + need:
            return (f"abgeschnitten ({size / 1e6:.1f} von {(hlen + need) / 1e6:.1f} MB, "
                    f"{100 * (size - hlen) / need:.0f} % der Bilddaten)")
    return None


def _warn(msg):
    try:
        from .cli import log
    except Exception:
        log = print
    log(msg)


def read_headers(m, solved_dir=None, skipped=None):
    """Headers of all lights; a solved copy in SOLVED\\ (same file name) takes precedence for the WCS.
    Empty, unreadable or truncated FITS files are skipped with a warning (appended to `skipped` as (file, reason))."""
    out = []
    solved_dir = solved_dir or getattr(m, "solved_dir", os.path.join(m.root, "SOLVED"))
    for f in light_files(m):
        try:
            h = fits.getheader(f)
        except Exception:
            h = None
        why = fits_problem(f, h)
        if why:
            if skipped is not None:
                skipped.append((f, why))
            if f not in _WARNED:
                _WARNED.add(f)
                _warn(f"WARNUNG: defekte FITS-Datei uebersprungen: {os.path.basename(f)} - {why}")
            continue
        typ = str(h.get("IMAGETYP", "LIGHT")).upper()
        if any(w in typ for w in ("BIAS", "DARK", "FLAT", "OFFSET", "MASTER")):   # masters lying among the lights
            continue
        alt = os.path.join(solved_dir, os.path.basename(f))
        src = f
        if not ("CTYPE1" in h and h.get("PLTSOLVD", True)) and os.path.exists(alt):
            h2 = fits.getheader(alt)
            if "CTYPE1" in h2:
                h, src = h2, alt
        out.append(dict(file=f, src=src, header=h, size=os.path.getsize(f),
                        solved=("CTYPE1" in h) and bool(h.get("PLTSOLVD", True))))
    return out


def site(m, h):
    s = m.cfg.get("site", {})
    lat = s.get("lat") or h.get("SITELAT"); lon = s.get("lon") or h.get("SITELONG"); el = s.get("elev") or h.get("SITEELEV", 0)
    return EarthLocation(lon=float(lon) * u.deg, lat=float(lat) * u.deg, height=float(el) * u.m)


def target_coord(m, h=None):
    t = m.cfg.get("target", {})
    if "ra" in t and "dec" in t:
        return SkyCoord(float(t["ra"]), float(t["dec"]), unit="deg")
    if h is not None and "OBJCTRA" in h:
        return SkyCoord(h["OBJCTRA"], h["OBJCTDEC"], unit=(u.hourangle, u.deg))
    raise SystemExit("Zielkoordinaten fehlen: [target] ra/dec in RESULT\\transit.toml setzen")


def times(m, headers):
    """dict with jd_start, jd_mid (UTC), bjd_tdb (mid), airmass_calc, altitude, east flag."""
    h0 = headers[0]["header"]
    loc = site(m, h0)
    tgt = target_coord(m, h0)
    start = Time([x["header"]["DATE-OBS"] for x in headers], scale="utc", location=loc)
    exp = np.array([float(x["header"].get("EXPTIME", x["header"].get("EXPOSURE", 0))) for x in headers])
    if all("DATE-AVG" in x["header"] for x in headers):
        mid = Time([x["header"]["DATE-AVG"] for x in headers], scale="utc", location=loc)
    else:
        mid = start + exp / 2 * u.s
    bjd = (mid.tdb + mid.light_travel_time(tgt, "barycentric")).jd
    aa = tgt.transform_to(AltAz(obstime=mid, location=loc))
    return dict(jd_start=start.jd, jd_mid=mid.jd, bjd_tdb=bjd, airmass_calc=np.asarray(aa.secz.value),
                alt_deg=np.asarray(aa.alt.deg), exptime=exp,
                east=np.array([str(x["header"].get("PIERSIDE", "")).lower().startswith("e") for x in headers], float),
                airmass_header=np.array([float(x["header"].get("AIRMASS", np.nan)) for x in headers]))


def read_data(path):
    """Pixel data as float32 ADU; memmap with manual BZERO/BSCALE (astropy cannot memmap scaled data)."""
    with fits.open(path, memmap=True, do_not_scale_image_data=True) as hl:
        hd = hl[0].header
        return hl[0].data.astype(np.float32) * np.float32(hd.get("BSCALE", 1)) + np.float32(hd.get("BZERO", 0))
