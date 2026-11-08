"""Reproduce the cloud upload path against the active DB."""
import os, sys, shutil, tempfile, traceback, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT); sys.path.insert(0, str(ROOT))

from claimparser import ingest

SAMPLE = ROOT.parent / "CBPInsure-20261104T094959Z-1-001" / "CBPInsure" / \
    "KLEIN - GAIC" / "BILLS - KLEIN - 251420364" / "25016400-01.pdf"
tmp = Path(tempfile.mkdtemp(prefix="claims_"))
p = tmp / "25016400-01.pdf"
shutil.copy(SAMPLE, p)
try:
    s = ingest.ingest_upload(p, tmp / "work", print)
    print("UPLOAD OK:", s)
except Exception:
    traceback.print_exc()
