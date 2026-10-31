"""transit plan - observing suggestions for the next nights.

ExoClock transits that are fully observable from the site ([site]) in astronomical darkness above the minimum altitude,
deep enough for the telescope (noise model: photons + sky + scintillation + floor), ranked by ExoClock priority,
expected precision, the cloud forecast (Open-Meteo, no key) and warnings (meridian flip, moon, airmass, baseline).
Writes plan\\plan.json (read by the GUI) and plan\\plan.csv; the site coordinates are not written there.
"""
import csv
import json
import math
import os
import time
import tomllib
import urllib.parse
import urllib.request
import warnings
from datetime import datetime, timedelta, timezone

import numpy as np

from .config import DEFAULT_TOML, PIPE_DIR
from .ephem import exoclock_db

PLAN_DIR = os.path.join(PIPE_DIR, "plan")
WX_CACHE = os.path.join(PIPE_DIR, "cache", "wetter.json")
GAIA_CACHE = os.path.join(PIPE_DIR, "cache", "plan_gaia.json")
GAIA_BUDGET_S = 180         # all Gaia queries of one plan together; afterwards only cached comparison-star counts
WX_URL = "https://api.open-meteo.com/v1/forecast"
WX_VARS = ("cloud_cover", "cloud_cover_low", "cloud_cover_mid", "cloud_cover_high", "precipitation_probability",
           "relative_humidity_2m", "wind_gusts_10m")
PRIO = {"alert": 1.0, "high": 0.85, "medium": 0.6, "low": 0.35}
ZP_E_S_CM2 = 1.0e6          # electrons/s/cm2 of a 0 mag star through a clear filter incl. optics and QE (rough, for ranking)
STEP_MIN = 5                # time grid of a night
WOCHENTAG = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
DEFAULTS = dict(naechte=3, alt_min=10.0, sonne_max=-12.0, mond_abstand_min=30.0, tiefe_snr_min=3.0, rauschboden_ppt=1.0,
                himmel_mag=20.0, tastgrad=0.8, exoclock_oeffnung=True, prioritaeten=["alert", "high", "medium", "low"],
                bewoelkung_gut=20, bewoelkung_max=60, wetter=True, sensor_px=[6248, 4176])


def load_cfg():
    with open(DEFAULT_TOML, "rb") as fh:
        cfg = tomllib.load(fh)
    pc = dict(DEFAULTS, **cfg.get("planning", {}))
    site = cfg.get("site", {})
    if site.get("lat") in (None, "") or site.get("lon") in (None, ""):
        raise SystemExit(f"Standort fehlt: [site] lat/lon in {os.path.basename(DEFAULT_TOML)} eintragen")
    return cfg, pc


# ------------------------------------------------------------------ instrument
def instrument(cfg, pc):
    cam = cfg["camera"]
    D = float(cfg["fit"].get("aperture_cm", 15.0))
    scale = cam["pixel_um"] / cam["focal_mm"] * 206.265                     # arcsec / px
    nx, ny = pc["sensor_px"]
    return dict(D_cm=D, D_inch=D / 2.54, scale=scale, fov_arcmin=(nx * scale / 60, ny * scale / 60),
                r_ap=cfg["photometry"].get("reference_radius", 16) * scale)


def noise_ppt(mag, X, inst, pc, elev):
    """Expected rms of a 10-min bin (ppt): photon + sky noise of the target, scintillation (Young 1967 x 1.5,
    Osborn et al. 2015), x1.3 for the comparison ensemble, plus a systematic floor."""
    D = inst["D_cm"]
    T = 600 * pc["tastgrad"]
    A = math.pi * (D / 2) ** 2
    S = ZP_E_S_CM2 * 10 ** (-0.4 * mag) * A * T
    B = ZP_E_S_CM2 * 10 ** (-0.4 * pc["himmel_mag"]) * math.pi * inst["r_ap"] ** 2 * A * T
    ph = math.sqrt(S + B) / S
    sc = 1.5 * 0.09 * D ** (-2 / 3) * X ** 1.75 * math.exp(-elev / 8000) / math.sqrt(2 * T)
    return math.sqrt(1.3 * (ph ** 2 + sc ** 2) * 1e6 + pc["rauschboden_ppt"] ** 2)


