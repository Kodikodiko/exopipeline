"""Process pool for the expensive steps (fits, MCMC chains, cube photometry).  Standard library only.

Workers are spawned processes (Windows); each gets one BLAS/OpenMP thread so N workers use N cores.
The worker functions below also run in-process for the serial path (workers = 1), so both paths
compute exactly the same thing.
"""
import multiprocessing as mp
import os
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait

THREAD_VARS = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS")
SCALARS = ("Tc", "Tc_err", "rp", "rp_err", "depth_ppt", "ars", "inc", "rms_ppt", "flip_ppt", "bic")

_G = {}


def n_workers(m, a, key="workers"):
    """--workers N  >  [run] workers  >  cores - 2 (0 or missing = automatic)."""
    w = getattr(a, "workers", None)
    if not w:
        w = m.cfg.get("run", {}).get("workers", 0)
    if not w or w <= 0:
        w = max(1, (os.cpu_count() or 2) - 2)
    if key != "workers":
        cap = m.cfg.get("run", {}).get(key, 0)
        if cap and cap > 0:
            w = min(w, cap)
    return int(w)


def executor(n, initializer=None, initargs=()):
    for v in THREAD_VARS:               # inherited by the spawned workers (this process has numpy loaded already)
        os.environ[v] = "1"
    return ProcessPoolExecutor(max_workers=n, mp_context=mp.get_context("spawn"), initializer=initializer, initargs=initargs)


def counter():
    return mp.get_context("spawn").Value("q", 0)


def run_jobs(ex, jobs, on_done=None, poll=None, poll_s=1.0):
    """Submit [(key, fn, args)], return {key: result}; on_done(key, result) per finished job,
    poll() every poll_s while waiting (progress from a shared counter)."""
    futs = {ex.submit(fn, *args): key for key, fn, args in jobs}
    out, pending = {}, set(futs)
    while pending:
        done, pending = wait(pending, timeout=poll_s, return_when=FIRST_COMPLETED)
        for f in done:
            out[futs[f]] = f.result()
            if on_done:
                on_done(futs[f], out[futs[f]])
        if poll:
            poll()
    return out


# ------------------------------------------------------------------ fit / MCMC workers (Night shared per worker)
def init_night(night, ctr=None):
    _G["n"], _G["ctr"] = night, ctr


def slim(f):
    return {k: f[k] for k in SCALARS}


def fit_combo(radius, ens):
    n = _G["n"]
    return slim(n.fit(radius, ens)), slim(n.fit(radius, ens, free=True))


def fit_one(radius, ens, mask=None, free=False, rp_fix=None):
    return slim(_G["n"].fit(radius, ens, mask=mask, free=free, rp_fix=rp_fix))


def tc_profile(radius, ens, half_min, step_min):
    return _G["n"].tc_profile(radius, ens, half_min, step_min)


def mcmc_chain(radius, ens, free, nstep, seed, jitter):
    ctr = _G.get("ctr")
    last = [0]

    def tick(i, acc):
        if ctr is not None:
            with ctr.get_lock():
                ctr.value += i - last[0]
            last[0] = i
    r = _G["n"].mcmc_chain(radius, ens, free=free, nstep=nstep, seed=seed, tick=tick, jitter=jitter)
    return r


def chain_plan(nstep, workers, chains_cfg=0):
    """(chains, steps per chain).  Same number of kept samples as one chain of nstep."""
    if chains_cfg and chains_cfg > 0:
        k = int(chains_cfg)
    elif workers <= 1:
        k = 1
    else:
        k = int(min(workers, 16, max(2, nstep // 2000)))
    return k, int(-(-nstep // k))


# ------------------------------------------------------------------ cube workers (calibrator built once per worker)
def init_cube(cal_args, ra, de, radii, ann, gain, rn, cbox, b=1, ctr=None):
    from .calib import Calibrator
    _G.update(cal=Calibrator(*cal_args), ra=ra, de=de, radii=radii, ann=ann, gain=gain, rn=rn, cbox=cbox, b=b, ctr=ctr)


def cube_frames(items):
    """items: [(k, file, header)] -> [(k, per-star results)]"""
    from .photometry import measure_frame
    out = []
    for k, path, hdr in items:
        out.append((k, measure_frame(path, hdr, _G["cal"], _G["ra"], _G["de"], _G["radii"], _G["ann"], _G["gain"],
                                     _G["rn"], _G["cbox"], _G.get("b", 1))))
        ctr = _G.get("ctr")
        if ctr is not None:
            with ctr.get_lock():
                ctr.value += 1
    return out


def chunks(seq, n):
    return [seq[i:i + n] for i in range(0, len(seq), n)]


def now():
    return time.time()
