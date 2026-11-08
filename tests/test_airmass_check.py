import numpy as np

from transit.checks import airmass_check


def test_kleine_abweichung_wird_nicht_gemeldet():
    calc = np.array([1.20, 1.25, 1.30])
    assert airmass_check(calc + np.array([-0.012, 0.0, -0.004]), calc, np.zeros(3, int)) is None


def test_grosse_abweichung_ohne_nan_bei_leerer_seite():
    calc = np.array([1.20, 1.25, 1.30])
    c = airmass_check(calc + 0.15, calc, np.zeros(3, int))
    assert c["level"] == "WARN"
    assert "nan" not in c["text"] and "West im Mittel +0.150" in c["text"] and "Ost" not in c["text"]


def test_beide_seiten_und_fehlender_header():
    calc = np.array([1.2, 1.3, 1.4, 1.5])
    hdr = np.array([1.2, np.nan, 1.6, 1.7])
    c = airmass_check(hdr, calc, np.array([0, 0, 1, 1]))
    assert "West im Mittel +0.000" in c["text"] and "Ost im Mittel +0.200" in c["text"]
    assert airmass_check(np.full(4, np.nan), calc, np.zeros(4, int)) is None
