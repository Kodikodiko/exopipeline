"""Multi-radius aperture photometry cube (frames x stars x radii), processed frame by frame."""
import os
import time

import numpy as np
from astropy.stats import sigma_clipped_stats
from astropy.wcs import WCS
from photutils.aperture import CircularAperture, CircularAnnulus, aperture_photometry
from photutils.centroids import centroid_2dg, centroid_com
import warnings

from .frames import read_data
from . import progress

warnings.filterwarnings("ignore", message="The fit may not have converged")


def measure_star(data, x, y, radii, r_in, r_out, gain, rn, cbox):
    stamp = int(r_out) + 6
    ny, nx = data.shape
    xi, yi = int(round(x)), int(round(y))
    x1, x2, y1, y2 = xi - stamp, xi + stamp + 1, yi - stamp, yi + stamp + 1
    if x1 < 0 or y1 < 0 or x2 > nx or y2 > ny:
        return None
    st = data[y1:y2, x1:x2]
    cx, cy = x - x1, y - y1
    _, med, _ = sigma_clipped_stats(st, sigma=3)
    h = cbox // 2
    for _ in range(2):
        bx, by = int(round(cx)), int(round(cy))
        b = st[by - h:by + h + 1, bx - h:bx + h + 1] - med
        try:
            ox, oy = centroid_2dg(b)
        except Exception:
            ox, oy = centroid_com(np.clip(b, 0, None))
        if not (np.isfinite(ox) and np.isfinite(oy)) or abs(ox - h) > h or abs(oy - h) > h:
            ox, oy = centroid_com(np.clip(b, 0, None))
        cx, cy = bx - h + ox, by - h + oy
    ann = CircularAnnulus((cx, cy), r_in, r_out)
    am = ann.to_mask(method="center")
    av = am.multiply(st)[am.data > 0]
    _, bkg, _ = sigma_clipped_stats(av, sigma=3, maxiters=5)
    t = aperture_photometry(st, [CircularAperture((cx, cy), r) for r in radii], method="exact")
    raw = np.array([t[f"aperture_sum_{i}"][0] for i in range(len(radii))])
    area = np.pi * np.asarray(radii) ** 2
    flux = raw - bkg * area
    var = gain * np.clip(flux, 0, None) + area * (1 + area / av.size) * (gain * max(bkg, 0) + rn ** 2)
    yy, xx = np.mgrid[:st.shape[0], :st.shape[1]]
    rr2 = (xx - cx) ** 2 + (yy - cy) ** 2
    msk = rr2 < 144
    I = np.clip(st[msk] - bkg, 0, None)
    fwhm = 2.3548 * np.sqrt((I * rr2[msk]).sum() / (2 * I.sum())) if I.sum() > 0 else np.nan
    return dict(flux=flux, err=np.sqrt(var) / gain, bkg=bkg, x=cx + x1, y=cy + y1, fwhm=fwhm)


def pixbin(cfg, header):
    """2 for a colour (Bayer/OSC) camera, else 1.  [camera] farbkamera = "auto" (BAYERPAT in the header) | "ja" | "nein"."""
    v = str(cfg.get("camera", {}).get("farbkamera", "auto")).strip().lower()
    if v in ("ja", "yes", "true", "1"):
        return 2
    if v in ("nein", "no", "false", "0"):
        return 1
    return 2 if str(header.get("BAYERPAT", "")).strip() else 1


