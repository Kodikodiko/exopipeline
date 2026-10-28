"""Configuration: global defaults merged with the per-measurement RESULT\\transit.toml."""
import copy
import os
import tomllib

PIPE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# global defaults: own config.local.toml (not in git) wins, then config_default.toml (older installations), else the example
DEFAULT_TOML = next((p for p in (os.path.join(PIPE_DIR, n) for n in ("config.local.toml", "config_default.toml"))
                     if os.path.exists(p)), os.path.join(PIPE_DIR, "config.example.toml"))
LIGHT_DIR_NAMES = ("LIGHTS", "LIGHT", "LIGHT work", "_work", "_orig", "orig")     # original light frames, read-only (first found wins)
OUT_DIRS = ("CALIBRATED", "SOLVED", "AIJ", "RESULT")


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


FITS_EXT = (".fit", ".fits", ".fts")


def find_lights(root):
    """Light folder of a measurement: the first known subfolder, else the folder itself if FITS files lie directly in it
    (then only those files are read; outputs still go to subfolders).  None = no measurement."""
    if not os.path.isdir(root):
        return None
    subs = [os.path.join(root, n) for n in LIGHT_DIR_NAMES if os.path.isdir(os.path.join(root, n))]
    for p in subs + [root]:                                # first place that really holds FITS files
        try:
            fs = sorted(f for f in os.listdir(p) if f.lower().endswith(FITS_EXT))
        except OSError:
            continue
        if fs and p == root and not subs:                  # FITS directly in the folder: not a folder of darks/flats/biases
            try:
                from astropy.io import fits
                typ = str(fits.getheader(os.path.join(p, fs[len(fs) // 2])).get("IMAGETYP", "LIGHT")).upper()
                if any(w in typ for w in ("BIAS", "DARK", "FLAT", "OFFSET")):
                    continue
            except Exception:
                pass
        if fs:
            return p
    return subs[0] if subs else None                       # empty light folder: still a measurement (0 frames)


def unwrap(p, depth=2):
    """A folder that only wraps the real measurement (e.g. WASP-135b/WASP-135b/LIGHT): step into its single
    subfolder until lights are found.  Returns p unchanged if that does not lead to a measurement."""
    q = p
    ok = lambda x: find_lights(x) is not None or os.path.isdir(os.path.join(x, "RESULT"))    # lights or results
    for _ in range(depth):
        if ok(q) or not os.path.isdir(q):
            break
        subs = [d for d in os.listdir(q) if os.path.isdir(os.path.join(q, d)) and not d.startswith((".", "_")) and d.upper() != "RESULT"]
        if len(subs) != 1:
            break
        q = os.path.join(q, subs[0])
    return q if ok(q) else p


class Measurement:
    """One observing night: <root>\\{LIGHTS|_work} read-only, outputs in CALIBRATED/SOLVED/AIJ/RESULT."""

    def __init__(self, root, out_sub="pipeline"):
        self.root = os.path.abspath(root)
        if not os.path.isdir(self.root):
            raise SystemExit(f"Messordner nicht gefunden: {self.root}")
        self.lights = find_lights(self.root)
        if self.lights is None:
            raise SystemExit(f"Kein Light-Ordner ({', '.join(LIGHT_DIR_NAMES)}) und keine FITS-Dateien in {self.root}")
        self.result = os.path.join(self.root, "RESULT")
        self.out = os.path.join(self.result, out_sub)      # where this tool writes its products
        self.cfg_path = os.path.join(self.result, "transit.toml")
        self.reports = os.path.join(self.root, "_reports")
        with open(DEFAULT_TOML, "rb") as fh:
            cfg = tomllib.load(fh)
        if os.path.exists(self.cfg_path):
            with open(self.cfg_path, "rb") as fh:
                cfg = _merge(cfg, tomllib.load(fh))
        self.run_cfg_path = os.path.join(self.out, "lauf.toml")     # settings for this run only (e.g. excluded stars)
        if os.path.exists(self.run_cfg_path):
            with open(self.run_cfg_path, "rb") as fh:
                cfg = _merge(cfg, tomllib.load(fh))
        self.cfg = cfg

    def dir(self, kind):
        """Output directory (created on demand); kind in CALIBRATED/SOLVED/AIJ/RESULT/out."""
        p = self.out if kind == "out" else os.path.join(self.root, kind)
        os.makedirs(p, exist_ok=True)
        return p

    def path(self, name):
        return os.path.join(self.dir("out"), name)


def write_measurement_toml(m, target_name, ra, dec, planet, extra=None):
    """Create RESULT\\transit.toml if missing (never overwrites)."""
    if os.path.exists(m.cfg_path):
        return False
    os.makedirs(m.result, exist_ok=True)
    lines = ["# Einstellungen fuer diese Messung (ueberschreiben config.local.toml).", "",
             "[target]", f'name = "{target_name}"', f"ra = {ra}", f"dec = {dec}", f'planet = "{planet}"', ""]
    for sec, vals in (extra or {}).items():
        lines.append(f"[{sec}]")
        for k, v in vals.items():
            lines.append(f"{k} = {v!r}".replace("'", '"') if isinstance(v, str) else f"{k} = {v}")
        lines.append("")
    with open(m.cfg_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return True
