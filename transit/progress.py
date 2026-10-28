"""Progress reporting: console bar, RESULT\\<lauf>\\status.json (heartbeat), run.log, run_state.json, toast.

One process = one run. cli.main() calls start(); long loops use
    bar = progress.task("Photometrie", n_frames, "Frames"); ... bar.update(); ... bar.done()
Without start() (e.g. imported elsewhere) every call is a no-op apart from the console bar.
"""
import base64
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import threading
import time

STATUS = "status.json"
STATE = "run_state.json"
RUNLOG = "run.log"
HANG_S = 120            # heartbeat older than this -> "haengt?"
STALL_S = 900           # no progress for this long (process alive) -> "steht?"

_lock = threading.RLock()
_S = dict(m=None, verbose=False, cmd="", t0=0.0, interval=10.0, task=None, steps=[], state="idle", tty=False,
          last_draw=0.0, last_line_pct=-1, last_line_t=0.0, bar_on=False, last_progress=0.0, thread=None, stop=None,
          result=None, error=None)


# ------------------------------------------------------------------ time helpers
def tzname(t=None):
    lt = time.localtime(t)
    off = lt.tm_gmtoff // 60
    if off == 120:
        return "CEST"
    if off == 60:
        return "CET"
    return f"UTC{off // 60:+d}" if off % 60 == 0 else f"UTC{off / 60:+.1f}"


def clock(t, with_date=None):
    """10:23 CEST (with date if not today)."""
    if t is None:
        return "-"
    lt = time.localtime(t)
    if with_date is None:
        with_date = time.strftime("%Y-%m-%d", lt) != time.strftime("%Y-%m-%d")
    return time.strftime("%d.%m. %H:%M" if with_date else "%H:%M:%S", lt) + " " + tzname(t)


def iso(t):
    return None if t is None else time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t)) + f" {tzname(t)}"


def dur(s):
    if s is None or s != s:
        return "-"
    s = int(round(s))
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s // 60}:{s % 60:02d} min"
    return f"{s // 3600}:{s % 3600 // 60:02d} h"


# ------------------------------------------------------------------ files
def _write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, ensure_ascii=False)
    for _ in range(5):                      # a reader (transit status) may hold the file for a moment
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.1)


def runlog(msg, level="INFO"):
    m = _S["m"]
    if m is None:
        return
    try:
        with open(os.path.join(m.out, RUNLOG), "a", encoding="utf-8") as fh:
            for line in str(msg).splitlines() or [""]:
                fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {level:5s} {line}\n")
    except OSError:
        pass


def debug(msg):
    """Only with --verbose: console + run.log."""
    if not _S["verbose"]:
        return
    with _lock:
        clear_line()
        print(f"  [debug] {msg}", flush=True)
    runlog(msg, "DEBUG")


# ------------------------------------------------------------------ status.json
def snapshot():
    t = _S["task"]
    now = time.time()
    d = dict(command=_S["cmd"], state=_S["state"], pid=os.getpid(), started=iso(_S["t0"]), heartbeat=iso(now),
             heartbeat_unix=now, last_progress_unix=_S["last_progress"] or _S["t0"], elapsed_s=round(now - _S["t0"], 1),
             steps=_S["steps"], result=_S["result"], error=_S["error"])
    if t is not None:
        d.update(task=t.name, done=t.n, total=t.total, unit=t.unit, percent=round(t.pct(), 1),
                 eta_s=None if t.eta() is None else round(t.eta()), eta_local=clock(t.eta_abs()),
                 eta_unix=t.eta_abs(), task_elapsed_s=round(now - t.t0, 1), eta_includes=t.then or None)
    cur = next((s for s in _S["steps"] if s["state"] == "laeuft"), None)
    if cur:
        d["step"] = cur["name"]
        d["step_no"] = _S["steps"].index(cur) + 1
        d["n_steps"] = len(_S["steps"])
    return d


def write_status():
    m = _S["m"]
    if m is None:
        return
    with _lock:
        d = snapshot()
    try:
        _write_json(os.path.join(m.out, STATUS), d)
    except OSError:
        pass


def _beat(stop):
    while not stop.wait(_S["interval"]):
        write_status()