# ------------------------------------------------------------------ weather (Open-Meteo)
def weather(lat, lon, days, log=print):
    """Hourly forecast {var: {iso_hour_utc: value}}; cached for 1 h.  Coordinates rounded to 0.1 deg (~10 km)."""
    q = dict(latitude=round(lat, 1), longitude=round(lon, 1), hourly=",".join(WX_VARS), timezone="UTC",
             forecast_days=min(16, days))
    key = urllib.parse.urlencode(q)
    try:
        c = json.load(open(WX_CACHE, encoding="utf-8"))
        if c.get("key") == key and time.time() - c["t"] < 3600:
            return c["data"]
    except Exception:
        pass
    try:
        with urllib.request.urlopen(f"{WX_URL}?{key}", timeout=30) as r:
            h = json.load(r)["hourly"]
    except Exception as e:
        log(f"Wetter nicht abrufbar ({e}) - Vorschlag ohne Wetter")
        return None
    data = {v: dict(zip(h["time"], h[v])) for v in WX_VARS if v in h}
    os.makedirs(os.path.dirname(WX_CACHE), exist_ok=True)
    json.dump(dict(key=key, t=time.time(), data=data), open(WX_CACHE, "w", encoding="utf-8"))
    return data


def wx_window(wx, t0, t1):
    """Weather over [t0, t1] (datetimes, UTC): mean/max cloud cover, max rain probability, gusts, humidity."""
    if not wx:
        return None
    hrs, t = [], t0.replace(minute=0, second=0, microsecond=0)
    while t <= t1:
        hrs.append(t.strftime("%Y-%m-%dT%H:00"))
        t += timedelta(hours=1)
    get = lambda v: [x for x in (wx.get(v, {}).get(h) for h in hrs) if x is not None]
    cc = get("cloud_cover")
    if not cc:
        return None                                     # beyond the forecast
    mx = lambda v: max(get(v)) if get(v) else None
    return dict(wolken=float(np.mean(cc)), wolken_max=float(max(cc)), tief=mx("cloud_cover_low"), mittel=mx("cloud_cover_mid"),
                hoch=mx("cloud_cover_high"), regen=mx("precipitation_probability"), boeen=mx("wind_gusts_10m"),
                feuchte=mx("relative_humidity_2m"))


def ampel(w, pc):
    if w is None:
        return "?"
    return "gruen" if w["wolken"] <= pc["bewoelkung_gut"] else "gelb" if w["wolken"] <= pc["bewoelkung_max"] else "rot"


# ------------------------------------------------------------------ Gaia comparison stars
def comp_count(name, c, gmag, inst, cfg, log=print, net=True):
    """Gaia stars in the field (inscribed circle of the sensor) within the [comps] magnitude range of the target.
    net=False: cached value only (None if not cached)."""
    try:
        cache = json.load(open(GAIA_CACHE, encoding="utf-8"))
    except Exception:
        cache = {}
    cc = cfg["comps"]
    key = f"{name}|{gmag:.2f}|{cc['dmag_bright']}|{cc['dmag_faint']}|{min(inst['fov_arcmin']):.0f}"
    if key in cache or not net:
        return cache.get(key)
    from . import gaia
    try:
        r = min(inst["fov_arcmin"]) / 120
        g = gaia.cone(cfg, c.ra.deg, c.dec.deg, r, gmin=gmag + cc["dmag_bright"], gmax=gmag + cc["dmag_faint"])
        sep = np.hypot((np.array(g["ra"], float) - c.ra.deg) * math.cos(c.dec.rad), np.array(g["dec"], float) - c.dec.deg)
        n = int((sep * 3600 > 5).sum())
    except Exception as e:
        log(f"Gaia-Abfrage fuer {name} fehlgeschlagen: {e}")
        return None
    cache[key] = n
    os.makedirs(os.path.dirname(GAIA_CACHE), exist_ok=True)
    json.dump(cache, open(GAIA_CACHE, "w", encoding="utf-8"))
    return n


# ------------------------------------------------------------------ nights
def night_dates(n, now=None):
    """Local evening dates; before local noon the running night counts as the first."""
    loc = (now or datetime.now(timezone.utc)).astimezone()
    d0 = (loc - timedelta(hours=12)).date()
    return [d0 + timedelta(days=i) for i in range(n)]


def local_noon_utc(d):
    return datetime(d.year, d.month, d.day, 12).astimezone().astimezone(timezone.utc)


