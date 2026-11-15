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
            "the uploaded fluxes are corrected for it.") in t
    assert "Meridian flip during the transit" in t
    assert "Comparison ensemble used for the light curve (3 stars)" in t and len(t) <= k.MAXLEN_ALLES


def test_kommentar_max(tmp_path):
    lauf(tmp_path)
    t = k.make(str(tmp_path), {"export": {"kommentar_max": 480}})
    assert len(t) <= 480 and "more." in t


def test_flip_teilweise_im_ensemble(tmp_path):
    fr = lauf(tmp_path)
    (tmp_path / "compsearch.json").write_text(json.dumps(dict(flip=dict(t_flip_bjd=2461359.5787, n_stars=4,
                                                                        stars=[dict(name="G05"), dict(name="G99")]))))
    assert "measured on 4 field stars (incl. 1 of the 3 comparison stars)" in k.make(str(tmp_path), {})
