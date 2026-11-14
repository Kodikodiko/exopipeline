import numpy as np

from transit.analysis import cloud_frames, time_ranges


def test_wolkenbank_und_einzelne_frames():
    f = np.full(200, 1000.0) * np.linspace(1.0, 0.8, 200)        # slow airmass trend: not a cloud
    f[50:75] *= 0.1                                                # cloud bank, 25 frames
    f[120] *= 0.4                                                  # single thick frame
    f[150] *= 0.8                                                  # thin haze: below threshold
    f[10] = np.nan
    tr, cl = cloud_frames(f, 0.5)
    assert set(np.where(cl)[0]) == set(range(50, 75)) | {120}
    assert np.isnan(tr[10]) and not cl[10]
    assert abs(tr[150] - 0.8) < 0.05


def test_schwelle_null_ist_aus():
    f = np.r_[np.ones(50), np.full(10, 0.01), np.ones(50)]
    assert not cloud_frames(f, 0)[1].any()


def test_zeitbereiche():
    jd = 2461358.0 + np.arange(20) / 1440              # one frame per minute from 12:00 UT
    m = np.zeros(20, bool); m[[2, 3, 4, 15]] = True
    assert time_ranges(jd, m) == [("12:02", "12:04", 3), ("12:15", "12:15", 1)]