def hm(dt):
    return dt.astimezone().strftime("%H:%M")


def candidates(db, prios):
    """ExoClock planets with usable ephemeris, as arrays."""
    from astropy.coordinates import SkyCoord
    import astropy.units as u
    rows = []
    for k, p in db.items():
        try:
            if (p.get("priority") or "low") not in prios:
                continue
            mag = next((float(p[m]) for m in ("gaia_g_mag", "r_mag", "v_mag") if p.get(m) not in (None, "", 0)), None)
            rows.append(dict(name=k, star=p.get("star", k[:-1]), prio=p.get("priority") or "low", T0=float(p["t0_bjd_tdb"]),
                             T0_err=float(p.get("t0_unc") or 0), P=float(p["period_days"]), P_err=float(p.get("period_unc") or 0),
                             dur_h=float(p["duration_hours"]), depth_mmag=float(p.get("depth_r_mmag") or 0), mag=mag,
                             min_inch=float(p.get("min_telescope_inches") or 0), oc_min=p.get("current_oc_min"),
                             ra_s=p["ra_j2000"], dec_s=p["dec_j2000"]))
        except (KeyError, TypeError, ValueError):
            continue
    coords = SkyCoord([r["ra_s"] for r in rows], [r["dec_s"] for r in rows], unit=(u.hourangle, u.deg))
    return rows, coords


