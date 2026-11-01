"""Find measurements by path or name, in the local working folder (...\\auto) and on the NAS ([paths] archiv_wurzel),
both recursively.  A measurement is a folder with lights (see config.find_lights) or with a RESULT folder.

The local tree is scanned on every call (fast); the NAS list is cached in _pipeline\\cache\\nas_index.json and rebuilt
when it is older than 5 min and a name is not in it, or on request (GUI "Aktualisieren").  Names compare as
case-insensitive substrings without punctuation; HAT-P-42b = HAT-42b = HAT42b; the planet name in RESULT\\transit.toml
also counts.  Several hits: the console lists them to choose from, the GUI shows buttons.
"""
import json
import os
import re
import sys
import time
import tomllib

from .config import DEFAULT_TOML, PIPE_DIR, find_lights, unwrap

BASE = os.path.dirname(PIPE_DIR)                           # ...\auto
INDEX = os.path.join(PIPE_DIR, "cache", "nas_index.json")
DEPTH = 5                                                  # folder levels below each root
SKIP = {"RESULT", "SOLVED", "CALIBRATED", "AIJ", "CACHE"}  # never measurements themselves


def nas_root():
    try:
        return tomllib.load(open(DEFAULT_TOML, "rb")).get("paths", {}).get("archiv_wurzel", "")
    except Exception:
        return ""


def key(s):
    k = re.sub(r"[^a-z0-9]", "", str(s).lower())
    return re.sub(r"^([a-z]+)p(\d)", r"\1\2", k)          # HAT-P-42b -> hat42b, like HAT-42b


def is_measurement(p):
    return find_lights(p) is not None


def is_entry(p):
    return is_measurement(p) or os.path.isdir(os.path.join(p, "RESULT"))


def planet_of(p):
    try:
        return tomllib.load(open(os.path.join(p, "RESULT", "transit.toml"), "rb")).get("target", {}).get("planet", "")
    except Exception:
        return ""


def matches(p, k, planet=None):
    """Case-insensitive substring match on folder name or planet name (punctuation ignored, HAT-P-42b = HAT-42b)."""
    if not k:
        return False
    nm = os.path.basename(os.path.normpath(p))
    return any(k in x for x in (key(nm), re.sub(r"[^a-z0-9]", "", nm.lower()), key(planet if planet is not None else planet_of(p))))


def scan(root):
    """All measurements below root (does not descend into a measurement)."""
    found = []
    for d, subs, _ in os.walk(root):
        depth = os.path.relpath(d, root).count(os.sep) + (d != root)
        if d != root and is_entry(d):
            found.append(dict(pfad=d, planet=planet_of(d)))
            subs[:] = []
            continue
        subs[:] = [s for s in subs if not s.startswith(("_", ".")) and s.upper() not in SKIP] if depth < DEPTH else []
    return found


def nas_index(refresh=False, log=print):
    """Cached NAS list; refresh=True rebuilds it (at most every 5 min unless forced by refresh='force')."""
    root = nas_root()
    if not root:
        return []
    old = None
    if os.path.exists(INDEX):
        j = json.load(open(INDEX, encoding="utf-8"))
        old = j["messungen"] if j.get("wurzel") == root else None
    stale = not os.path.exists(INDEX) or time.time() - os.path.getmtime(INDEX) > 300
    if old is not None and not (refresh == "force" or (refresh and stale)):
        return old
    if not os.path.isdir(root):
        log(f"NAS nicht erreichbar: {root} - nur lokal gesucht")
        return old or []
    log(f"Durchsuche NAS {root} ...")
    found = scan(root)
    os.makedirs(os.path.dirname(INDEX), exist_ok=True)
    json.dump(dict(wurzel=root, erstellt=time.strftime("%Y-%m-%d %H:%M"), messungen=found),
              open(INDEX, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return found


def all_measurements(refresh=False, log=print):
    """[(path, 'lokal'|'NAS')] - local tree, NAS index and archive paths from the logbook."""
    from .ergebnisblatt import logbook_read
    out, seen = [], set()

    def add(p, ort):
        n = os.path.normcase(os.path.abspath(p))
        if n not in seen and os.path.isdir(p):
            seen.add(n); out.append((os.path.abspath(p), ort))
    for e in scan(BASE):
        add(e["pfad"], "lokal")
    for e in nas_index(refresh, log):
        add(e["pfad"], "NAS")
    for r in logbook_read():
        a = r.get("archiv") or ""
        if a and a != "-":
            add(a, "NAS")
    return out


def search(name, log=print):
    k = key(name)
    hits = [(p, o) for p, o in all_measurements(False, log) if matches(p, k)]
    if not hits:                                           # NAS list may be old: rebuild once (max. every 5 min)
        hits = [(p, o) for p, o in all_measurements(True, log) if matches(p, k)]
    return hits


def copies(root, log=lambda *x: None):
    """Other folders of the same measurement (archive path from the logbook first, then local/NAS folders of the same
    name), e.g. the NAS copy holding the lights when root only keeps RESULT.  Only folders that exist right now."""
    from .ergebnisblatt import logbook_read
    nc = lambda x: os.path.normcase(os.path.abspath(x))
    me, name = nc(root), os.path.basename(os.path.normpath(root)).lower()
    out = []

    def add(p):
        if p and p != "-" and nc(p) != me and nc(p) not in map(nc, out) and os.path.isdir(p):
            out.append(os.path.abspath(p))
    try:
        for r in logbook_read():
            if nc(r["messordner"]) == me:
                add(r.get("archiv"))
    except Exception:
        pass
    for refresh in (False, True):                          # NAS list may be old: rebuild once
        ms = [p for p, _ in all_measurements(refresh, log)]
        for p in ms:
            if os.path.basename(os.path.normpath(p)).lower() == name:
                add(p)
        if not out:                                        # name spelled differently (HAT-42b / HAT42b / HAT-P-42b):
            k = key(name)                                  # same planet key, and the same night when both are known
            for p in ms:
                if nc(p) != me and key(os.path.basename(os.path.normpath(p))) == k and same_night(root, p):
                    add(p)
        if len(out) > 0:
            break
    return out


def same_night(a, b):
    """True unless both folders have a known night and the nights differ."""
    try:
        from .gui import meta
        na, nb = meta(a)[1], meta(b)[1]
    except Exception:
        return True
    return not (na and nb and na != nb)


def ask(frage):
    try:
        return input(frage).strip().lower()
    except EOFError:                                       # no console (called from a script or the GUI)
        return None


def resolve(arg, nas=False):
    """Path of the measurement: the given path, else a name searched locally and on the NAS (nas: kept for compatibility)."""
    p = unwrap(os.path.abspath(arg))
    if is_entry(p):
        return p
    name = os.path.basename(os.path.normpath(arg))
    hits = search(name)
    if not hits:
        raise SystemExit(f"Messung '{arg}' weder lokal ({BASE}) noch am NAS ({nas_root()}) gefunden.")
    if len(hits) == 1:
        print(f"Messung gefunden ({hits[0][1]}): {hits[0][0]}")
        return hits[0][0]
    print(f"mehrere Messungen zu '{name}':")
    for i, (h, o) in enumerate(hits, 1):
        print(f"  {i}. [{o}] {h}")
    w = ask("Nummer waehlen (Enter = abbrechen): ") if sys.stdin.isatty() else None
    if w is None:
        raise SystemExit("Bitte den vollen Pfad angeben.")
    if not w.isdigit() or not 1 <= int(w) <= len(hits):
        raise SystemExit("Abgebrochen.")
    return hits[int(w) - 1][0]
