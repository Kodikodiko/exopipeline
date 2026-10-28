"""Read-only protection for the light frames.

* guard_write(path): refuses any write target inside the light folder.
* checksums: fast fingerprint (size, mtime, SHA-256 of the first and last 64 KiB) or full SHA-256,
  stored in RESULT\\lights_checksums.json; every command checks it before and after running.
"""
import glob
import hashlib
import json
import os

CHUNK = 65536


class ReadOnlyViolation(RuntimeError):
    pass


def guard_write(m, path):
    p = os.path.abspath(path)
    nc = os.path.normcase
    if nc(m.lights) == nc(m.root):                        # FITS directly in the measurement folder: only subfolders
        if nc(os.path.dirname(p)) == nc(m.root):           # (RESULT, SOLVED, ...) may be written, never the folder itself
            raise ReadOnlyViolation(f"Schreiben neben die Lights ist verboten: {p}")
    elif os.path.commonpath([p, m.lights]) == m.lights:
        raise ReadOnlyViolation(f"Schreiben in den Light-Ordner ist verboten: {p}")
    return p


def light_files(m):
    from .config import FITS_EXT
    return sorted(f for f in glob.glob(os.path.join(m.lights, "*.f*")) if f.lower().endswith(FITS_EXT))


def fingerprint(path, full=False):
    st = os.stat(path)
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        if full:
            for blk in iter(lambda: fh.read(1 << 20), b""):
                h.update(blk)
        else:
            h.update(fh.read(CHUNK))
            if st.st_size > 2 * CHUNK:
                fh.seek(-CHUNK, os.SEEK_END)
                h.update(fh.read(CHUNK))
    return dict(size=st.st_size, mtime=st.st_mtime, sha256=h.hexdigest(), full=full)


def snapshot(m, full=False):
    return {os.path.basename(f): fingerprint(f, full) for f in light_files(m)}


def checksum_file(m):
    return os.path.join(m.result, "lights_checksums.json")


def record(m, full=False):
    os.makedirs(m.result, exist_ok=True)
    snap = snapshot(m, full)
    with open(checksum_file(m), "w") as fh:
        json.dump(snap, fh, indent=0)
    return snap


def verify(m, stage=""):
    """Compare current fast fingerprints with the stored ones. Raises on any change."""
    cf = checksum_file(m)
    if not os.path.exists(cf):
        record(m)
        return "angelegt"
    ref = json.load(open(cf))
    cur = snapshot(m, full=False)
    bad = []
    for k, v in ref.items():
        c = cur.get(k)
        if c is None:
            bad.append(f"{k}: fehlt")
        elif c["size"] != v["size"] or (not v.get("full") and c["sha256"] != v["sha256"]):
            bad.append(f"{k}: veraendert")
    new = sorted(set(cur) - set(ref))
    if ref and not cur:                                    # folder emptied from outside (moved to the NAS?)
        raise ReadOnlyViolation(f"Keine der {len(ref)} Light-Dateien liegt mehr in {m.lights} - Ordner verschoben? "
                                "Den Ordner waehlen, in dem die Lights jetzt liegen (z. B. am NAS). Es wurde nichts veraendert.")
    if bad:
        raise ReadOnlyViolation(f"Light-Dateien veraendert ({stage}): " + "; ".join(bad[:10]))
    return f"ok ({len(ref)} Dateien" + (f", {len(new)} neu" if new else "") + ")"