def plan(cfg, pc, n_nights=None, top=10, gaia_top=0, use_weather=None, log=print, now=None):
    from astropy.coordinates import AltAz, EarthLocation, get_body
    from astropy.time import Time
    from astropy.utils import iers
    import astropy.units as u
    iers.conf.iers_degraded_accuracy = "warn"              # future dates without fresh IERS-A: warn instead of fail
    warnings.filterwarnings("ignore", module="astropy")
    site = cfg["site"]
    lat, lon, elev = float(site["lat"]), float(site["lon"]), float(site.get("elev") or 0)
    loc = EarthLocation(lat=lat * u.deg, lon=lon * u.deg, height=elev * u.m)
    inst = instrument(cfg, pc)
    pl = cfg["planning"] if "planning" in cfg else {}
    base_h = float(pl.get("baseline_min_h", 1.0))
    flip_h = float(pl.get("flip_min_before_ingress_h", 1.0))
    am_max = float(pl.get("airmass_max_baseline", 2.0))
    n_nights = n_nights or int(pc["naechte"])
    use_weather = pc["wetter"] if use_weather is None else use_weather
    dates = night_dates(n_nights, now)
    days = (dates[-1] - datetime.now(timezone.utc).astimezone().date()).days + 2
    wx = weather(lat, lon, days, log) if use_weather else None
    rows, coords = candidates(exoclock_db(), set(pc["prioritaeten"]))
    log(f"{len(rows)} ExoClock-Planeten, Instrument {inst['D_cm']:.0f} cm, Feld {inst['fov_arcmin'][0]:.0f}'x{inst['fov_arcmin'][1]:.0f}', "
        f"Mindesthoehe {pc['alt_min']:.0f} Grad, Sonne < {pc['sonne_max']:.0f} Grad")
    T0 = np.array([r["T0"] for r in rows]); P = np.array([r["P"] for r in rows])
    out = []
    gaia = dict(ok=True, ende=time.time() + GAIA_BUDGET_S)
    for d in dates:
        t0 = local_noon_utc(d)
        grid = [t0 + timedelta(minutes=STEP_MIN * i) for i in range(24 * 60 // STEP_MIN + 1)]
        t = Time(grid)
        frame = AltAz(obstime=t, location=loc)
        sun_c, moon_c = get_body("sun", t, loc), get_body("moon", t, loc)
        sun = sun_c.transform_to(frame).alt.deg
        moon_alt = moon_c.transform_to(frame).alt.deg
        dark = sun < pc["sonne_max"]
        if not dark.any():
            out.append(dict(datum=d.isoformat(), dunkel=None, vorschlaege=[], hinweis="keine astronomische Dunkelheit"))
            continue
        i_a, i_b = int(np.argmax(dark)), len(dark) - 1 - int(np.argmax(dark[::-1]))
        illum = float(np.mean((1 - np.cos(sun_c.separation(moon_c).rad)) / 2))
        jd = t.utc.jd
        # transits whose mid-time falls in this night (BJD_TDB ~ JD_UTC + 69 s +- 8 min light time; refined below)
        lo, hi = jd[i_a] - 0.3, jd[i_b] + 0.3
        nmin, nmax = np.ceil((lo - T0) / P), np.floor((hi - T0) / P)
        idx = [i for i in range(len(rows)) if nmax[i] >= nmin[i]]
        cand = [(i, int(e)) for i in idx for e in range(int(nmin[i]), int(nmax[i]) + 1)]
        if not cand:
            out.append(dict(datum=d.isoformat(), vorschlaege=[]))
            continue
        ci = np.array([c[0] for c in cand]); ep = np.array([c[1] for c in cand])
        tc_bjd = T0[ci] + ep * P[ci]
        cc = coords[ci]
        tt = Time(tc_bjd, format="jd", scale="tdb")
        tc_utc = (tt - tt.light_travel_time(cc, "barycentric", location=loc)).utc.jd
        alt = cc[:, None].transform_to(AltAz(obstime=t[None, :], location=loc)).alt.deg     # (cand, grid)
        lst = t.sidereal_time("apparent", longitude=lon * u.deg).hour
        ha = (lst[None, :] - cc.ra.hour[:, None] + 12) % 24 - 12
        msep = cc[:, None].separation(moon_c[None, :]).deg
        night_wx = wx_window(wx, grid[i_a], grid[i_b])
        sug = []
        for k, (i, e) in enumerate(cand):
            r = rows[i]
            dur = r["dur_h"] / 24
            tc_err = math.hypot(r["T0_err"], e * r["P_err"])
            buf = 3 * tc_err
            ing, egr = tc_utc[k] - dur / 2 - buf, tc_utc[k] + dur / 2 + buf
            ok = dark & (alt[k] >= pc["alt_min"])
            tr = (jd >= ing - STEP_MIN / 2880) & (jd <= egr + STEP_MIN / 2880)
            if not tr.any() or not ok[tr].all():
                continue
            k_in, k_eg = int(np.argmax(tr)), len(tr) - 1 - int(np.argmax(tr[::-1]))
            j = k_in
            while j > 0 and ok[j - 1]:
                j -= 1
            pre_h = max(0.0, (ing - jd[j]) * 24)
            j = k_eg
            while j < len(ok) - 1 and ok[j + 1]:
                j += 1
            post_h = max(0.0, (jd[j] - egr) * 24)
            if min(pre_h, post_h) < base_h / 2:
                continue
            start, end = ing - min(pre_h, base_h) / 24, egr + min(post_h, base_h) / 24
            win = (jd >= start) & (jd <= end)
            X = 1 / np.sin(np.radians(np.clip(alt[k][win], 1, 90)))
            mag = r["mag"]
            depth_ppt = (1 - 10 ** (-0.4 * r["depth_mmag"] / 1000)) * 1000
            sig = noise_ppt(mag, float(np.median(X)), inst, pc, elev) if mag else None
            snr = depth_ppt / sig if sig else None
            if snr is not None and snr < pc["tiefe_snr_min"]:
                continue
            if pc["exoclock_oeffnung"] and r["min_inch"] > inst["D_inch"] + 1e-6:
                continue
            warn, fac = [], 1.0
            fz = (jd >= ing - flip_h / 24) & (jd <= egr + 0.25 / 24)
            if fz.sum() > 1 and np.sign(ha[k][fz]).min() < 0 < np.sign(ha[k][fz]).max():
                tf = jd[fz][np.argmax(ha[k][fz] >= 0)]
                warn.append(f"Meridian-Flip {hm(Time(tf, format='jd').to_datetime(timezone.utc))} im/nahe am Transit")
                fac *= 0.75
            if pre_h < base_h or post_h < base_h:
                warn.append(f"Baseline nur {min(pre_h, base_h) * 60:.0f}/{min(post_h, base_h) * 60:.0f} min")
                fac *= 0.7
            if X.max() > am_max:
                warn.append(f"Airmass bis {X.max():.1f}")
                fac *= 0.8
            mwin = win & (moon_alt > 0)
            msep_min = float(msep[k][mwin].min()) if mwin.any() else None
            if msep_min is not None and msep_min < pc["mond_abstand_min"] and illum > 0.3:
                warn.append(f"Mond {msep_min:.0f} Grad entfernt")
                fac *= 0.85
            if mag and mag < 9:
                warn.append("hell: kurz belichten oder leicht defokussieren")
            dt_start = Time(start, format="jd").to_datetime(timezone.utc)
            dt_end = Time(end, format="jd").to_datetime(timezone.utc)
            w = wx_window(wx, dt_start, dt_end)
            if w and (w["regen"] or 0) >= 50:
                warn.append(f"Regenrisiko {w['regen']:.0f} %")
            if w and (w["feuchte"] or 0) >= 90:
                warn.append("Taugefahr (Feuchte >= 90 %)")
            if w and (w["boeen"] or 0) >= 40:
                warn.append(f"Boeen bis {w['boeen']:.0f} km/h")
            q = min(1.0, (snr or pc["tiefe_snr_min"]) / (3 * pc["tiefe_snr_min"]))
            wf = 1 - w["wolken"] / 100 if w else 1.0
            score = 100 * PRIO.get(r["prio"], 0.35) * (0.5 + 0.5 * q) * fac * wf
            iso = lambda x: Time(x, format="jd").to_datetime(timezone.utc).isoformat(timespec="minutes")
            kk = np.arange(max(0, i_a - 6), min(len(grid), i_b + 7), 2)          # 10-min curve for the GUI
            sug.append(dict(planet=r["name"], stern=r["star"], prio=r["prio"], mag=mag, tiefe_ppt=round(depth_ppt, 2),
                            rauschen_ppt=round(sig, 2) if sig else None, snr=round(snr, 1) if snr else None,
                            dauer_h=r["dur_h"], tc=iso(tc_utc[k]), tc_err_min=round(tc_err * 1440, 1),
                            ingress=iso(tc_utc[k] - dur / 2), egress=iso(tc_utc[k] + dur / 2), start=iso(start), ende=iso(end),
                            baseline_h=[round(min(pre_h, base_h), 2), round(min(post_h, base_h), 2)],
                            airmass_max=round(float(X.max()), 2), hoehe_max=round(float(alt[k][win].max()), 1),
                            mond_abstand=round(msep_min, 0) if msep_min is not None else None, wetter=w, ampel=ampel(w, pc),
                            min_oeffnung_inch=r["min_inch"], oc_min=r["oc_min"], warnungen=warn, score=round(score, 1),
                            ra=cc[k].ra.to_string(u.hour, sep=":", precision=1), dec=cc[k].dec.to_string(u.deg, sep=":", precision=0, alwayssign=True),
                            kurve=dict(t0=grid[kk[0]].isoformat(timespec="minutes"), schritt_min=STEP_MIN * 2,
                                       hoehe=[round(float(a), 1) for a in alt[k][kk]])))
        sug.sort(key=lambda s: -s["score"])
        if gaia_top:
            for s in sug[:gaia_top]:
                if gaia["ok"] and time.time() > gaia["ende"]:
                    log(f"Gaia antwortet zu langsam (> {GAIA_BUDGET_S} s): weitere Vergleichssterne nur aus dem Cache")
                    gaia["ok"] = False
                c = coords[[r["name"] for r in rows].index(s["planet"])]
                n = comp_count(s["stern"], c, s["mag"] or 12, inst, cfg, log, net=gaia["ok"])
                if n is None and gaia["ok"]:
                    log("Gaia nicht erreichbar: weitere Vergleichssterne nur aus dem Cache")
                    gaia["ok"] = False
                s["vergleichssterne"] = n
                if n is not None and n < cfg["search"].get("n_min", 3):
                    s["warnungen"].append(f"nur {n} Vergleichssterne im Feld")
                    s["score"] = round(s["score"] * 0.6, 1)
            sug.sort(key=lambda s: -s["score"])
        kk = np.arange(max(0, i_a - 6), min(len(grid), i_b + 7), 2)
        out.append(dict(datum=d.isoformat(), dunkel=[grid[i_a].isoformat(timespec="minutes"), grid[i_b].isoformat(timespec="minutes")],
                        mond_beleuchtung=round(illum * 100), wetter=night_wx, ampel=ampel(night_wx, pc), anzahl=len(sug),
                        vorschlaege=sug[:top], sonne=dict(t0=grid[kk[0]].isoformat(timespec="minutes"), schritt_min=STEP_MIN * 2,
                                                          hoehe=[round(float(a), 1) for a in sun[kk]]),
                        mond=[round(float(a), 1) for a in moon_alt[kk]]))
    return dict(erstellt=datetime.now(timezone.utc).isoformat(timespec="minutes"),
                instrument=dict(oeffnung_cm=inst["D_cm"], feld_arcmin=[round(x, 1) for x in inst["fov_arcmin"]],
                                skala=round(inst["scale"], 3)),
                parameter=dict(alt_min=pc["alt_min"], sonne_max=pc["sonne_max"], tiefe_snr_min=pc["tiefe_snr_min"],
                               baseline_min_h=base_h, wetter=bool(wx)), naechte=out)


# ------------------------------------------------------------------ output
def write(res):
    os.makedirs(PLAN_DIR, exist_ok=True)
    jp = os.path.join(PLAN_DIR, "plan.json")
    json.dump(res, open(jp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    cols = ("datum", "score", "planet", "prio", "mag", "tiefe_ppt", "snr", "start", "ingress", "tc", "egress", "ende",
            "airmass_max", "ampel", "wolken", "warnungen", "ra", "dec")
    with open(os.path.join(PLAN_DIR, "plan.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(cols)
        for n in res["naechte"]:
            for s in n["vorschlaege"]:
                w.writerow([n["datum"], s["score"], s["planet"], s["prio"], s["mag"], s["tiefe_ppt"], s["snr"], s["start"],
                            s["ingress"], s["tc"], s["egress"], s["ende"], s["airmass_max"], s["ampel"],
                            round(s["wetter"]["wolken"]) if s["wetter"] else "", " | ".join(s["warnungen"]), s["ra"], s["dec"]])
    return jp


def show(res):
    loc = lambda s: datetime.fromisoformat(s).astimezone().strftime("%H:%M")
    for n in res["naechte"]:
        d = datetime.fromisoformat(n["datum"])
        head = f"\nNacht {WOCHENTAG[d.weekday()]} {d:%d.%m.} -> {d + timedelta(days=1):%d.%m.}"
        if not n.get("dunkel"):
            print(head + ": " + n.get("hinweis", "nichts")); continue
        w = n.get("wetter")
        print(head + f": dunkel {loc(n['dunkel'][0])}-{loc(n['dunkel'][1])}, Mond {n['mond_beleuchtung']} %, "
              + (f"Bewoelkung im Mittel {w['wolken']:.0f} % ({n['ampel']})" if w else "Wetter: keine Vorhersage")
              + f", {n['anzahl']} beobachtbare Transits")
        if not n["vorschlaege"]:
            continue
        print(f"  {'Score':>5s} {'Planet':13s} {'Prio':6s} {'mag':>5s} {'Tiefe':>6s} {'SNR':>5s}  {'Beobachten':11s} "
              f"{'Ingr.':5s} {'Tc':5s} {'Egr.':5s} {'X max':>5s} {'Wolken':>6s}  Hinweise")
        for s in n["vorschlaege"]:
            print(f"  {s['score']:5.0f} {s['planet']:13s} {s['prio']:6s} {s['mag'] or 0:5.1f} {s['tiefe_ppt']:6.1f} "
                  f"{s['snr'] or 0:5.1f}  {loc(s['start'])}-{loc(s['ende'])} {loc(s['ingress'])} {loc(s['tc'])} {loc(s['egress'])} "
                  f"{s['airmass_max']:5.2f} {(str(round(s['wetter']['wolken'])) + ' %') if s['wetter'] else '?':>6s}  "
                  + "; ".join(s["warnungen"] + ([f"{s['vergleichssterne']} Vgl.-Sterne"] if s.get("vergleichssterne") is not None else [])))
    print("\nZeiten lokal. Tiefe in ppt, SNR = Tiefe / Rauschen eines 10-min-Bins (Schaetzung). Beobachten = mit Baseline.")


def cmd_plan(a):
    cfg, pc = load_cfg()
    if a.prioritaet:
        pc["prioritaeten"] = a.prioritaet
    res = plan(cfg, pc, n_nights=a.naechte, top=a.top, gaia_top=a.vergleich, use_weather=False if a.ohne_wetter else None)
    p = write(res)
    show(res)
    print(f"Gespeichert: {p} (+ plan.csv)")