# ------------------------------------------------------------------ console bar
def clear_line():
    if _S["bar_on"]:
        sys.stderr.write("\r" + " " * 100 + "\r"); sys.stderr.flush()
        _S["bar_on"] = False


def _draw(t, force=False):
    now = time.time()
    pct = t.pct()
    if _S["tty"]:
        if not force and now - _S["last_draw"] < 0.25:
            return
        _S["last_draw"] = now
        w = 28
        k = int(w * pct / 100)
        eta = t.eta()
        txt = (f"\r  {t.name[:22]:22s} [{'#' * k}{'.' * (w - k)}] {pct:5.1f}%  {t.n}/{t.total} {t.unit}  "
               f"Rest {dur(eta)}" + (f" inkl. {t.then}" if t.then else "") + (f" (fertig ~{clock(t.eta_abs())})" if eta else ""))
        sys.stderr.write(txt[:118].ljust(100)); sys.stderr.flush()
        _S["bar_on"] = True
    else:                                    # redirected output: one line per 10 % or per minute
        step = int(pct // 10)
        if force or step > _S["last_line_pct"] or now - _S["last_line_t"] > 60:
            _S["last_line_pct"], _S["last_line_t"] = step, now
            eta = t.eta()
            print(f"  .. {t.name}: {pct:5.1f}% ({t.n}/{t.total} {t.unit}), Rest {dur(eta)}" + (f" inkl. {t.then}" if t.then else "")
                  + (f", fertig ~{clock(t.eta_abs())}" if eta else ""), flush=True)


class Task:
    def __init__(self, name, total, unit="", then_s=0.0, then=""):
        self.name, self.total, self.unit = name, max(int(total), 1), unit
        self.n, self.t0 = 0, time.time()
        self.then_s, self.then = float(then_s or 0), then     # estimated seconds of the following sub-task (e.g. MCMC)

    def pct(self):
        return min(100.0, 100.0 * self.n / self.total)

    def eta(self):
        if self.n <= 0:
            return None
        el = time.time() - self.t0
        return max(0.0, el / self.n * (self.total - self.n)) + self.then_s

    def eta_abs(self):
        e = self.eta()
        return None if e is None else time.time() + e

    def update(self, k=1, n=None):
        with _lock:
            self.n = n if n is not None else self.n + k
            _S["last_progress"] = time.time()
            _draw(self)

    def done(self):
        with _lock:
            self.n, self.then_s = self.total, 0.0
            if _S["tty"] or _S["last_line_pct"] < 10:
                _draw(self, force=True)
            clear_line()
            if _S["task"] is self:
                _S["task"] = None
        debug(f"{self.name}: fertig in {dur(time.time() - self.t0)}")
        write_status()


def task(name, total, unit="", then_s=0.0, then=""):
    t = Task(name, total, unit, then_s, then)
    with _lock:
        _S["task"] = t
        _S["last_line_pct"] = -1
        _S["last_progress"] = time.time()
    debug(f"{name}: {t.total} {unit}")
    write_status()
    return t


# ------------------------------------------------------------------ steps (one command or the steps of 'run')
def plan(names):
    with _lock:
        _S["steps"] = [dict(name=n, state="offen", start=None, end=None, duration_s=None) for n in names]
    write_status()


def step_begin(name):
    with _lock:
        s = next((x for x in _S["steps"] if x["name"] == name), None)
        if s is None:
            s = dict(name=name, state="offen", start=None, end=None, duration_s=None); _S["steps"].append(s)
        s.update(state="laeuft", start=iso(time.time()), _t=time.time())
        _S["last_progress"] = time.time()
    runlog(f"===== Schritt {name}: Start")
    write_status()


def step_end(name, state="fertig"):
    with _lock:
        s = next((x for x in _S["steps"] if x["name"] == name), None)
        if s is None:
            return
        t = s.pop("_t", None)
        s.update(state=state, end=iso(time.time()), duration_s=None if t is None else round(time.time() - t, 1))
        _S["task"] = None
    runlog(f"===== Schritt {name}: {state}" + (f" ({dur(s['duration_s'])})" if s["duration_s"] is not None else ""))
    write_status()


def step_skip(name, why):
    with _lock:
        s = next((x for x in _S["steps"] if x["name"] == name), None)
        if s is not None:
            s.update(state="uebersprungen", note=why)
    runlog(f"===== Schritt {name}: uebersprungen ({why})")


# ------------------------------------------------------------------ process lifetime
def start(m, cmd, verbose=False):
    pc = m.cfg.get("progress", {})
    global HANG_S
    HANG_S = float(pc.get("hang_after_s", HANG_S))
    _S.update(m=m, cmd=cmd, verbose=verbose, t0=time.time(), state="laeuft", interval=float(pc.get("status_interval_s", 10)),
              tty=sys.stderr.isatty(), last_progress=time.time(), steps=[], result=None, error=None)
    runlog(f"##### transit {cmd}  (pid {os.getpid()}, {' '.join(sys.argv[1:])})")
    write_status()
    stop = threading.Event()
    th = threading.Thread(target=_beat, args=(stop,), daemon=True)
    th.start()
    _S["thread"], _S["stop"] = th, stop


def finish(ok=True, error=None, result=None):
    if _S["stop"] is not None:
        _S["stop"].set()
    with _lock:
        clear_line()
        for s in _S["steps"]:
            if s["state"] == "laeuft":
                s.pop("_t", None); s["state"] = "abgebrochen" if not ok else "fertig"
        _S["state"] = "fertig" if ok else "fehler"
        _S["error"], _S["result"], _S["task"] = error, result, None
    runlog(f"##### Ende: {_S['state']} nach {dur(time.time() - _S['t0'])}" + (f" - {error}" if error else ""))
    write_status()


def elapsed():
    return time.time() - _S["t0"]


def steps():
    return list(_S["steps"])


# ------------------------------------------------------------------ resume bookkeeping (run_state.json)
# step -> config sections that influence its result; a change there invalidates the step (and all later ones)
CFG_DEPS = dict(inventory=["target", "site", "planning"], calibrate=["calib"],
                cube=["camera", "photometry", "comps", "site"], compsearch=["search"], fit=["fit"], export=[], report=["report", "observer"])


def cfg_hash(cfg, sections):
    sub = {k: cfg.get(k) for k in sections}
    return hashlib.sha1(json.dumps(sub, sort_keys=True, default=str).encode()).hexdigest()[:12]


def load_state(m):
    p = os.path.join(m.out, STATE)
    try:
        return json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def mark_done(m, step, params, outputs):
    st = load_state(m)
    st[step] = dict(finished=iso(time.time()), finished_unix=time.time(), params=params,
                    cfg=cfg_hash(m.cfg, CFG_DEPS.get(step, [])), outputs=outputs)
    try:
        _write_json(os.path.join(m.out, STATE), st)
    except OSError:
        pass


# ------------------------------------------------------------------ is a pid alive (Windows, no os.kill: that would terminate it)
def pid_alive(pid):
    if not pid:
        return None
    if os.name != "nt":
        try:
            os.kill(pid, 0); return True
        except OSError:
            return False
    try:
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, int(pid))      # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259             # STILL_ACTIVE
    except Exception:
        return None


# ------------------------------------------------------------------ Windows toast (Windows PowerShell 5.1, nothing to install)
def toast(title, text):
    if os.name != "nt":
        return False
    esc = lambda s: str(s).replace("'", "''")
    ps = ("$ErrorActionPreference='Stop';"
          "[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime]>$null;"
          "$t=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
          "[Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
          "$x=$t.GetElementsByTagName('text');"
          f"$x.Item(0).AppendChild($t.CreateTextNode('{esc(title)}'))>$null;"
          f"$x.Item(1).AppendChild($t.CreateTextNode('{esc(text)}'))>$null;"
          "$id='{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe';"
          "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($id).Show("
          "[Windows.UI.Notifications.ToastNotification]::new($t))")
    enc = base64.b64encode(ps.encode("utf-16-le")).decode()
    exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    try:
        r = subprocess.run([exe, "-NoProfile", "-NonInteractive", "-EncodedCommand", enc], capture_output=True, timeout=20,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode != 0:
            debug(f"Toast fehlgeschlagen: {r.stderr.decode(errors='replace')[:200]}")
        return r.returncode == 0
    except Exception as e:
        debug(f"Toast nicht moeglich: {e}")
        return False
