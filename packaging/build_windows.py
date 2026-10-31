"""Build the portable Windows package (ZIP) - Python, all packages and the transit code in one folder.

Runs on Windows, Linux or in GitHub Actions; all wheels are downloaded for win_amd64 regardless of the build machine.
    python packaging/build_windows.py            ->  dist/exopipeline-<version>-windows.zip

Python itself comes from the official NuGet package "python" (python.org build, no installer, no admin rights).
User data (config.local.toml, cache/, logbuch.csv, plan/) is not in the ZIP, so a new version can simply be
unpacked over the old folder.
"""
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

PY_VERSION = "3.12.10"
PY_TAG = "312"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
DIST = os.path.join(ROOT, "dist")
NAME = "exopipeline"
FILES = ["transit.cmd", "transit_gui.cmd", "transit_gui_klassisch.cmd", "HANDBUCH.md", "README.md", "LICENSE", "config.example.toml",
         "aij_vorlage.plotcfg", "requirements.txt"]


def version():
    ns = {}
    with open(os.path.join(ROOT, "transit", "__init__.py"), encoding="utf-8") as f:
        exec(f.read(), ns)
    return ns["__version__"]


def fetch_python():
    os.makedirs(BUILD, exist_ok=True)
    pkg = os.path.join(BUILD, f"python.{PY_VERSION}.nupkg")
    if not os.path.exists(pkg):
        url = f"https://api.nuget.org/v3-flatcontainer/python/{PY_VERSION}/python.{PY_VERSION}.nupkg"
        print("lade", url)
        urllib.request.urlretrieve(url, pkg + ".part")
        os.replace(pkg + ".part", pkg)
    return pkg


def crlf(src, dst):
    with open(src, encoding="utf-8") as f:
        text = f.read().replace("\r\n", "\n")
    with open(dst, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(text)


def main():
    ver = version()
    out = os.path.join(BUILD, NAME)
    if os.path.exists(out):
        shutil.rmtree(out)
    py = os.path.join(out, "python")

    # 1. Python (tools/ of the NuGet package = complete python.org layout incl. pip)
    with zipfile.ZipFile(fetch_python()) as z:
        for m in z.infolist():
            if m.filename.startswith("tools/") and not m.is_dir():
                dst = os.path.join(py, *m.filename[len("tools/"):].split("/"))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with z.open(m) as s, open(dst, "wb") as d:
                    shutil.copyfileobj(s, d)

    # 2. packages as Windows wheels straight into site-packages.  uv evaluates environment markers for the target
    #    (Windows, Python 3.12); plain pip evaluates them for the build machine, so without uv build on Windows/3.12.
    site = os.path.join(py, "Lib", "site-packages")
    req = os.path.join(ROOT, "requirements.txt")
    uv = shutil.which("uv")
    if uv:
        subprocess.check_call([uv, "pip", "install", "--target", site, "--python-platform", "x86_64-pc-windows-msvc",
                               "--python-version", PY_VERSION, "--only-binary", ":all:", "--no-compile", "-r", req])
    else:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-compile",
                               "--target", site, "--platform", "win_amd64", "--python-version", PY_TAG,
                               "--implementation", "cp", "--abi", f"cp{PY_TAG}", "--only-binary=:all:", "-r", req])

    # 3. transit code and documents; .cmd/.txt with CRLF for Windows
    shutil.copytree(os.path.join(ROOT, "transit"), os.path.join(out, "transit"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for n in FILES:
        if n.endswith(".cmd"):
            crlf(os.path.join(ROOT, n), os.path.join(out, n))
        else:
            shutil.copy2(os.path.join(ROOT, n), os.path.join(out, n))
    crlf(os.path.join(ROOT, "packaging", "LIESMICH.txt"), os.path.join(out, "LIESMICH.txt"))

    # 4. ZIP with a top-level folder "exopipeline"
    os.makedirs(DIST, exist_ok=True)
    zpath = os.path.join(DIST, f"{NAME}-{ver}-windows.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for d, _, files in os.walk(out):
            for f in files:
                p = os.path.join(d, f)
                z.write(p, os.path.relpath(p, BUILD))
    print(f"fertig: {zpath} ({os.path.getsize(zpath) / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
