"""Ephemeris: ExoClock (JSON, cached in the pipeline folder) with NASA Exoplanet Archive fallback."""
import json
import os
import time
import urllib.request

from .config import PIPE_DIR

CACHE = os.path.join(PIPE_DIR, "cache", "exoclock_planets.json")
URL = "https://www.exoclock.space/database/planets_json"


def exoclock_db(max_age_days=7):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    if not os.path.exists(CACHE) or time.time() - os.path.getmtime(CACHE) > max_age_days * 86400:
        try:
            with urllib.request.urlopen(URL, timeout=60) as r:
                data = r.read()
            with open(CACHE, "wb") as fh:
                fh.write(data)
        except Exception as e:                        # offline: keep using an old cache
            if not os.path.exists(CACHE):
                raise SystemExit(f"ExoClock nicht erreichbar und kein Cache: {e}")
    return json.load(open(CACHE))


def planet_params(name):
    db = exoclock_db()
    key = name if name in db else next((k for k in db if k.replace(" ", "").lower() == name.replace(" ", "").lower()), None)
    if key:
        p = db[key]
        return dict(source="ExoClock", name=key, T0=p["t0_bjd_tdb"], T0_err=p["t0_unc"], P=p["period_days"],
                    P_err=p["period_unc"], dur_h=p["duration_hours"], ars=p["sma_over_rs"], inc=p["inclination"],
                    rp=p["rp_over_rs"], depth_mmag=p.get("depth_r_mmag"), ra=p["ra_j2000"], dec=p["dec_j2000"])
    from astroquery.ipac.nexsci.nasa_exoplanet_archive import NasaExoplanetArchive
    nm = name[:-1].strip() + " " + name[-1] if not name.endswith(" b") else name
    r = NasaExoplanetArchive.query_criteria("pscomppars", where=f"pl_name='{nm}'")
    if len(r) == 0:
        raise SystemExit(f"Planet {name} weder bei ExoClock noch im NASA-Archiv gefunden")
    g = lambda k: float(r[k][0])
    return dict(source="NASA Exoplanet Archive", name=nm, T0=g("pl_tranmid"), T0_err=g("pl_tranmiderr1"), P=g("pl_orbper"),
                P_err=g("pl_orbpererr1"), dur_h=g("pl_trandur"), ars=g("pl_ratdor"), inc=g("pl_orbincl"), rp=g("pl_ratror"))


def predict(par, bjd_mid):
    import numpy as np
    n = round((bjd_mid - par["T0"]) / par["P"])
    tc = par["T0"] + n * par["P"]
    dur = par["dur_h"] / 24
    return dict(epoch=n, Tc=tc, Tc_err=float(np.hypot(par["T0_err"], n * par["P_err"])), ingress=tc - dur / 2,
                egress=tc + dur / 2, dur_d=dur, P=par["P"], source=par["source"])
