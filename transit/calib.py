"""Calibration masters from the library (read-only) and on-the-fly calibration.

Masters are searched recursively in [calib] library; only stacked masters are used (file name contains
MASTER or header has STACKCNT/NCOMBINE). Match: camera (INSTRUME), GAIN, OFFSET, binning, image size;
flat additionally FILTER, dark EXPTIME; the date closest to the night wins.
Siril stores float masters normalised to 0..1; those are scaled x65535 to ADU.
"""
import glob
import json
import os
from datetime import datetime

import numpy as np
from astropy.io import fits
from scipy.ndimage import median_filter

ADU = 65535.0


def _date(h):
    s = str(h.get("DATE-OBS", ""))[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        return None


def scan_library(lib):
    rows = []
    from . import xisf
    files = glob.glob(os.path.join(lib, "**", "*.fit*"), recursive=True) + glob.glob(os.path.join(lib, "**", "*.xisf"), recursive=True)
    for f in sorted(files):
        try:
            h = xisf.read_header(f) if xisf.is_xisf(f) else fits.getheader(f)
        except Exception:
            continue
        name = os.path.basename(f).upper()
        is_master = "MASTER" in name or "STACKCNT" in h or "NCOMBINE" in h or "MASTER" in str(h.get("IMAGETYP", "")).upper()
        typ = str(h.get("IMAGETYP", "")).upper()
        kind = "BIAS" if "BIAS" in typ or "OFFSET" in typ else "DARK" if "DARK" in typ else "FLAT" if "FLAT" in typ else None
        if kind is None:
            for k in ("BIAS", "DARK", "FLAT"):
                if k in name:
                    kind = k
        rows.append(dict(path=f, kind=kind, master=is_master, instr=str(h.get("INSTRUME", "")), gain=h.get("GAIN"),
                         offset=h.get("OFFSET"), xbin=h.get("XBINNING", 1), nx=h.get("NAXIS1"), ny=h.get("NAXIS2"),
                         filter=str(h.get("FILTER", "")), exptime=float(h.get("EXPTIME", h.get("EXPOSURE", 0)) or 0),
                         ccd_temp=h.get("CCD-TEMP"), date=_date(h), nstack=h.get("STACKCNT", h.get("NCOMBINE"))))
    return rows


def match(rows, light_h, night_date):
    def ok(r):
        return (r["master"] and r["kind"] and r["instr"] == str(light_h.get("INSTRUME", "")) and r["gain"] == light_h.get("GAIN")
                and r["offset"] == light_h.get("OFFSET") and r["nx"] == light_h.get("NAXIS1") and r["ny"] == light_h.get("NAXIS2"))
    cand = [r for r in rows if ok(r)]

    def best(lst):
        if not lst:
            return None
        return min(lst, key=lambda r: abs((r["date"] - night_date).days) if r["date"] else 1e9)
    filt = str(light_h.get("FILTER", ""))
    exp = float(light_h.get("EXPTIME", 0))
    bias = best([r for r in cand if r["kind"] == "BIAS"])
    flat = best([r for r in cand if r["kind"] == "FLAT" and r["filter"] == filt])
    darks = [r for r in cand if r["kind"] == "DARK"]
    dark = best([r for r in darks if abs(r["exptime"] - exp) < 0.5]) or best(darks)
    return dict(bias=bias, flat=flat, dark=dark)


def load_master(path):
    # memmap needs unscaled data; integer masters carry BZERO, so scale by hand
    from . import xisf
    if xisf.is_xisf(path):                                              # PixInsight/Siril master
        a = xisf.read_data(path)
    else:
        with fits.open(path, memmap=True, do_not_scale_image_data=True) as hl:
            hd = hl[0].header
            a = hl[0].data.astype(np.float32) * np.float32(hd.get("BSCALE", 1)) + np.float32(hd.get("BZERO", 0))
    if np.nanmedian(a[::50, ::50]) < 2.0:                               # Siril 0..1 normalisation
        a = a * np.float32(ADU)
    return a


class Calibrator:
    """mode raw | f (flat only: the masters' bias is subtracted from the flat, not from the lights,
    for lights taken with a different offset) | bf | bfd.  crop = (x0, y0): the lights are a
    sub-frame of the masters starting at this pixel (e.g. ASCOM driver 6216x4152 inside 6224x4168)."""

    def __init__(self, mode, masters, dark_scale=1.0, crop=(0, 0)):
        self.requested = mode
        self.mode, self.notes = effective_mode(mode, masters)   # missing masters: fall back, never stop
        mode = self.mode
        self.k = np.float32(dark_scale)
        self.crop = tuple(int(v) for v in crop)
        self._cut = False
        self.dc = None
        if mode == "raw":
            return
        self.bias = load_master(masters["bias"]["path"])
        if mode == "b":
            self.flat = None
            return
        flat = load_master(masters["flat"]["path"]) - self.bias
        self.flat = (flat / np.median(flat)).astype(np.float32)
        if mode == "bfd":
            # the scale factor k absorbs exposure-time and temperature differences
            self.dc = load_master(masters["dark"]["path"]) - self.bias

    def _fit_shape(self, shape):
        if self._cut:
            return
        # binned lights (e.g. 2x2) with unbinned masters: average the masters in b x b blocks.  For the normalised flat
        # mean and sum are identical; bias/dark are averaged (the camera's binning mode only scales them, ~9 ADU here).
        ref = self.bias if self.flat is None else self.flat
        b = ref.shape[0] // shape[0]
        if b > 1 and ref.shape == (shape[0] * b, shape[1] * b) and tuple(self.crop) == (0, 0):
            binm = lambda a: a.reshape(shape[0], b, shape[1], b).mean((1, 3)).astype(np.float32)
            if self.flat is not None:
                self.flat = binm(self.flat)
            self.bias = binm(self.bias)
            if self.dc is not None:
                self.dc = binm(self.dc)
            self.binned = b
        x0, y0 = self.crop
        sl = (slice(y0, y0 + shape[0]), slice(x0, x0 + shape[1]))
        if self.flat is not None:
            self.flat = self.flat[sl] / np.median(self.flat[sl])
        self.bias = self.bias[sl]
        if self.dc is not None:
            self.dc = self.dc[sl]
        if self.bias.shape != shape:
            raise SystemExit(f"Master {self.bias.shape} passt nicht zu Light {shape} mit crop {self.crop}")
        self._cut = True

    def __call__(self, data):
        if self.mode == "raw":
            return data
        self._fit_shape(data.shape)
        if self.mode == "f":
            return data / self.flat
        d = data - self.bias
        if self.dc is not None:
            d -= self.k * self.dc
        if self.flat is not None:
            d /= self.flat
        return d


def effective_mode(mode, masters):
    """Best calibration the found masters allow: bfd -> bf -> b (bias only) -> raw; f needs bias + flat too.
    Returns (mode, notes); a missing master never stops the run."""
    has = {k: bool(masters.get(k)) for k in ("bias", "flat", "dark")}
    want = mode
    if mode == "bfd" and not has["dark"]:
        mode = "bf"
    if mode in ("bf", "f") and not has["flat"]:
        mode = "b"
    if mode in ("b", "bf", "f", "bfd") and not has["bias"]:
        mode = "raw"
    notes = []
    if mode != want:
        miss = [k for k in ("bias", "flat", "dark") if not has[k] and (k != "dark" or want == "bfd")]
        notes.append(f"Kalibrierung {want} nicht moeglich ({', '.join(miss)} fehlt) - gerechnet mit {mode}")
    return mode, notes


def estimate_dark_scale(m, light_paths, masters, region=(slice(400, 1400), slice(4800, 5800)), every=8):
    """One factor per night from hot pixels: light excess = k * dark excess (5x5 median-filtered)."""
    from .frames import read_data
    bias = load_master(masters["bias"]["path"])[region]
    dc = load_master(masters["dark"]["path"])[region] - bias
    ed = dc - median_filter(dc, size=5)
    hot = ed > 10
    ks = []
    for p in light_paths[::every]:
        a = read_data(p)[region]
        el = (a - bias) - median_filter(a - bias, size=5)
        med = median_filter(a, size=5)
        ok = hot & (med < np.median(med) + 50)
        x, y = ed[ok], el[ok]
        msk = np.ones(x.size, bool)
        for _ in range(5):
            k = (x[msk] * y[msk]).sum() / (x[msk] ** 2).sum()
            r = y - k * x
            s = 1.4826 * np.median(np.abs(r[msk]))
            msk = np.abs(r) < 4 * s
        ks.append(float(k))
    return dict(k_night=float(np.median(ks)), k_min=min(ks), k_max=max(ks), n_hot=int(hot.sum()), per_frame=ks)
