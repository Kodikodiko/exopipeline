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


def measure_frame(path, header, calibrator, ra, de, radii, ann, gain, rn, cbox):
    """All stars in one frame -> list of (flux, err, bkg, x, y, fwhm, peak) or None per star."""
    raw = read_data(path)
    data = calibrator(raw)
    px, py = WCS(header).world_to_pixel_values(ra, de)
    out = []
    for j in range(len(ra)):
        r = measure_star(data, px[j], py[j], radii, ann[0], ann[1], gain, rn, cbox)
        if r is None:
            out.append(None); continue
        xi, yi = int(round(r["x"])), int(round(r["y"]))
        out.append((r["flux"], r["err"], r["bkg"], r["x"], r["y"], r["fwhm"], raw[yi - 4:yi + 5, xi - 4:xi + 5].max()))
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
    args = (radii, (r_in, r_out), cam["gain_e_per_adu"], cam["readnoise_e"], p["centroid_box"])

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
                calib=calibrator.mode, runtime_s=time.time() - t0)
    return cube
