"""Exports: ExoClock upload file (+ form values), detrended light curve, AIJ radec file."""
import os

import numpy as np
from astropy.time import Time

# exactly the entries of the ExoClock upload menu (checked 2026-10-24)
FILTER_EXOCLOCK = {"L": "Luminance (B to R)", "LUM": "Luminance (B to R)", "LUMINANCE": "Luminance (B to R)",
                   "CLEAR": "Clear (UV to IR)", "C": "Clear (UV to IR)", "NONE": "Clear (UV to IR)",
                   "U": "U (Johnson)", "B": "B (Johnson)", "V": "V (Johnson)", "R": "R (Cousins)", "I": "I (Cousins)",
                   "H": "H (2MASS)", "J": "J (2MASS)", "KS": "Ks (2MASS)",
                   "U'": "u' (SDSS)", "G'": "g' (SDSS)", "R'": "r' (SDSS)", "I'": "i' (SDSS)", "Z'": "z' (SDSS)",
                   "SG": "g' (SDSS)", "SR": "r' (SDSS)", "SI": "i' (SDSS)",
                   "EXO": "Astrodon ExoPlanet-BB (V to IR)", "EXOPLANET": "Astrodon ExoPlanet-BB (V to IR)"}


def aperture_en(c, r, sel):
    from .apertur import is_variable, px
    if not is_variable(r):
        return f"r={r}px"
    _, lo, hi = px(c, r, sel)
    return f"growing aperture {c['vap'][r]['k']:g}xFWHM (r {lo:.1f}-{hi:.1f}px, same radius for all stars per frame)"


def hms(ra):
    h = ra / 15
    return f"{int(h):02d}:{int(h * 60 % 60):02d}:{h * 3600 % 60:06.3f}"


def dms(de):
    s = "+" if de >= 0 else "-"; a = abs(de)
    return f"{s}{int(a):02d}:{int(a * 60 % 60):02d}:{a * 3600 % 60:05.2f}"


