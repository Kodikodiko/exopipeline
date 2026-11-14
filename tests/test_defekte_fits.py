import os
import types

import numpy as np
from astropy.io import fits

from transit import frames


def _light(path, n=64):
    h = fits.Header()
    h["IMAGETYP"] = "LIGHT"
    h["DATE-OBS"] = "2026-11-13T20:31:54"
    fits.writeto(path, np.zeros((n, n), np.uint16), h)


def test_fits_problem_erkennt_leer_abgeschnitten_kaputt(tmp_path):
    ok, leer, cut, junk = (str(tmp_path / f) for f in ("ok.fits", "leer.fits", "cut.fits", "junk.fits"))
    _light(ok); _light(cut)
    open(leer, "wb").close()
    with open(cut, "r+b") as fh:
        fh.truncate(os.path.getsize(cut) // 2)
    with open(junk, "wb") as fh:
        fh.write(b"\0" * 5000)
    assert frames.fits_problem(ok) is None
    assert "leer" in frames.fits_problem(leer)
    assert "abgeschnitten" in frames.fits_problem(cut)
    assert frames.fits_problem(junk)


def test_read_headers_ueberspringt_defekte(tmp_path, capsys):
    for i in (1, 2, 3):
        _light(str(tmp_path / f"f_{i:04d}.fits"))
    open(tmp_path / "f_0002(1).fits", "wb").close()
    with open(tmp_path / "f_0003.fits", "r+b") as fh:
        fh.truncate(4000)
    m = types.SimpleNamespace(lights=str(tmp_path), root=str(tmp_path), solved_dir=str(tmp_path / "SOLVED"))
    skipped = []
    hd = frames.read_headers(m, skipped=skipped)
    assert [os.path.basename(x["file"]) for x in hd] == ["f_0001.fits", "f_0002.fits"]
    assert sorted(os.path.basename(f) for f, _ in skipped) == ["f_0002(1).fits", "f_0003.fits"]
    assert "defekte FITS-Datei uebersprungen" in capsys.readouterr().out