def superpixel(a, b, how="sum"):
    """b x b blocks: sum (calibrated data: one luminance value per Bayer cell) or max (raw peak for saturation)."""
    ny, nx = a.shape[0] // b * b, a.shape[1] // b * b
    v = a[:ny, :nx].reshape(ny // b, b, nx // b, b)
    return v.sum((1, 3)) if how == "sum" else v.max((1, 3))


def measure_frame(path, header, calibrator, ra, de, radii, ann, gain, rn, cbox, b=1):
    """All stars in one frame -> list of (flux, err, bkg, x, y, fwhm, peak) or None per star.
    b = 2 (colour camera): the calibrated Bayer image is summed in 2x2 superpixels before the photometry, so the
    R/G/B levels no longer show up as a pattern in the sky ring.  Everything going in and out stays in original
    image pixels (radii, annulus, x, y, FWHM, sky per pixel), so config, AIJ export and plots need no change."""
    raw = read_data(path)
    data = calibrator(raw)
    px, py = WCS(header).world_to_pixel_values(ra, de)
    if b > 1:
        data, raw = superpixel(data, b), superpixel(raw, b, "max")
        px, py = (np.asarray(px) + 0.5) / b - 0.5, (np.asarray(py) + 0.5) / b - 0.5
        rn = rn * b                                     # b*b read-outs summed
        radii, ann, cbox = np.asarray(radii, float) / b, (ann[0] / b, ann[1] / b), max(5, int(cbox) // b | 1)
    out = []
    for j in range(len(ra)):
        r = measure_star(data, px[j], py[j], radii, ann[0], ann[1], gain, rn, cbox)
        if r is None:
            out.append(None); continue
        xi, yi = int(round(r["x"])), int(round(r["y"]))
        pk = raw[max(yi - 4, 0):yi + 5, max(xi - 4, 0):xi + 5].max()
        x, y = (r["x"] + 0.5) * b - 0.5, (r["y"] + 0.5) * b - 0.5
        out.append((r["flux"], r["err"], r["bkg"] / b ** 2, x, y, r["fwhm"] * b, pk))
    return out


def build_cube(m, headers, stars, tm, calibrator, log=print, workers=1, cal_args=None):
    p, cam = m.cfg["photometry"], m.cfg["camera"]
    radii = np.array(p["radii"], float)
    r_in, r_out = p["annulus"]
    use = [i for i, x in enumerate(headers) if x["solved"]]
    nf, ns, nr = len(use), len(stars), len(radii)
    ra = np.array([s["ra"] for s in stars]); de = np.array([s["dec"] for s in stars])
    flux = np.full((nf, ns, nr), np.nan); ferr = flux.copy()
    bkg = np.full((nf, ns), np.nan); peak = bkg.copy(); xs = bkg.copy(); ys = bkg.copy(); fw = bkg.copy()
    t0 = time.time()
    bar = progress.task(f"Photometrie ({calibrator.mode})", nf, "Frames")
    b = pixbin(m.cfg, headers[use[0]]["header"]) if use else 1
    if b > 1:
        log(f"  Farbkamera (BAYERPAT {headers[use[0]]['header'].get('BAYERPAT', '-')}): Photometrie in {b}x{b}-Superpixeln; "
            f"Radien und Positionen weiter in Bildpixeln")
    args = (radii, (r_in, r_out), cam["gain_e_per_adu"], cam["readnoise_e"], p["centroid_box"], b)

    def store(k, res):
        for j, r in enumerate(res):
            if r is not None:
                flux[k, j], ferr[k, j], bkg[k, j], xs[k, j], ys[k, j], fw[k, j], peak[k, j] = r
    if workers > 1 and cal_args is not None and nf > 2 * workers:
        from . import parallel
        ctr = parallel.counter()
        items = [(k, headers[i]["file"], headers[i]["header"]) for k, i in enumerate(use)]
        size = max(1, min(8, nf // (4 * workers)))             # small chunks: even load, live progress
        log(f"  {workers} Prozesse, je {size} Frames pro Paket")
        with parallel.executor(workers, parallel.init_cube, (cal_args, ra, de) + args + (ctr,)) as ex:
            jobs = [(c, parallel.cube_frames, (ch,)) for c, ch in enumerate(parallel.chunks(items, size))]
            parallel.run_jobs(ex, jobs, on_done=lambda key, res: [store(k, r) for k, r in res],
                              poll=lambda: bar.update(n=ctr.value))
    else:
        for k, i in enumerate(use):
            x = headers[i]
            store(k, measure_frame(x["file"], x["header"], calibrator, ra, de, *args))
            bar.update()
            progress.debug(f"Frame {k + 1}/{nf} {os.path.basename(x['file'])}  {time.time() - t0:.0f}s")
    bar.done()
    sub = lambda a: np.asarray(a)[use]
    cube = dict(flux=flux, flux_err=ferr, background=bkg, peak_raw=peak, x=xs, y=ys, fwhm_star=fw, radii=radii,
                fwhm=np.nanmedian(fw, axis=1), star_name=np.array([s["name"] for s in stars]),
                star_role=np.array([s["role"] for s in stars]), star_ra=ra, star_dec=de,
                star_G=np.array([float(s["G"]) for s in stars]), star_gaia=np.array([str(s["source_id"]) for s in stars]),
                frame_file=np.array([os.path.basename(headers[i]["file"]) for i in use]),
                jd_start=sub(tm["jd_start"]), jd_utc_mid=sub(tm["jd_mid"]), bjd_tdb=sub(tm["bjd_tdb"]),
                airmass_calc=sub(tm["airmass_calc"]), airmass_header=sub(tm["airmass_header"]), east=sub(tm["east"]),
                ccd_temp=np.array([float(headers[i]["header"].get("CCD-TEMP", np.nan)) for i in use]),
                calib=calibrator.mode, pixbin=b, runtime_s=time.time() - t0)
    return cube
