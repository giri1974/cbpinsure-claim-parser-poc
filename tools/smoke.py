"""Smoke-test a Streamlit page with AppTest: report exceptions, errors, tabs.

  python tools/smoke.py app.py
  python tools/smoke.py pages/document_viewer.py --doc 176
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("page")
    ap.add_argument("--doc")
    ap.add_argument("--click-tabs", action="store_true")
    a = ap.parse_args()

    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(a.page, default_timeout=180)
    if a.doc:
        at.query_params["doc"] = a.doc
    # simulate a signed-in admin so the login gate doesn't block the smoke test
    at.session_state["auth_user"] = {"username": "admin", "role": "admin"}
    at.run()

    exc = [str(e.value)[:200] for e in at.exception]
    err = [e.value[:160] for e in at.error]
    print("PAGE:", a.page)
    print("exceptions:", exc)
    print("errors:", err)
    try:
        print("tabs:", [t.label for t in at.tabs])
    except Exception:
        pass
    print("dataframes:", len(at.dataframe), "buttons:", len(at.button), "selectboxes:", len(at.selectbox))
    sys.exit(1 if exc or err else 0)


if __name__ == "__main__":
    main()
