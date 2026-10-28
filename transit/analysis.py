"""Frame selection, linearity check, meridian-flip offsets, comparison-ensemble search, transit fit, MCMC."""
import numpy as np
from scipy.optimize import least_squares

from .model import model

SIG_RES = 6e-3
STARTS = np.array([-30, -15, 0, 15, 30]) / 1440


class Night:
    """Everything the search/fit needs, built from a cube + config + ephemeris prediction."""

    def __init__(self, cube, cfg, pred, geom, exclude_frames=(), log=print):
        self.c, self.cfg, self.pred, self.geom, self.log = cube, cfg, pred, geom, log
        c = cube
        self.names = [str(s) for s in c["star_name"]]
        nf, ns, _ = c["flux"].shape
        sat = cfg["camera"]["saturation_adu"]
        pk = c["peak_raw"]
        keep = ~np.isin(c["frame_file"], list(exclude_frames))
        amax = cfg["search"].get("airmass_max", 0)          # 0 = no cut; drops frames above this airmass (edge systematics)
        self.n_airmass_cut = int((keep & (c["airmass_calc"] > amax)).sum()) if amax else 0
        if amax:
            keep &= c["airmass_calc"] <= amax
        self.keep = keep
        self.excluded_stars = [s for s in cfg.get("comps", {}).get("exclude_stars", []) if s in self.names]
        cand = [j for j in range(1, ns) if self.names[j] not in self.excluded_stars]
        frac = (pk[keep][:, cand] > sat).mean(0)
        self.cand = [j for j, f in zip(cand, frac) if f <= 0.05]
        self.dropped_saturating = [self.names[j] for j, f in zip(cand, frac) if f > 0.05]
        sel = keep & (pk[:, 0] <= sat) & np.all(pk[:, self.cand] <= sat, axis=1)
        sel &= np.all(np.isfinite(c["flux"][:, [0] + self.cand, :]).reshape(nf, -1), axis=1)
        self.sel = sel
        self.t = c["bjd_tdb"][sel]
        mg = cfg["search"]["oot_margin_min"] / 1440
        self.oot = (self.t < pred["ingress"] - mg) | (self.t > pred["egress"] + mg)
        self.am = c["airmass_calc"][sel]
        self.east = c["east"][sel]
        # baseline columns: 1, airmass (, airmass^2 with fit.airmass_order = 2) (, flip step - always the LAST column)
        cols = [np.ones(sel.sum()), self.am - 1.5]
        self.airmass_order = int(cfg["fit"].get("airmass_order", 1))
        if self.airmass_order >= 2:
            cols.append((self.am - 1.5) ** 2)
        self.detrend_fwhm = bool(cfg["fit"].get("detrend_fwhm", False))
        if self.detrend_fwhm:                                # seeing/focus term, [px] around the night's median
            fw = np.asarray(c["fwhm"], float)[sel]
            cols.append(np.where(np.isfinite(fw), fw - np.nanmedian(fw), 0.0))
        self.weights = str(cfg["fit"].get("weights", "none"))
        if self.weights == "modell" and "exptime" not in c:
            log("[WARN] fit.weights = 'modell' braucht die Belichtungszeiten (headers.csv) - rechne ungewichtet")
            self.weights = "none"
        self.flip_mode = cfg["fit"]["flip"] if self.east.min() != self.east.max() else "none"
        if self.flip_mode != "none":
            cols.append(self.east)
        self.X = np.vstack(cols).T
        self.fc = self.X.shape[1] - 1 if self.flip_mode != "none" else None      # flip column
        xs, ys = np.nanmedian(c["x"], axis=0), np.nanmedian(c["y"], axis=0)
        self.dxy = np.c_[xs - xs[0], ys - ys[0]]            # star offsets from the target [px], for the symmetry measure
        self.u = (cfg["fit"]["u1"], cfg["fit"]["u2"])
        self.flipd = {}
        self.flip_target = (0.0, 1.0)
        self.info = dict(frames_total=int(nf), frames_used=int(sel.sum()), excluded_list=int((~keep).sum()),
                         excluded_saturation=int((keep & ~sel).sum()), n_oot=int(self.oot.sum()),
                         n_oot_pre=int((self.oot & (self.t < pred["Tc"])).sum()),
                         n_oot_post=int((self.oot & (self.t > pred["Tc"])).sum()),
                         dropped_saturating=self.dropped_saturating, flip_mode=self.flip_mode,
                         excluded_stars=self.excluded_stars, excluded_airmass=self.n_airmass_cut,
                         airmass_max=amax, airmass_order=self.airmass_order,
                         weights=self.weights, detrend_fwhm=self.detrend_fwhm,
                         symmetry_weight=cfg["search"].get("symmetry_weight", 0))

    def asym(self, ens, ir=None):
        """Ensemble asymmetry around the target: |flux-weighted sum of offset vectors| / flux-weighted sum of lengths
        (0 = balanced on all sides, 1 = all on one side).  The flat-field residual turns by 180 deg at the flip,
        so a balanced ensemble cancels more of it."""
        ir = self.ir(16) if ir is None else ir
        w = np.nanmedian(self.c["flux"][self.sel][:, ens, ir], axis=0)
        v = self.dxy[ens]
        return float(np.linalg.norm((w[:, None] * v).sum(0)) / (w * np.linalg.norm(v, axis=1)).sum())

    def ir(self, r):
        return list(self.c["radii"]).index(r)

    def r_px(self, r):
        """Typical radius in px (median over the used frames; for a growing aperture it varies per frame)."""
        from .apertur import px
        return px(self.c, r, self.sel)[0]

    def r_text(self, r):
        from .apertur import text
        return text(self.c, r, self.sel)

    # ---------------------------------------------------------------- comp pre-filter
    def prefilter(self, r=16):
        ir = self.ir(r)
        F = self.c["flux"][self.sel][:, self.cand, ir]
        tt = self.t - self.t.mean()
        rms, tr = [], []
        for a in range(len(self.cand)):
            lc = F[:, a] / np.delete(F, a, axis=1).sum(1); lc /= np.median(lc)
            rms.append(np.std(lc) * 1e3)
            tr.append(abs(np.polyfit(tt, lc, 1)[0]) * np.ptp(tt) * 1e3)
        rms, tr = np.array(rms), np.array(tr)
        k = self.cfg["search"]["prefilter_sigma"]
        bad = (rms > k * np.median(rms)) | (tr > k * np.median(tr))
        self.pool = [j for j, b in zip(self.cand, bad) if not b]
        self.prefilter_table = [dict(name=self.names[j], rms_ppt=float(a), trend_ppt=float(b), rejected=bool(x))
                                for j, a, b, x in zip(self.cand, rms, tr, bad)]
        return [self.names[j] for j, b in zip(self.cand, bad) if b]

    # ---------------------------------------------------------------- flip offsets
    def flip_offsets(self, r=16):
        if self.flip_mode == "none":
            return None
        c = self.c
        ir = self.ir(r)
        hrs = c["bjd_tdb"]
        tflip = hrs[c["east"] > 0].min() if c["east"][0] == 0 else hrs[c["east"] == 0].min()
        w0, w1 = self.cfg["fit"]["flip_window_h"]
        sat = self.cfg["camera"]["saturation_adu"]
        win = self.keep & (hrs > tflip + w0 / 24) & (hrs < tflip + w1 / 24)
        rejected = {p["name"] for p in getattr(self, "prefilter_table", []) if p["rejected"]}
        stars = [j for j in range(1, len(self.names)) if self.names[j] not in rejected and self.names[j] not in self.excluded_stars]
        okc = [j for j in stars if np.nanmax(c["peak_raw"][win, j]) < sat]
        am = c["airmass_calc"]
        rows = []
        for j in okc:
            others = [k for k in okc if k != j]
            y = np.log(c["flux"][:, j, ir] / c["flux"][:, others, ir].sum(1))
            X = np.vstack([np.ones(len(y)), am - 1.45, c["east"]]).T
            mm = win & np.isfinite(y)
            co, *_ = np.linalg.lstsq(X[mm], y[mm], rcond=None)
            res = y[mm] - X[mm] @ co
            cov = np.linalg.inv(X[mm].T @ X[mm]) * res.var(ddof=3)
            rows.append(dict(name=self.names[j], idx=j, d=co[2], err=np.sqrt(cov[2, 2]),
                             x=float(np.nanmedian(c["x"][win, j])), y=float(np.nanmedian(c["y"][win, j]))))
        d = np.array([r_["d"] for r_ in rows]); e = np.array([r_["err"] for r_ in rows])
        x = np.array([r_["x"] for r_ in rows]); y = np.array([r_["y"] for r_ in rows])
        A = np.vstack([np.ones_like(x), (x - 3112) / 1000, (y - 2084) / 1000]).T
        wts = 1 / e ** 2
        p, *_ = np.linalg.lstsq(A * np.sqrt(wts)[:, None], d * np.sqrt(wts), rcond=None)
        xt, yt = np.nanmedian(c["x"][win, 0]), np.nanmedian(c["y"][win, 0])
        pred = p @ [1, (xt - 3112) / 1000, (yt - 2084) / 1000]
        scatter = float(np.std(d - A @ p))
        self.flipd = {r_["idx"]: r_["d"] for r_ in rows}
        self.flip_target = (float(pred), scatter)
        self.flip_table = rows
        return dict(target_pred_ppt=pred * 1e3, scatter_ppt=scatter * 1e3, n_stars=len(rows), plane=p.tolist(),
                    t_flip_bjd=float(tflip), stars=[dict(name=r_["name"], d_ppt=r_["d"] * 1e3, err_ppt=r_["err"] * 1e3,
                                                          x=r_["x"], y=r_["y"]) for r_ in rows])

    def flip_prior(self, ens, ir):
        if self.flip_mode != "prior":
            return None
        D, S = self.flip_target
        w = np.nanmedian(self.c["flux"][self.sel][:, ens, ir], axis=0)
        dens = [self.flipd.get(j, np.nan) for j in ens]
        if np.any(np.isnan(dens)):
            return D, np.sqrt(2) * S
        return D - np.average(dens, weights=w), np.sqrt(S ** 2 + S ** 2 * (w ** 2).sum() / w.sum() ** 2)

    # ---------------------------------------------------------------- light curves / linear solve
    def rel(self, ir, ens):
        f = self.c["flux"][self.sel, 0, ir] / self.c["flux"][self.sel][:, ens, ir].sum(1)
        return f / np.median(f[self.oot])

    def rel_err(self, ir, ens):
        c = self.c
        ft = c["flux"][self.sel, 0, ir]; et = c["flux_err"][self.sel, 0, ir]
        fc = c["flux"][self.sel][:, ens, ir].sum(1); ec = np.sqrt((c["flux_err"][self.sel][:, ens, ir] ** 2).sum(1))
        r = ft / fc
        return r * np.hypot(et / ft, ec / fc) / np.median(r[self.oot])

    def noise_shape(self, ir, ens):
        """Relative noise per frame (median 1) for fit.weights = "modell", else all 1.  Scintillation after Young (1967)
        with the factor 1.5 of Osborn et al. (2015), for the target and for the comparison sum (independent per star),
        plus photon/read noise.  Only the shape is used: the overall scale still comes from the residuals."""
        if self.weights != "modell":
            return np.ones(self.sel.sum())
        D = float(self.cfg["fit"].get("aperture_cm", 15.0))
        h = float(self.cfg.get("site", {}).get("elev") or 0.0)
        texp = np.asarray(self.c["exptime"], float)[self.sel]
        sc = 1.5 * 0.09 * D ** (-2 / 3) * self.am ** 1.75 * np.exp(-h / 8000) / np.sqrt(2 * texp)
        F = self.c["flux"][self.sel][:, ens, ir]
        sc_c = sc * np.sqrt((F ** 2).sum(1)) / F.sum(1)
        ph = self.rel_err(ir, ens) / self.rel(ir, ens)
        s = np.sqrt(sc ** 2 + sc_c ** 2 + ph ** 2)
        return s / np.median(s)

    def lin_solve(self, f, mm, X, prior, w=None):
        """Baseline coefficients; w = 1/noise per frame (weighted least squares), None = equal weights."""
        A = X * mm[:, None]
        if w is not None:
            A, f = A * w[:, None], f * w
        if prior is None:
            co, *_ = np.linalg.lstsq(A, f, rcond=None)
            return co, np.array([])
        mu, sd = prior
        wp = SIG_RES / sd
        row = np.zeros(X.shape[1]); row[self.fc] = wp
        co, *_ = np.linalg.lstsq(np.vstack([A, row]), np.concatenate([f, [wp * mu]]), rcond=None)
        return co, np.array([wp * (mu - co[self.fc])])

    def oot_rms(self, ir, ens):
        f = self.rel(ir, ens)
        o = self.oot
        co, _ = self.lin_solve(f[o], np.ones(o.sum()), self.X[o], self.flip_prior(ens, ir))
        return float(np.std(f[o] - self.X[o] @ co) * 1e3)

    # ---------------------------------------------------------------- greedy search
    def greedy(self, r, tick=None):
        ir = self.ir(r)
        s = self.cfg["search"]
        seen = {}

        sw = float(s.get("symmetry_weight", 0))

        def score(e):
            k = tuple(sorted(e))
            if k not in seen:
                seen[k] = self.oot_rms(ir, list(k)) * ((1 + sw * self.asym(list(k), ir)) if sw and len(k) > 1 else 1)
                if tick:
                    tick(len(seen))
            return seen[k]
        cur = sorted(self.pool, key=lambda j: score([j]))[:s["n_min"]]
        best = score(cur); improved = True
        while improved:
            improved = False
            if len(cur) < min(s["n_max"], len(self.pool)):        # small pools: never search beyond the pool
                v, j = min((score(cur + [j]), j) for j in self.pool if j not in cur)
                if v < best:
                    cur, best, improved = cur + [j], v, True
            if len(cur) > s["n_min"]:
                v, j = min((score([k for k in cur if k != j]), j) for j in cur)
                if v < best:
                    cur, best, improved = [k for k in cur if k != j], v, True
        path = list(cur)
        while len(path) < min(s["n_max"], len(self.pool)):
            path.append(min((score(path + [j]), j) for j in self.pool if j not in path)[1])
        return {k: v for k, v in seen.items() if s["n_min"] <= len(k) <= s["n_max"]}, tuple(sorted(cur)), best

    # ---------------------------------------------------------------- transit fit
    def fit(self, r, ens, mask=None, free=False):
        ir = self.ir(r)
        m_ = np.ones(self.sel.sum(), bool) if mask is None else mask
        f = self.rel(ir, ens)[m_]; tt = self.t[m_]; X = self.X[m_]
        pr = self.flip_prior(ens, ir)
        if pr is not None and X[:, self.fc].min() == X[:, self.fc].max():
            X = X[:, :-1]; pr = None                           # no flip inside the mask: drop the flip column (last)
        P = self.pred["P"]; u1, u2 = self.u
        s = self.noise_shape(ir, ens)[m_]; wt = 1 / s

        Tc0 = self.pred["Tc"]

        # Tc is fitted as the offset dt = Tc - Tc0 (days).  With the absolute BJD (~2.46e6) the optimizer's relative
        # step tolerance (xtol * |x|) amounted to ~35 min and it stopped after 1-2 steps near the start value.
        def resid(q):
            if free:
                dt, rp, ars, inc = q
            else:
                (dt, rp), (ars, inc) = q, self.geom
            mm = model(tt, Tc0 + dt, P, rp, ars, inc, u1, u2)
            co, pres = self.lin_solve(f, mm, X, pr, wt)
            return np.concatenate([(f - mm * (X @ co)) * wt, pres])
        best = None
        for dt in STARTS:
            q0 = [dt, 0.09] + ([self.geom[0], min(self.geom[1], 89.5)] if free else [])
            lo = [-0.04, 0.02] + ([3, 75] if free else [])
            hi = [0.04, 0.25] + ([25, 90] if free else [])
            rr = least_squares(resid, q0, bounds=(lo, hi), x_scale=[0.002, 0.005] + ([0.5, 1] if free else []))
            if best is None or rr.cost < best.cost:
                best = rr
        nres = len(f)
        res = best.fun[:nres]
        k = len(best.x) + X.shape[1]
        s2 = (best.fun ** 2).sum() / (nres - k)
        try:
            cov = np.linalg.inv(best.jac.T @ best.jac) * s2
            err = np.sqrt(np.diag(cov))
        except np.linalg.LinAlgError:
            cov, err = None, np.full(len(best.x), np.nan)
        q = best.x.copy()
        q[0] += Tc0
        ars, inc = (q[2], q[3]) if free else self.geom
        mm = model(tt, q[0], P, q[1], ars, inc, u1, u2)
        co, _ = self.lin_solve(f, mm, X, pr, wt)
        # res is noise-normalised (res / s); the BIC includes sum(ln s), so weighted and unweighted fits compare directly
        return dict(Tc=float(q[0]), Tc_err=float(err[0]), rp=float(q[1]), depth_ppt=float(q[1] ** 2 * 1e3),
                    ars=float(ars), inc=float(inc), rms_ppt=float(np.std(res) * 1e3),
                    flip_ppt=float(co[self.fc] / co[0] * 1e3) if (self.fc is not None and X.shape[1] > self.fc) else 0.0, prior=pr,
                    f=f, t=tt, model=mm, base=X @ co, res=res, s=s, mask=m_, ncol=X.shape[1],
                    bic=float(nres * np.log((res ** 2).sum() / nres) + 2 * np.log(s).sum() + k * np.log(nres)),
                    errs=[float(e) for e in err], cov=None if cov is None else cov.tolist())

    # ---------------------------------------------------------------- MCMC
    def mcmc(self, r, ens, free=False, nstep=30000, seed=1, tick=None):
        """Single chain (serial path); same numbers as before the multi-chain version."""
        return summarize_chains([self.mcmc_chain(r, ens, free, nstep, seed, tick)], free)

    def mcmc_chain(self, r, ens, free=False, nstep=30000, seed=1, tick=None, jitter=0.0):
        """One Metropolis chain from the best fit; returns the chain after burn-in (first quarter dropped).
        jitter > 0 starts the chain jitter x step away from the best fit (independent chains for R-hat)."""
        rng = np.random.default_rng(seed)
        fb = self.fit(r, ens, free=free)
        f, tt = fb["f"], fb["t"]
        pr = fb["prior"]; X = self.X[:, :fb["ncol"]]
        beta = beta_factor(fb["res"])
        sig = np.std(fb["res"]) * beta
        wt = 1 / fb["s"]
        P = self.pred["P"]; u1, u2 = self.u

        def lnp(q):
            if free:
                tc, rp, ars, inc = q
                if not (3 < ars < 25 and 75 < inc <= 90):
                    return -np.inf
            else:
                (tc, rp), (ars, inc) = q, self.geom
            if not 0.02 < rp < 0.25:
                return -np.inf
            mm = model(tt, tc, P, rp, ars, inc, u1, u2)
            co, pres = self.lin_solve(f, mm, X, pr, wt)
            rr = (f - mm * (X @ co)) * wt
            lp = -0.5 * ((rr / sig) ** 2).sum()
            if pres.size:
                lp -= 0.5 * (pres[0] / SIG_RES) ** 2
            return lp
        q = np.array([fb["Tc"], fb["rp"]] + ([fb["ars"], fb["inc"]] if free else []))
        step = np.array([0.0015, 0.002] + ([0.3, 0.5] if free else []))
        if jitter:
            q = q + jitter * step * rng.standard_normal(q.size)
        adapt = min(2000, nstep // 6)
        lp = lnp(q); chain = []; acc = 0
        for i in range(nstep):
            qn = q + step * rng.standard_normal(q.size)
            ln = lnp(qn)
            if np.log(rng.random()) < ln - lp:
                q, lp = qn, ln; acc += 1
            chain.append(q.copy())
            if i == adapt:
                step *= np.clip(acc / adapt / 0.3, 0.3, 3)
            if tick and (i + 1) % 250 == 0:
                tick(i + 1, acc / (i + 1))
        return dict(chain=np.array(chain[nstep // 4:]), acc=acc / nstep, beta=beta, sig=sig)


def gelman_rubin(chains):
    """R-hat per parameter for a list of equal-length chains (n x k arrays)."""
    n = min(len(c) for c in chains)
    a = np.array([c[:n] for c in chains])                  # m x n x k
    if len(a) < 2:
        return None
    W = a.var(axis=1, ddof=1).mean(0)
    B = n * a.mean(axis=1).var(axis=0, ddof=1)
    V = (n - 1) / n * W + B / n
    return np.sqrt(V / W).tolist()


def summarize_chains(res, free):
    ch = np.vstack([r["chain"] for r in res])
    pc = lambda a: np.percentile(a, [16, 50, 84]).tolist()
    rh = gelman_rubin([r["chain"] for r in res])
    out = dict(beta=res[0]["beta"], sigma_ppt=res[0]["sig"] * 1e3, acceptance=float(np.mean([r["acc"] for r in res])),
               Tc=pc(ch[:, 0]), depth_ppt=pc(ch[:, 1] ** 2 * 1e3), ars=pc(ch[:, 2]) if free else None,
               inc=pc(ch[:, 3]) if free else None, n_chains=len(res), n_samples=int(len(ch)))
    if rh is not None:
        names = ["Tc", "rp"] + (["ars", "inc"] if free else [])
        out["rhat"] = dict(zip(names, rh))
        out["rhat_max"] = float(max(rh))
    return out


def beta_factor(res):
    s1 = np.std(res); out = []
    for nb in range(5, 21):
        M = res.size // nb
        if M < 4:
            break
        sN = np.std(res[:M * nb].reshape(M, nb).mean(1))
        out.append(sN / (s1 / np.sqrt(nb) * np.sqrt(M / (M - 1))))
    return max(1.0, float(np.median(out))) if out else 1.0


def linearity(cube, sel_frames, pool, cfg, r=16):
    """Residual of brighter comps vs a faint reference ensemble, binned by raw peak (good-seeing frames)."""
    c = cube
    ir = list(c["radii"]).index(r)
    pk = c["peak_raw"]
    faint = [j for j in pool if np.nanmax(pk[sel_frames, j]) < 35000]
    bright = [j for j in pool if j not in faint] + [0]
    if len(faint) < 3:
        return None
    am, east, fw = c["airmass_calc"], c["east"], c["fwhm"]
    X = np.vstack([np.ones(len(am)), am, east]).T
    good = sel_frames & (fw < np.nanpercentile(fw[sel_frames], 40))
    pts = []
    for j in bright:
        y = np.log(c["flux"][:, j, ir] / c["flux"][:, faint, ir].sum(1))
        low = sel_frames & (pk[:, j] < 40000) & np.isfinite(y)
        if low.sum() < 8:
            continue
        co, *_ = np.linalg.lstsq(X[low], y[low], rcond=None)
        res = (y - X @ co) * 1e3
        for i in np.where(good & np.isfinite(y))[0]:
            pts.append((pk[i, j], res[i]))
    pts = np.array(pts)
    if not len(pts):
        return None
    tab = []
    for a, b in [(0, 40000), (40000, 45000), (45000, 50000), (50000, 55000), (55000, 60000), (60000, 65000), (65000, 70000)]:
        s = pts[(pts[:, 0] >= a) & (pts[:, 0] < b), 1]
        if len(s) >= 3:
            tab.append(dict(bin=f"{a // 1000}-{b // 1000}k", n=len(s), median_ppt=float(np.median(s)),
                            sem_ppt=float(1.4826 * np.median(np.abs(s - np.median(s))) * 1.2533 / np.sqrt(len(s)))))
    return dict(table=tab, points=pts, faint=len(faint))
