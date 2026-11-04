"""A/B OCR comparison on the Klein case, scored against the accumulator spreadsheet
(ground truth). Prints per-engine counts of correctly-parsed service-line charges.

  python tools/compare_ocr.py
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from claimparser import config
from claimparser.ingest import parse_bill_pdf
from claimparser.ocr import active_engine

ROOT = config.DEFAULT_SAMPLES / "KLEIN - GAIC"
BILLS = ROOT / "BILLS - KLEIN - 251420364"
ACC = BILLS / "CLAIMS ACCUM - KLEIN - 251420364.xls"


def truth() -> set[tuple[str, float]]:
    df = pd.read_excel(ACC)
    out = set()
    for _, r in df.iterrows():
        cpt = str(r["ProcedureCode"]).strip()
        out.add((cpt, round(float(r["TotalCharges"]), 2)))
    return out


def run(engine: str) -> dict:
    config.set_engine(engine)
    eng = active_engine()
    pairs, charged = set(), 0
    for f in sorted(BILLS.glob("25016400-*.pdf")):
        parsed = parse_bill_pdf(f)["parsed"]
        for ln in parsed["lines"]:
            if ln.get("cpt_code"):
                pairs.add((ln["cpt_code"], round(ln["charge_amount"], 2) if ln.get("charge_amount") else None))
                if ln.get("charge_amount"):
                    charged += 1
    return {"engine": eng, "lines": len(pairs), "with_charge": charged, "pairs": pairs}


def main() -> None:
    gt = truth()
    print(f"Accumulator ground-truth (cpt, charge) pairs: {len(gt)}\n")
    rows = []
    for e in ("rapidocr", "tesseract"):
        r = run(e)
        matched = len(r["pairs"] & gt)
        cpt_only = len({c for c, _ in r["pairs"]} & {c for c, _ in gt})
        rows.append({"engine": r["engine"], "parsed_lines": r["lines"], "lines_with_charge": r["with_charge"],
                     "cpt+charge matched": matched, "cpt matched": cpt_only})
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