def export_all(m, n, c, fitres, inv, log):
    best = fitres["best"]
    r = best["radius"]
    ir = n.ir(r)
    idx = {nm: i for i, nm in enumerate(n.names)}
    ens = [idx[s] for s in best["comps"]]
    fb = n.fit(r, ens)
    sel = n.sel
    jd0 = c["jd_start"][sel]
    rel = n.rel(ir, ens)
    erel = n.rel_err(ir, ens)
    scale = float(np.std(fb["res"]) / np.median(erel / fb["base"]))
    if n.weights != "none":                                # per-frame noise model: error = scale x model shape
        erel = fb["s"] * fb["base"] * np.median(erel / fb["base"])
    flip = fb["flip_ppt"] * 1e-3
    east = n.east
    flipcorr = rel / (1 + flip * east)
    det = fb["f"] / fb["base"]
    planet = inv["planet"]["name"]
    filt = m.cfg.get("export", {}).get("filter") or (inv["filters"][0] if inv["filters"] else "")   # header may lack FILTER
    fex = FILTER_EXOCLOCK.get(str(filt).strip().upper(), str(filt))
    exp = float(np.median(inv["exptimes"]))                # several exposure times in one night: median for the form
    date = Time(jd0.min(), format="jd").iso[:10]
    base = f"{planet}_{date}"
    hdr = ["#Planet: " + planet, "#Time format: JD_UTC", "#Time stamp: Exposure start", "#Flux format: Flux",
           f"#Filter: {fex}", f"#Exposure time in seconds: {exp:g}"]
    lauf = os.path.basename(m.out)
    f1 = m.path(f"{base}_{lauf}_exoclock_JDUTC.txt")         # run name in the file name: no mix-ups between runs
    old = m.path(f"{base}_exoclock_JDUTC.txt")               # name used before 2026-10-24
    if os.path.exists(old):
        os.remove(old)
    with open(f1, "w", newline="\n") as fh:
        fh.write("\n".join(hdr + [f"#Relative flux T1/({'+'.join(best['comps'])}), {aperture_en(c, r, n.sel)}, normalised out of transit; "
                                  f"meridian-flip step corrected ({flip * 1e3:+.2f} ppt), NOT airmass-detrended",
                                  "#Time                   Flux            Flux uncertainty"]) + "\n")
        np.savetxt(fh, np.c_[jd0, flipcorr, erel * scale], fmt=["%.7f", "%.6f", "%.6f"])
    f2 = m.path(f"{base}_detrended_BJDTDB.txt")
    with open(f2, "w", newline="\n") as fh:
        fh.write("\n".join(["#Planet: " + planet, "#Time format: BJD_TDB", "#Time stamp: Mid-exposure", "#Flux format: Flux",
                            "#Detrended (airmass + flip) - reference only, not for ExoClock",
                            "#BJD_TDB                Flux            Flux uncertainty  Airmass"]) + "\n")
        np.savetxt(fh, np.c_[n.t, det, erel / fb["base"] * scale, n.am], fmt=["%.7f", "%.6f", "%.6f", "%.4f"])
    f3 = m.path(f"{base}_best_ensemble.radec.txt")
    with open(f3, "w") as fh:
        fh.write("#RA in decimal or sexagesimal HOURS\n#Dec in decimal or sexagesimal DEGREES\n"
                 "#Ref Star=0,1,missing (0=target star, 1=ref star, missing->first ap=target, others=ref)\n"
                 "#Centroid=0,1,missing (0=do not centroid, 1=centroid, missing=centroid)\n"
                 "#Apparent Magnitude or missing (value = 99.999 if missing)\n#\n")
        for j, fl in [(0, 0)] + [(j, 1) for j in ens]:
            fh.write(f"{hms(c['star_ra'][j])}, {dms(c['star_dec'][j])}, {fl}, 1, {c['star_G'][j]:.3f}\n")
    mc = fitres["mcmc"]; pred = fitres["ephemeris"]
    site = m.cfg["site"]
    lines = [f"ExoClock-Formular, {planet}, Nacht {date}", "=" * 60,
             f"Datei .............. {os.path.basename(f1)}", f"Planet ............. {planet}",
             f"Datum .............. {Time(jd0.min(), format='jd').iso[:16]} bis {Time(jd0.max(), format='jd').iso[:16]} UTC",
             "Time format ........ JD_UTC", "Time stamp ......... Exposure start", "Flux format ........ Flux",
             f"Filter ............. {fex}  (" + (f"aus [export] filter = {filt}, Header ohne FILTER" if m.cfg.get("export", {}).get("filter")
                                                else f"FITS-Header FILTER = {filt}") + f"; im ExoClock-Menue genau diesen Filter waehlen)",
             f"Belichtung ......... {exp:g} s", f"Punkte ............. {sel.sum()}",
             f"Standort ........... {site['lat']} N, {site['lon']} E, {site['elev']} m",
             "Vergleichssterne ... " + ", ".join(f"{s} = Gaia DR3 {g}" for s, g in zip(best["comps"], best["gaia"])),
             f"Ziel ............... Gaia DR3 {c['star_gaia'][0]}",
             f"Detrending ......... keines (ExoClock fittet Airmass/Zeit); Flip-Stufe {flip * 1e3:+.2f} ppt korrigiert",
             f"Fehlerskalierung ... x{scale:.2f} auf gemessene Streuung", "",
             "Eigenes Ergebnis (nur Referenz):",
             f"  Tc = {mc['Tc'][1]:.5f} BJD_TDB +{(mc['Tc'][2] - mc['Tc'][1]) * 1440:.1f}/-{(mc['Tc'][1] - mc['Tc'][0]) * 1440:.1f} min",
             f"  Vorhersage {pred['Tc']:.5f} ({pred['source']}), O-C {mc['OC_min']:+.1f} min",
             f"  Tiefe {mc['depth_ppt'][1]:.2f} ppt ({mc['depth_ppt'][0]:.2f}..{mc['depth_ppt'][2]:.2f})"]
    try:
        from .kommentar import make
        lines += ["", "Kommentar fuer ExoClock (Englisch, zum Hineinkopieren; auch: transit kommentar <Messordner>):", "  " + make(m.out, m.cfg)]
    except Exception as e_:
        log(f"  Kommentar nicht erzeugt: {e_}")
    with open(m.path("exoclock_formular.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    log(f"Export: {os.path.basename(f1)}, {os.path.basename(f2)}, {os.path.basename(f3)}, exoclock_formular.txt")
