"""Walks a claim-package folder, parses every document, assembles one 'case'
(policy + member + claimant + claims + line items) and writes it to SQL Server."""
from __future__ import annotations

import json
import re
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from . import db
from .config import MAX_FILES_PER_CASE
from .ocr import extract_pdf
from .parsers import (classify_page, parse_claim_form, parse_cms1500, parse_eob,
                      parse_policy, parse_ub04, money)

BILL_RE = re.compile(r"^(\d{6,12})-(\d{1,3})$")
Progress = Callable[[str], None]


# ------------------------------------------------------------------ helpers
def _s(v):
    """Pandas value -> clean str or None."""
    if v is None or (isinstance(v, float) and pd.isna(v)) or (not isinstance(v, str) and pd.isna(v)):
        return None
    return str(v).strip() or None


def _f(v):
    try:
        return None if v is None or pd.isna(v) else round(float(v), 2)
    except (TypeError, ValueError):
        return None


def _d(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return pd.Timestamp(v).date().isoformat()
    s = str(v).strip().split(".")[0]
    for fmt in ("%Y%m%d", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def _first(*vals):
    for v in vals:
        if v not in (None, "", []):
            return v
    return None


def _sum(vals):
    vals = [v for v in vals if v is not None]
    return round(sum(vals), 2) if vals else None


# ------------------------------------------------------------ document level
def parse_bill_pdf(path: Path) -> dict:
    """One bill file = claim form (CMS-1500/UB-04) + payer EOB/ERA pages."""
    ex = extract_pdf(path)
    kinds, parsed = [], {"lines": [], "eobs": []}
    for page in ex["pages"]:
        kind = classify_page(page)
        kinds.append(kind)
        if kind == "cms1500":
            p = parse_cms1500(page)
        elif kind == "ub04":
            p = parse_ub04(page)
        elif kind == "eob":
            parsed["eobs"].append(parse_eob(page))
            continue
        else:
            continue
        parsed["lines"].extend(p.pop("lines", []))
        for k, v in p.items():
            if parsed.get(k) in (None, "", []):
                parsed[k] = v
    parsed["page_kinds"] = kinds
    return {"extract": ex, "parsed": parsed, "kinds": kinds}


def parse_accumulator(path: Path, case_name: str) -> list[dict]:
    df = pd.read_excel(path)
    rows = []
    for _, r in df.iterrows():
        g = lambda c: r.get(c)
        la = _s(g("lossActivity"))
        rows.append({
            "case_name": case_name,
            "claim_no": _s(g("ClaimNo")),
            "line_number": int(g("linenumber")) if _f(g("linenumber")) is not None else None,
            "claimant_id": _s(g("ClaimantID")),
            "claimant_name": _s(g("ClaimantName")),
            "loss_activity": la.split(".")[0].zfill(3) if la else None,
            "loss_activity_desc": _s(g("LossActivityDescription")),
            "diagnosis_code": _s(g("DiagnosisCode")),
            "diagnosis_desc": _s(g("DiagnosisDescription")),
            "procedure_code": _s(g("ProcedureCode")),
            "procedure_desc": _s(g("ProcedureCodeDesc")),
            "provider_id": _s(g("providerid")),
            "provider_name": _s(g("providername")),
            "incurred_from": _d(g("IncurredFromDate")),
            "incurred_to": _d(g("IncurredToDate")),
            "received_date": _d(g("received_date")),
            "total_charges": _f(g("TotalCharges")),
            "allowed_amount": _f(g("AllowedAmount")),
            "deductible": _f(g("CoinsuranceDeductible")),
            "copay": _f(g("CopayAmount")),
            "amount_paid": _f(g("Amountpaid")),
            "remark_code": _s(g("remarkcode")),
            "policy_effective_dt": _s(g("effective_dt")),
            "source_file": path.name,
        })
    return rows


# ------------------------------------------------------------------ case level
def discover_cases(root: Path) -> list[Path]:
    root = Path(root)
    subdirs = sorted(d for d in root.iterdir() if d.is_dir() and not d.name.startswith("."))
    direct = [f for f in root.iterdir() if f.suffix.lower() in (".pdf", ".xls", ".xlsx")]
    cases = list(subdirs)
    if direct:
        cases.insert(0, root)
    return cases


def _priority(f: Path) -> int:
    """Lower = processed first. Keeps the context docs when the demo cap applies."""
    up = f.name.upper()
    if f.suffix.lower() in (".xls", ".xlsx"):
        return 0
    if "POLICY" in up and "RENEWAL" not in up:
        return 1
    if "CLAIM FORM" in up:
        return 2
    if BILL_RE.match(f.stem):
        return 3
    return 4


def _case_files(case_dir: Path, recurse: bool) -> list[Path]:
    it = case_dir.rglob("*") if recurse else case_dir.iterdir()
    files = sorted((f for f in it if f.is_file() and f.suffix.lower() in (".pdf", ".xls", ".xlsx")),
                   key=lambda f: (_priority(f), str(f)))
    return files[:MAX_FILES_PER_CASE] if MAX_FILES_PER_CASE else files


def process_case(case_dir: Path, progress: Progress = print, recurse: bool = True) -> dict:
    case_dir = Path(case_dir)
    case_name = case_dir.name
    files = _case_files(case_dir, recurse)
    progress(f"[{case_name}] {len(files)} files")

    docs, bills, policy_info, claim_form, accum = [], {}, None, None, []
    for f in files:
        up = f.name.upper()
        rel = str(f)
        if f.suffix.lower() in (".xls", ".xlsx"):
            progress(f"  accumulator: {f.name}")
            accum = parse_accumulator(f, case_name)
            docs.append(_doc_row(case_name, None, f, ["accumulator"], None, "table", {"rows": len(accum)}, ""))
            continue
        if "POLICY" in up and "RENEWAL" not in up:
            progress(f"  policy: {f.name}")
            ex = extract_pdf(f, max_pages=4)
            text = "\n".join(ex["pages"])
            policy_info = parse_policy(text)
            docs.append(_doc_row(case_name, None, f, ["policy"], ex, ex["method"], policy_info, text))
        elif "RENEWAL" in up:
            ex = extract_pdf(f, max_pages=1)
            docs.append(_doc_row(case_name, None, f, ["policy_renewal"], ex, ex["method"], {}, "\n".join(ex["pages"])))
        elif "CLAIM FORM" in up:
            progress(f"  claim form: {f.name}")
            ex = extract_pdf(f)
            text = "\n".join(ex["pages"])
            claim_form = parse_claim_form(text)
            docs.append(_doc_row(case_name, None, f, ["claim_form"], ex, ex["method"], claim_form, text))
        elif BILL_RE.match(f.stem):
            progress(f"  bill: {f.name}")
            r = parse_bill_pdf(f)
            cn = BILL_RE.match(f.stem).group(1)
            bills.setdefault(cn, []).append((f, r))
            docs.append(_doc_row(case_name, cn, f, sorted(set(r["kinds"])), r["extract"], r["extract"]["method"],
                                 r["parsed"], "\n\n=== PAGE ===\n".join(r["extract"]["pages"])))
        else:
            progress(f"  skipped (unrecognised): {f.name}")

    return _assemble(case_name, case_dir, docs, bills, policy_info, claim_form, accum)


def _doc_row(case, claim_no, f: Path, kinds, ex, method, parsed, text) -> dict:
    return {
        "case_name": case, "claim_number": claim_no, "file_name": f.name, "file_path": str(f)[:900],
        "doc_types": ",".join(kinds)[:200], "page_count": (ex or {}).get("page_count"),
        "extract_method": method, "parsed_json": json.dumps(parsed, default=str),
        "raw_text": text,
        # per-page index (stored in dbo.document_pages, keyed by doc_id)
        "_pages": [(i, classify_page(t), t) for i, t in enumerate((ex or {}).get("pages", []), 1)],
    }


def _assemble(case_name, case_dir, docs, bills, policy_info, claim_form, accum) -> dict:
    case: dict = {"case_name": case_name, "documents": docs, "claims": [], "accumulator": accum}
    acc_by_claim: dict[str, list[dict]] = {}
    for a in accum:
        acc_by_claim.setdefault(a["claim_no"], []).append(a)

    # ---- policy
    policy_id = _first((policy_info or {}).get("policy_id"), (claim_form or {}).get("policy_no"))
    cms_policy = None
    for cn, items in bills.items():
        for _, r in items:
            cms_policy = cms_policy or r["parsed"].get("policy_group_no")
    policy_id = policy_id or cms_policy
    if policy_info or policy_id:
        pol = policy_info or {}
        case["policy"] = {
            "policy_id": (policy_id or case_name)[:100], "policyholder": pol.get("policyholder"),
            "effective_date": pol.get("effective_date"), "term_end_date": pol.get("term_end_date"),
            "benefit_period_weeks": pol.get("benefit_period_weeks") or 52,
            "benefit_maximum": pol.get("benefit_maximum"), "deductible": pol.get("deductible"),
            "source_file": next((d["file_name"] for d in docs if "policy" in d["doc_types"]), None),
        }
    else:
        policy_id = None

    # ---- member id: folder/file name digits -> accumulator -> CMS id
    m = re.search(r"\b(\d{9})\b", " ".join([case_name] + [d["file_name"] for d in docs]))
    member_id = m.group(1) if m else None
    if not member_id and accum:
        member_id = accum[0]["claimant_id"]

    from collections import Counter
    names, ids = Counter(), Counter()
    first_member = None
    for items in bills.values():
        for _, r in items:
            p = r["parsed"]
            names.update([p["patient_name"]] if p.get("patient_name") else [])
            ids.update([p["insured_id"]] if p.get("insured_id") else [])
            first_member = first_member or p.get("member_name")
    # a case = one claimant in these packages, so use the consensus name (OCR noise gets out-voted)
    first_patient = names.most_common(1)[0][0] if names else None
    first_cms_id = ids.most_common(1)[0][0] if ids else None
    member_id = (member_id or first_cms_id or case_name)[:100]

    if accum and accum[0]["claimant_name"]:
        first_patient = first_patient or accum[0]["claimant_name"].title()
    member_name = first_member or first_patient
    claimant_id = member_id
    case["member"] = {"member_id": member_id, "member_name": member_name}
    case["claimant"] = {"claimant_id": claimant_id, "member_id": member_id, "claimant_name": first_patient}

    # ---- claims
    for cn, items in bills.items():
        all_lines, eobs, p0 = [], [], {}
        for f, r in items:
            p = r["parsed"]
            for k in ("provider_tin", "provider_name", "patient_account_no", "dx_codes", "patient_name"):
                if not p0.get(k) and p.get(k):
                    p0[k] = p[k]
            for ln in p["lines"]:
                all_lines.append({**ln, "_file": f.name, "_tin": p.get("provider_tin"), "_prov": p.get("provider_name")})
            eobs.extend(p["eobs"])

        dos_from = min((l["dos_from"] for l in all_lines if l.get("dos_from")), default=None)
        dos_thru = max((l["dos_thru"] for l in all_lines if l.get("dos_thru")), default=None)
        charges = _sum([l.get("charge_amount") for l in all_lines])
        eob_tot = _sum([e.get("total_charges") for e in eobs])
        charges = charges if charges is not None else eob_tot
        # CMS-1500 prints dollars/cents in separate boxes; OCR can fuse them (x100). EOB total is the cross-check.
        if eob_tot and len(all_lines) == 1 and all_lines[0].get("charge_amount") \
                and abs(all_lines[0]["charge_amount"] / 100 - eob_tot) < 0.02:
            all_lines[0]["charge_amount"] = eob_tot
            charges = eob_tot

        acc = acc_by_claim.get(cn, [])
        dx_code = _first((p0.get("dx_codes") or [None])[0], acc[0]["diagnosis_code"] if acc else None)
        dx_desc = acc[0]["diagnosis_desc"] if acc and acc[0]["diagnosis_code"] else None
        activity = acc[0]["loss_activity"] if acc else None
        received = _first(min((a["received_date"] for a in acc if a["received_date"]), default=None),
                          datetime.fromtimestamp(items[0][0].stat().st_mtime).date().isoformat())
        prov_tin = _first(p0.get("provider_tin"), next((e.get("provider_tin") for e in eobs if e.get("provider_tin")), None))
        acct = _first(p0.get("patient_account_no"), next((e.get("patient_account_no") for e in eobs if e.get("patient_account_no")), None))

        notes = []
        if not activity:
            notes.append("Activity code missing - assign manually")
        dol = (claim_form or {}).get("date_of_loss")
        if not dol:
            notes.append("Date of loss missing - assign manually")
        if not prov_tin:
            notes.append("Provider TIN not found")
        if not dx_code:
            notes.append("Diagnosis not found")
        if not all_lines:
            notes.append("No service lines parsed")
        if not eobs:
            notes.append("No EOB/ERA page found (COB amounts blank)")
        if not accum:
            notes.append("received_date defaulted to file date")

        row = {
            "claim_number": cn, "case_name": case_name, "policy_id": (policy_id or None) and policy_id[:100],
            "member_id": member_id, "member_name": member_name, "claimant_id": claimant_id,
            "claimant_name": first_patient or p0.get("patient_name"),
            "date_of_loss": dol, "received_date": received,
            "date_of_service_from": dos_from, "date_of_service_thru": dos_thru,
            "diagnosis_code": dx_code, "diagnosis_desc": dx_desc, "activity_code": activity,
            "provider_tin": prov_tin, "provider_name": p0.get("provider_name"), "provider_address": None,
            "patient_account_no": acct, "total_charges": charges,
            "total_cob_allowable": _sum([e.get("allowed") for e in eobs]),
            "total_cob_paid": _sum([e.get("paid") for e in eobs]),
            "total_primary_paid": _sum([e.get("paid") for e in eobs]),
            "deductible_amount": _sum([e.get("deductible") for e in eobs]),
            "copay_amount": _sum([e.get("copay") for e in eobs]),
            "coinsurance_amount": _sum([e.get("coinsurance") for e in eobs]),
            "net_payable": None,
            "other_insurance": "Yes" if eobs else ((claim_form or {}).get("other_insurance")),
            "needs_review": 1 if notes else 0, "review_notes": "; ".join(notes) or None,
        }
        lines = []
        for i, l in enumerate(all_lines, 1):
            lines.append({
                "claim_number": cn, "bill_file": l["_file"], "line_no": i,
                "dos_from": l.get("dos_from"), "dos_thru": l.get("dos_thru"), "cpt_code": l.get("cpt_code"),
                "procedure_desc": (l.get("procedure_desc") or None),
                "provider_tin": l["_tin"], "provider_name": l["_prov"],
                "charge_amount": l.get("charge_amount"), "allowed_amount": None, "paid_amount": None,
            })
        # single-line bills: the EOB totals belong to that line
        if len(lines) == 1 and len(eobs) == 1:
            lines[0]["allowed_amount"] = eobs[0].get("allowed")
            lines[0]["paid_amount"] = eobs[0].get("paid")
        case["claims"].append({"row": row, "lines": lines})
    return case


# ------------------------------------------------------------------ entry points
def ingest_root(root: Path, progress: Progress = print, reset: bool = False, recurse: bool = True) -> dict:
    db.init_db()
    if reset:
        db.reset_data()
    summary = {"cases": 0, "claims": 0, "lines": 0, "documents": 0}
    for case_dir in discover_cases(Path(root)):
        case = process_case(case_dir, progress, recurse=recurse if case_dir != Path(root) else False)
        if not case["documents"]:
            continue
        db.save_case(case)
        summary["cases"] += 1
        summary["claims"] += len(case["claims"])
        summary["lines"] += sum(len(c["lines"]) for c in case["claims"])
        summary["documents"] += len(case["documents"])
        progress(f"[{case['case_name']}] saved: {len(case['claims'])} claims")
    return summary


def ingest_upload(path: Path, workdir: Path, progress: Progress = print) -> dict:
    """Ingest a user-uploaded .zip (a whole case) or a single .pdf/.xls."""
    path = Path(path)
    if path.suffix.lower() == ".zip":
        dest = workdir / path.stem
        with zipfile.ZipFile(path) as z:
            z.extractall(dest)
        return ingest_root(dest, progress)
    dest = workdir / ("upload_" + path.stem)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / path.name).write_bytes(path.read_bytes())
    return ingest_root(dest, progress)
