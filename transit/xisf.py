"""Minimal reader for PixInsight XISF images (masters from PixInsight/Siril), standard library + numpy only.

Supports monolithic XISF 1.0 with one image, sample formats UInt8/16/32 and Float32/64, uncompressed or zlib
(optionally byte-shuffled).  lz4/zstd compression is not supported (save the master uncompressed or as FITS).
FITS keywords stored in the XISF header are returned as an astropy Header, so the masters can be matched like FITS.
"""
import re
import struct
import zlib
import xml.etree.ElementTree as ET

import numpy as np
from astropy.io import fits

DTYPES = {"UInt8": "u1", "UInt16": "<u2", "UInt32": "<u4", "Float32": "<f4", "Float64": "<f8"}


def _xml(path):
    with open(path, "rb") as fh:
        head = fh.read(16)
        if head[:8] != b"XISF0100":
            raise ValueError(f"{path}: keine XISF-Datei")
        n = struct.unpack("<I", head[8:12])[0]
        root = ET.fromstring(fh.read(n).decode("utf-8"))
    img = next(e for e in root.iter() if e.tag.endswith("Image"))
    return root, img


def is_xisf(path):
    return str(path).lower().endswith(".xisf")


def read_header(path):
    root, img = _xml(path)
    h = fits.Header()
    for e in img.iter():
        if not e.tag.endswith("FITSKeyword"):
            continue
        k, v = e.get("name", ""), e.get("value", "").strip()
        if not k or k in ("COMMENT", "HISTORY", "SIMPLE", "BITPIX", "NAXIS", "NAXIS1", "NAXIS2", "EXTEND"):
            continue
        if v.startswith("'"):
            val = v.strip("'").strip()
        else:
            try:
                val = int(v)
            except ValueError:
                try:
                    val = float(v)
                except ValueError:
                    val = {"T": True, "F": False}.get(v, v)
        try:
            h[k] = val
        except Exception:
            pass
    w, hgt = (int(x) for x in img.get("geometry").split(":")[:2])
    h["NAXIS1"], h["NAXIS2"] = w, hgt
    return h


def read_data(path):
    root, img = _xml(path)
    geo = [int(x) for x in img.get("geometry").split(":")]
    w, hgt, ch = geo[0], geo[1], (geo[2] if len(geo) > 2 else 1)
    dt = np.dtype(DTYPES[img.get("sampleFormat")])
    loc = img.get("location").split(":")
    if loc[0] != "attachment":
        raise ValueError(f"{path}: Datenblock '{loc[0]}' nicht unterstuetzt")
    pos, size = int(loc[1]), int(loc[2])
    with open(path, "rb") as fh:
        fh.seek(pos)
        raw = fh.read(size)
    comp = img.get("compression")
    if comp:
        codec = comp.split(":")[0]
        if codec.startswith("zlib"):
            raw = zlib.decompress(raw)
            if codec.endswith("+sh"):                     # byte shuffling: unshuffle by item size
                n = len(raw) // dt.itemsize
                raw = np.frombuffer(raw, "u1").reshape(dt.itemsize, n).T.tobytes()
        else:
            raise ValueError(f"{path}: Kompression '{codec}' nicht unterstuetzt (unkomprimiert oder als FITS speichern)")
    a = np.frombuffer(raw, dt, count=w * hgt * ch).reshape(ch, hgt, w)
    return a[0].astype(np.float32) if ch == 1 else a.astype(np.float32)
