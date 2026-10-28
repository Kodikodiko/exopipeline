"""Quadratic limb-darkened transit light curve (circular orbit), numpy only.

The occulted flux is integrated over the stellar disk in thin annuli using the exact
circle-circle overlap area, which reproduces the Mandel & Agol (2002) quadratic-LD
model to ~1e-6 for N_ANN=1000.
"""
import numpy as np

N_ANN = 1000
_r = np.linspace(0, 1, N_ANN + 1)


def _overlap(R, p, z):
    """Area of overlap of a circle radius R (centre 0) with a circle radius p at distance z."""
    R = np.asarray(R, float)[None, :]
    z = np.asarray(z, float)[:, None]
    A = np.zeros(np.broadcast(R, z).shape)
    full_in = z <= R - p                       # planet completely inside radius R
    A = np.where(full_in, np.pi * p * p, A)
    cover = z <= p - R                         # circle R completely inside planet
    A = np.where(cover, np.pi * R * R, A)
    part = (z < R + p) & ~full_in & ~cover
    with np.errstate(invalid="ignore", divide="ignore"):
        k0 = np.arccos(np.clip((p * p + z * z - R * R) / (2 * p * z), -1, 1))
        k1 = np.arccos(np.clip((R * R + z * z - p * p) / (2 * R * z), -1, 1))
        sq = np.sqrt(np.clip(4 * z * z * R * R - (R * R + z * z - p * p) ** 2, 0, None))
        Ap = p * p * k0 + R * R * k1 - 0.5 * sq
    return np.where(part, Ap, A)


def flux_z_full(z, p, u1, u2):
    """Reference: all N_ANN annuli for every point (slow, kept for tests)."""
    z = np.atleast_1d(z)
    out = np.ones(z.shape)
    m = z < 1 + p
    if not m.any():
        return out
    rm = 0.5 * (_r[1:] + _r[:-1])
    mu = np.sqrt(1 - rm ** 2)
    I = 1 - u1 * (1 - mu) - u2 * (1 - mu) ** 2
    norm = np.sum(I * np.pi * (_r[1:] ** 2 - _r[:-1] ** 2))
    A = _overlap(_r, p, z[m])
    dA = np.diff(A, axis=1)
    out[m] = 1 - (dA * I[None, :]).sum(1) / norm
    return out


def flux_z(z, p, u1, u2):
    """Same sum as flux_z_full, but only over the annuli the planet edge actually crosses.

    For annulus radius R the overlap is 0 (R <= z - p), pi R^2 (R <= p - z) or pi p^2 (R >= z + p);
    only R between |z - p| and z + p needs the circle-circle formula.  The pi R^2 part below the
    window is a cumulative sum, the pi p^2 part above it has dA = 0.
    """
    z = np.atleast_1d(np.asarray(z, float))
    out = np.ones(z.shape)
    m = z < 1 + p
    if not m.any():
        return out
    rm = 0.5 * (_r[1:] + _r[:-1])
    mu = np.sqrt(1 - rm ** 2)
    I = 1 - u1 * (1 - mu) - u2 * (1 - mu) ** 2
    ring = np.pi * (_r[1:] ** 2 - _r[:-1] ** 2)
    norm = np.sum(I * ring)
    cum = np.concatenate([[0.0], np.cumsum(I * ring)])        # sum of I*ring over annuli 0..k-1
    zz = z[m]
    lo = np.abs(zz - p); hi = zz + p
    # grid points j0..j1 (inclusive) bracket the window; annuli k = j0..j1-1 use the exact formula
    j0 = np.clip(np.searchsorted(_r, lo, side="right") - 1, 0, N_ANN)
    j1 = np.clip(np.searchsorted(_r, hi, side="left"), 0, N_ANN)
    K = int((j1 - j0).max()) + 1
    jj = np.minimum(j0[:, None] + np.arange(K + 1)[None, :], N_ANN)   # K+1 grid points per row
    R = _r[jj]
    A = _overlap_rows(R, p, zz)
    dA = np.diff(A, axis=1)                                   # annuli jj[:, :-1]
    kk = jj[:, :-1]
    valid = (j0[:, None] + np.arange(K)[None, :]) < N_ANN
    win = (np.where(valid, dA, 0.0) * I[np.minimum(kk, N_ANN - 1)]).sum(1)
    # below the window: overlap pi R^2 if the planet covers the centre (z < p), else 0
    below = np.where(zz < p, cum[j0], 0.0)
    out[m] = 1 - (below + win) / norm
    return out


def _overlap_rows(R, p, z):
    """_overlap for a different radius grid per point: R (n x k), z (n)."""
    z = z[:, None]
    A = np.zeros(R.shape)
    full_in = z <= R - p
    A = np.where(full_in, np.pi * p * p, A)
    cover = z <= p - R
    A = np.where(cover, np.pi * R * R, A)
    part = (z < R + p) & ~full_in & ~cover
    with np.errstate(invalid="ignore", divide="ignore"):
        k0 = np.arccos(np.clip((p * p + z * z - R * R) / (2 * p * z), -1, 1))
        k1 = np.arccos(np.clip((R * R + z * z - p * p) / (2 * R * z), -1, 1))
        sq = np.sqrt(np.clip(4 * z * z * R * R - (R * R + z * z - p * p) ** 2, 0, None))
        Ap = p * p * k0 + R * R * k1 - 0.5 * sq
    return np.where(part, Ap, A)


def model(t, tc, per, p, ars, inc_deg, u1=0.40, u2=0.25, texp=120 / 86400, nsub=3):
    """Relative flux; exposure smeared over texp with nsub sub-samples."""
    off = (np.arange(nsub) + 0.5) / nsub - 0.5
    tt = (t[:, None] + off[None, :] * texp).ravel()
    ph = 2 * np.pi * (tt - tc) / per
    inc = np.radians(inc_deg)
    z = ars * np.sqrt(np.sin(ph) ** 2 + (np.cos(inc) * np.cos(ph)) ** 2)
    z = np.where(np.cos(ph) > 0, z, 1e3)      # secondary side
    return flux_z(z, p, u1, u2).reshape(t.size, nsub).mean(1)
