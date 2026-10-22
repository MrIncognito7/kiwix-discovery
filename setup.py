#!/usr/bin/env python3
"""Setup for Kiwix Discovery. Run:  python setup.py

Creates .venv, installs dependencies, downloads the Kiwix catalogue, builds the
local database and the semantic embeddings. Safe to re-run: finished steps are
skipped. To rebuild, delete data/catalog_enriched.db and/or data/.embeddings_built.

Then start the server yourself with uvicorn (see README).
"""
import gzip
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
DATA = ROOT / "data"
DB = DATA / "catalog_enriched.db"
EMBED_MARKER = DATA / ".embeddings_built"
OPDS_URL = "https://opds.library.kiwix.org/catalog/v2/entries?count=-1"
MIN_PY = (3, 10)


TOTAL_STEPS = 4
_step_no = 0


def bar(fraction, width=30):
    fraction = max(0.0, min(1.0, fraction))
    filled = int(width * fraction)
    return "[" + "#" * filled + "-" * (width - filled) + f"] {fraction * 100:3.0f}%"


def step(msg):
    global _step_no
    print(f"\n{bar(_step_no / TOTAL_STEPS)}  Step {_step_no + 1}/{TOTAL_STEPS}: {msg}", flush=True)
    _step_no += 1


def venv_python():
    sub = "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
    return VENV / sub


def run(*cmd):
    subprocess.run([str(c) for c in cmd], cwd=ROOT, check=True)


def download_catalogue(dest):
    req = urllib.request.Request(
        OPDS_URL, headers={"Accept-Encoding": "gzip", "User-Agent": "kiwix-discovery-setup"}
    )
    chunks, done = [], 0
    with urllib.request.urlopen(req, timeout=120) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        gzipped = resp.headers.get("Content-Encoding") == "gzip"
        while True:
            chunk = resp.read(64 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
            done += len(chunk)
            if total:
                print(f"\r    {bar(done / total)}  {done / 1e6:.1f}/{total / 1e6:.1f} MB", end="", flush=True)
            else:  # size unknown: show running total only
                print(f"\r    downloaded {done / 1e6:.1f} MB", end="", flush=True)
    print()
    raw = b"".join(chunks)
    if gzipped or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    dest.write_bytes(raw)
    print(f"    saved {len(raw) / 1e6:.1f} MB")


def main():
    if sys.version_info < MIN_PY:
        sys.exit(f"Python {MIN_PY[0]}.{MIN_PY[1]}+ required (found {sys.version.split()[0]}).")

    step("Virtual environment")
    if venv_python().exists():
        print("    .venv exists, reusing")
    else:
        run(sys.executable, "-m", "venv", VENV)
    py = venv_python()

    step("Dependencies")
    run(py, "-m", "pip", "install", "--quiet", "--upgrade", "pip")
    run(py, "-m", "pip", "install", "--progress-bar", "on", "-r", "requirements.txt")

    step("Catalogue database")
    DATA.mkdir(exist_ok=True)
    if DB.exists():
        print(f"    {DB.relative_to(ROOT)} exists, skipping")
    else:
        xml, tmp_db = ROOT / "catalog.xml", ROOT / "catalog.db"
        try:
            for f in (xml, tmp_db):
                f.unlink(missing_ok=True)
            print("    downloading Kiwix OPDS catalogue...")
            download_catalogue(xml)
            run(py, "scripts/ingest_catalog.py", xml, tmp_db)
            run(py, "scripts/enrich_catalog.py", tmp_db)
            shutil.copy(tmp_db, DB)
            EMBED_MARKER.unlink(missing_ok=True)  # new catalogue -> rebuild embeddings
        finally:
            for f in (xml, tmp_db):
                f.unlink(missing_ok=True)

    step("Semantic embeddings (first run downloads the model; this can take a while)")
    if EMBED_MARKER.exists():
        print("    already built, skipping")
    else:
        run(py, "scripts/build_embeddings.py")
        EMBED_MARKER.write_text("ok\n")

    print(f"\n{bar(1.0)}  Setup complete")
    activate = r".venv\Scripts\Activate.ps1" if sys.platform == "win32" else "source .venv/bin/activate"
    print(f"    Next:  {activate}")
    print("           uvicorn app:app --reload")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(f"\nSetup failed at: {' '.join(map(str, e.cmd))}")
    except KeyboardInterrupt:
        sys.exit("\nInterrupted.")
