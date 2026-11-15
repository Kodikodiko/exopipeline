"""ExoClock comment: flip sentence with numbers, comparison-star list with a legend, length limit."""
import csv
import json

from transit import kommentar as k

TG = dict(name="T", role="target", source_id="111", G="8.6", bp_rp="0.67", ra="92.6639", dec="30.9571")
STARS = [("G05", "3438063011972005120", "10.0", "0.63", 92.70, 31.05),
         ("G07", "3438035695980005248", "10.2", "1.06", 92.55, 30.80),
         ("G08", "3438057308255433728", "10.3", "1.05", 92.30, 30.70)]
PRED = dict(Tc=2461359.5358, ingress=2461359.43, egress=2461359.64)


def lauf(tmp_path, flip=True):
    with open(tmp_path / "candidates.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(TG))
        w.writeheader(); w.writerow(TG)
        for n, sid, g, c, ra, de in STARS:
            w.writerow(dict(name=n, role="comp", source_id=sid, G=g, bp_rp=c, ra=ra, dec=de))
    fr = dict(best=dict(comps=[s[0] for s in STARS], gaia=[s[1] for s in STARS]),
              info=dict(flip_mode="prior" if flip else "none"), ephemeris=PRED,
              mcmc=dict(Tc=[PRED["Tc"] - 0.003, PRED["Tc"], PRED["Tc"] + 0.003]),
              tests=dict(alle_fest=dict(flip_ppt=1.853)), flip_target=[0.0026, 0.0032])
    (tmp_path / "fit.json").write_text(json.dumps(fr))
    (tmp_path / "compsearch.json").write_text(json.dumps(dict(flip=dict(
        t_flip_bjd=2461359.5787, n_stars=9, stars=[dict(name=f"G{i:02d}") for i in range(3, 12)]))))
    with open(tmp_path / "headers.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["DATE-OBS", "PIERSIDE", "EXPTIME", "FILTER"])
        w.writeheader()
        for i in range(30):                                          # 2 min cadence, flip after frame 15
            w.writerow({"DATE-OBS": f"2026-11-15T0{1 + i // 30}:{(i * 2) % 60:02d}:00", "PIERSIDE": "pierEast" if i < 15 else "pierWest",
                        "EXPTIME": "10", "FILTER": "L"})
    return fr


def test_sternliste_mit_legende(tmp_path):
    fr = lauf(tmp_path)
    t = k.ensemble_text(str(tmp_path), fr, 1000)
    assert t.startswith("Target G 8.6, BP-RP 0.67. Comparison ensemble used for the light curve (3 stars), Gaia DR3 ID (G mag / BP-RP / separation from target): ")
    assert "3438063011972005120 (10.0 / 0.63 / " in t and t.endswith("').")
    assert t.count(" (") == 2 + len(STARS)                            # count, legend, one bracket per star


def test_sternliste_kuerzt_mit_more(tmp_path):
    fr = lauf(tmp_path)
    full = k.ensemble_text(str(tmp_path), fr, 1000)
    t = k.ensemble_text(str(tmp_path), fr, len(full) - 5)
    assert t.endswith("; +1 more.") and len(t) <= len(full) - 5
    assert k.ensemble_text(str(tmp_path), fr, 20) == ""


def test_flipsatz_mit_zahlen(tmp_path):
    fr = lauf(tmp_path)
    t = k.make(str(tmp_path), {})
    assert ("Flux step across the flip: +1.9 ppt, fitted with a prior (+2.6 +/- 3.2 ppt) measured on 9 field stars (incl. the comparison stars); "
            "the uploaded fluxes are corrected for it, otherwise not detrended.") in t
    assert "Meridian flip during the transit" in t
    assert "Comparison ensemble used for the light curve (3 stars)" in t and len(t) <= k.MAXLEN_ALLES


def test_kommentar_max(tmp_path):
    lauf(tmp_path)
    t = k.make(str(tmp_path), {"export": {"kommentar_max": 480}})
    assert len(t) <= 480 and "Comparison ensemble" in t


def test_flip_teilweise_im_ensemble(tmp_path):
    fr = lauf(tmp_path)
    (tmp_path / "compsearch.json").write_text(json.dumps(dict(flip=dict(t_flip_bjd=2461359.5787, n_stars=4,
                                                                        stars=[dict(name="G05"), dict(name="G99")]))))
    assert "measured on 4 field stars (incl. 1 of the 3 comparison stars)" in k.make(str(tmp_path), {})


def _status(n=300, used=None, why=None, east=None):
    import numpy as np
    jd = 2461359.375 + np.arange(n) / 1440                      # one frame per minute from 21:00 UT
    used = np.ones(n, bool) if used is None else used
    w = np.array([""] * n, dtype=object) if why is None else why
    return dict(jd=jd, bjd=jd + 0.005, used=used, why=w, east=east)


PR = dict(ingress=2461359.375 + 60 / 1440 + 0.005, egress=2461359.375 + 240 / 1440 + 0.005, Tc=2461359.375 + 150 / 1440 + 0.005)


def test_abdeckung_ohne_luecke():
    zeilen = k.coverage_text(_status(), PR)
    assert zeilen[0] == ("Coverage 21:00-01:59 UT (predicted ingress 22:00, egress 01:00 UT): Ingress and egress observed; "
                         "baseline 60 min before ingress and 59 min after egress.")
    assert zeilen[1] == "No gaps in the uploaded data."


def test_luecke_mit_ursache_lage_und_flip():
    import numpy as np
    st = _status()
    st["used"][160:230] = False
    st["why"][160:230] = "sat"
    st["used"][[180, 200]] = True; st["why"][[180, 200]] = ""     # two isolated points survive
    st["east"] = np.r_[np.zeros(190), np.ones(110)]
    z = k.coverage_text(st, PR)
    assert z[0].endswith("Ingress and egress observed; baseline 60 min before ingress and 59 min after egress.")
    assert z[1].startswith("Gap in the uploaded data: 23:39-00:50 UT (71 min, in transit, +9 to +80 min from mid-transit; "
                           "only 2 scattered points left): target or a comparison star saturated in 68 frames, meridian flip")


def test_egress_in_der_luecke():
    st = _status()
    st["used"][230:260] = False
    st["why"][230:260] = "cloud"
    z = k.coverage_text(st, PR)
    assert "Ingress observed, egress not covered" in z[0]
    assert "(31 min, across egress): clouds in 30 frames" in z[1]


def test_bilder_und_kalibrierung():
    st = _status(10)
    st["used"][:3] = False; st["why"][:3] = "sat"
    t = k.frames_text(st, [{"EXPTIME": "10"}], {"defekt": ["a.fits"]})
    assert t == "10 frames of 10 s (cadence 60 s), 7 used (removed: 3 saturated; 1 unreadable file skipped)."
    cj = {"mode": "bfd", "flat": {"date": "2026-01-01"}}
    assert k.calib_text(cj, [{"DATE-OBS": "2026-11-14T21:00:00"}]) == "Calibration: bias, dark and flat field; flat 317 days older than the data."


def test_frame_status_aus_cube_und_export(tmp_path):
    import numpy as np
    n = 40
    jd = 2461359.5 + np.arange(n) / 1440
    pk = np.full((n, 3), 30000.0); pk[10:20, 0] = 65535
    np.savez(tmp_path / "cube_f.npz", jd_start=jd, jd_utc_mid=jd, bjd_tdb=jd + 0.005, peak_raw=pk,
             flux=np.ones((n, 3, 2)), radii=np.array([12, 16]), star_name=np.array(["T", "G01", "G02"]),
             frame_file=np.array([f"f{i}.fits" for i in range(n)]))
    fr = dict(info=dict(dropped_saturating=["G02"]))
    st = k.frame_status(str(tmp_path), fr, {"camera": {"saturation_adu": 60000}, "search": {"exclude_frames": ["f3.fits"]}})
    assert list(st["why"][[3, 10, 19, 20]]) == ["list", "sat", "sat", ""] and st["used"].sum() == 29
    np.savetxt(tmp_path / "X_exoclock_JDUTC.txt", np.c_[jd[25:], np.ones(15)], header="Planet")
    st = k.frame_status(str(tmp_path), fr, {"camera": {"saturation_adu": 60000}})
    assert st["used"].sum() == 15 and st["why"][22] == "other" and st["why"][12] == "sat"
