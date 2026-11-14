import json
import os
import types

import pytest

from transit import safety


def _m(tmp_path):
    lights = tmp_path / "LIGHT"; lights.mkdir()
    for n, data in (("a.fits", b"x" * 300000), ("b.fits", b"y" * 300000), ("leer.fits", b"")):
        (lights / n).write_bytes(data)
    return types.SimpleNamespace(lights=str(lights), result=str(tmp_path / "RESULT"))


def test_nach_defekt_verschoben_und_leere_geloescht_ok(tmp_path):
    m = _m(tmp_path)
    safety.record(m)
    (tmp_path / "LIGHT" / "_defekt").mkdir()
    os.replace(tmp_path / "LIGHT" / "b.fits", tmp_path / "LIGHT" / "_defekt" / "b.fits")
    os.remove(tmp_path / "LIGHT" / "leer.fits")
    r = safety.verify(m, "vorher")
    assert "2 defekte beiseitegelegt" in r
    assert set(json.load(open(safety.checksum_file(m)))) == {"a.fits"}
    assert safety.verify(m, "nachher").startswith("ok (1 Dateien)")


def test_fehlende_oder_veraenderte_datei_bleibt_fehler(tmp_path):
    m = _m(tmp_path)
    safety.record(m)
    os.remove(tmp_path / "LIGHT" / "a.fits")
    with pytest.raises(safety.ReadOnlyViolation, match="a.fits: fehlt"):
        safety.verify(m)
    (tmp_path / "LIGHT" / "_defekt").mkdir()
    (tmp_path / "LIGHT" / "_defekt" / "a.fits").write_bytes(b"z" * 300000)   # same size, other content
    with pytest.raises(safety.ReadOnlyViolation, match="a.fits: fehlt"):
        safety.verify(m)
