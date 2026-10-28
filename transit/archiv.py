"""transit archiv <Messordner> --ziel <Pfad> [--probe] [--loeschen]

Copies a whole measurement folder to an archive (e.g. the NAS), verifies SHA-256 of every file at the target, records the
archive path in _pipeline\\logbuch.csv and deletes the local original only with --loeschen and only after every file
matched.  Everything the pipeline needs later (O-C history, valid Tc with errors, ensemble, run names) lives in the logbook.
"""
import hashlib
import json
import os
import shutil
import time

from . import progress
from .config import LIGHT_DIR_NAMES, PIPE_DIR, find_lights

CHUNK = 4 << 20
MANIFEST = "archiv_manifest.json"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(CHUNK), b""):
            h.update(blk)
    return h.hexdigest()


def gb(n):
    return f"{n / 1e9:.1f} GB"


def inside(a, b):
    """True if path a is b or inside b."""
    a, b = os.path.normcase(os.path.abspath(a)), os.path.normcase(os.path.abspath(b))
    try:
        return os.path.commonpath([a, b]) == b
    except ValueError:                                     # different drives
        return False


def cmd_archiv(a):
    from .ergebnisblatt import logbook_backfill, logbook_read, logbook_set_archive
    src = os.path.abspath(a.messordner)
    name = os.path.basename(src.rstrip("\\/"))
    dst = os.path.join(os.path.abspath(a.ziel), name)
    # ---------------- safety checks
    if not os.path.isdir(src):
        raise SystemExit(f"Messordner nicht gefunden: {src}")
    if find_lights(src) is None:
        raise SystemExit(f"{src} ist kein Messordner (kein {'/'.join(LIGHT_DIR_NAMES)}) - abgebrochen")
    if inside(PIPE_DIR, src) or inside(src, PIPE_DIR):
        raise SystemExit("Der Werkzeug-Ordner _pipeline darf nicht archiviert werden")
    if inside(a.ziel, src):
        raise SystemExit("Ziel liegt im Messordner - abgebrochen")
    if inside(src, a.ziel) and os.path.normcase(os.path.dirname(src)) == os.path.normcase(os.path.abspath(a.ziel)):
        raise SystemExit("Ziel ist der Ordner, in dem die Messung schon liegt - abgebrochen")
    files = []
    for dp, dn, fn in os.walk(src):
        for f in fn:
            p = os.path.join(dp, f)
            files.append((os.path.relpath(p, src), os.path.getsize(p)))
    total = sum(s for _, s in files)
    runs = [r for r in logbook_read() if os.path.normcase(r["messordner"]) == os.path.normcase(src)]
    print(f"Quelle : {src}  ({len(files)} Dateien, {gb(total)})")
    print(f"Ziel   : {dst}")
    print(f"Logbuch: {len(runs)} Lauf/Laeufe ({', '.join(sorted(r['lauf'] + ('*' if r['status'] == 'gueltig' else '') for r in runs)) or '-'};"
          " * = gueltig)")
    if not os.path.isdir(os.path.abspath(a.ziel)):
        msg = f"Ziel-Ordner {a.ziel} nicht erreichbar (NAS verbunden?)"
        if a.probe:
            print("  WARNUNG: " + msg)
        else:
            raise SystemExit(msg)
    else:
        free = shutil.disk_usage(os.path.abspath(a.ziel)).free
        print(f"Frei am Ziel: {gb(free)}" + ("  -> REICHT NICHT" if free < total * 1.02 else ""))
        if free < total * 1.02 and not a.probe:
            raise SystemExit("Zu wenig Platz am Ziel")
    exist = os.path.isdir(dst)
    if exist:
        print(f"Ziel existiert bereits: vorhandene Dateien gleicher Groesse werden nur geprueft, nicht neu kopiert")
    if a.probe:
        print("\nTROCKENLAUF - es wuerde passieren:")
        print(f"  1. Logbuch-Spalten der {len(runs)} Laeufe aus fit.json nachtragen (Tc, Fehler, Drift, Ephemeride, Upload-Datei)")
        print(f"  2. {len(files)} Dateien ({gb(total)}) nach {dst} kopieren")
        print(f"  3. SHA-256 jeder Datei an Quelle und Ziel vergleichen, {MANIFEST} am Ziel schreiben")
        print(f"  4. Archivpfad im Logbuch eintragen")
        print("  5. " + ("lokales Original LOESCHEN, nur wenn alle Pruefsummen stimmen" if a.loeschen
                         else "lokales Original BLEIBT (zum Loeschen: --loeschen)"))
        return
    # ---------------- 1. logbook first: everything later nights need stays in _pipeline
    logbook_backfill(src)
    # ---------------- 2. copy
    t0 = time.time()
    bar = progress.task("Kopieren", max(total, 1), "Bytes")
    done = 0
    for rel, size in files:
        s, d = os.path.join(src, rel), os.path.join(dst, rel)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        if not (os.path.exists(d) and os.path.getsize(d) == size):
            shutil.copy2(s, d)
        done += size
        bar.update(n=done)
    bar.done()
    print(f"Kopiert in {progress.dur(time.time() - t0)}")
    # ---------------- 3. verify every file (full SHA-256 at both ends)
    bar = progress.task("Pruefen", max(total, 1), "Bytes")
    bad, man, done = [], {}, 0
    for rel, size in files:
        hs, hd = sha256(os.path.join(src, rel)), sha256(os.path.join(dst, rel))
        man[rel] = dict(size=size, sha256=hs)
        if hs != hd:
            bad.append(rel)
        done += size
        bar.update(n=done)
    bar.done()
    with open(os.path.join(dst, MANIFEST), "w", encoding="utf-8") as fh:
        json.dump(dict(quelle=src, ziel=dst, datum=time.strftime("%Y-%m-%d %H:%M"), dateien=man), fh, indent=0)
    if bad:
        print(f"FEHLER: {len(bad)} Datei(en) am Ziel weichen ab, z. B. {bad[:5]}. Nichts geloescht, Logbuch unveraendert.")
        raise SystemExit(1)
    print(f"Alle {len(files)} Pruefsummen stimmen ({gb(total)}). Manifest: {os.path.join(dst, MANIFEST)}")
    # ---------------- 4. logbook
    k = logbook_set_archive(src, dst)
    print(f"Logbuch: Archivpfad bei {k} Lauf/Laeufen eingetragen")
    # ---------------- 5. delete only on request
    if a.loeschen:
        shutil.rmtree(src)
        print(f"Lokales Original geloescht: {src}")
    else:
        print(f"Lokales Original bleibt: {src}  (loeschen: transit archiv ... --loeschen; prueft vorher erneut alles)")
