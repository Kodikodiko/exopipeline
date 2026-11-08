"""Planen: zuoberst steht immer die laufende oder kommende Nacht, nie eine schon vergangene."""
import os
import time
from datetime import date, datetime, timezone

import numpy as np
import pytest

pytest.importorskip("astropy")
from astropy.utils import iers

from transit import plan as P


@pytest.fixture(autouse=True)
def wien(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Vienna")
    time.tzset()
    iers.conf.auto_download = False
    monkeypatch.setattr(P, "exoclock_db", lambda: None)
    monkeypatch.setattr(P, "candidates", lambda db, prios: ([], np.array([])))
    yield
    monkeypatch.delenv("TZ")
    time.tzset()


def naechte(jetzt_utc, n=3):
    cfg = dict(site=dict(lat=48.2, lon=16.4, elev=200), camera=dict(pixel_um=3.76, focal_mm=1090),
               fit=dict(aperture_cm=15), photometry={}, comps=dict(dmag_bright=-1, dmag_faint=3), search={})
    res = P.plan(cfg, dict(P.DEFAULTS), n_nights=n, use_weather=False, log=lambda *a: None, now=jetzt_utc)
    return [date.fromisoformat(x["datum"]) for x in res["naechte"]]


def test_sonntag_vormittag_beginnt_mit_sonntagnacht():
    # So 08.11.2026 11:56 MEZ = 10:56 UTC: die Nacht Sa->So ist laengst vorbei
    assert naechte(datetime(2026, 11, 8, 10, 56, tzinfo=timezone.utc)) == [date(2026, 11, 8), date(2026, 11, 9), date(2026, 11, 10)]


def test_mitten_in_der_nacht_zaehlt_die_laufende_nacht():
    # So 08.11.2026 02:00 MEZ: die Nacht Sa->So laeuft noch
    assert naechte(datetime(2026, 11, 8, 1, 0, tzinfo=timezone.utc))[0] == date(2026, 11, 7)


def test_abends_die_heutige_nacht():
    assert naechte(datetime(2026, 11, 8, 19, 0, tzinfo=timezone.utc), n=1) == [date(2026, 11, 8)]
