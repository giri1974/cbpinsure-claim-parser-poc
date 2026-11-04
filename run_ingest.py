"""CLI: parse the sample claim folders and load them into SQL Server LocalDB.

  python run_ingest.py                      # ingest default sample folder
  python run_ingest.py --path <folder>      # ingest another folder
  python run_ingest.py --reset              # wipe tables first
  python run_ingest.py --dry-run            # parse only, print JSON, no DB writes
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from claimparser import config, db, ingest
from claimparser.config import DEFAULT_SAMPLES


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=str(DEFAULT_SAMPLES))
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--db", choices=["local", "cloud"], help="target database (default: auto)")
    a = ap.parse_args()
    if a.db:
        config.set_mode(a.db)
    root = Path(a.path)

    if a.dry_run:
        for case_dir in ingest.discover_cases(root):
            case = ingest.process_case(case_dir)
            for c in case["claims"]:
                print(json.dumps({"claim": c["row"], "lines": c["lines"]}, indent=1, default=str))
        return

    ok, msg = db.test_connection()
    print(msg)
    if not ok:
        sys.exit(1)
    summary = ingest.ingest_root(root, reset=a.reset)
    print("\nDONE:", summary)


if __name__ == "__main__":
    main()
