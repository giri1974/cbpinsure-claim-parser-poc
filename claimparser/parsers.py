"""Rule-based parsers for the claim-package document types seen in the samples.

Document types handled (classified per PDF page):
  cms1500     - CMS-1500 professional claim form (scanned)
  ub04        - UB-04 / CMS-1450 institutional claim form (scanned)
  eob         - Primary-payer EOB / ERA remittance pages
  itemized    - hospital itemised statement
  statement   - provider patient statement
  claim_form  - TPA / carrier accident claim form (often handwritten)
  policy      - policy / certificate (text layer or scanned)
  accumulator - claims accumulator spreadsheet (.xls/.xlsx)

OCR output is noisy (missing spaces, mis-read digits), so every regex works on
either the raw text or a whitespace-squashed copy and every value is optional.
Anything not found stays None and the claim is flagged for manual review.
"""
from __future__ import annotations

import re
from datetime import date, datetime

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
MONEY_RE = r"\$?\s*(-?[\d,]*\d[.:]\d{2})"


def squash(text: str) -> str:
    return re.sub(r"\s+", "", text).upper()


def money(s: str | None) -> float | None:
    if s is None:
        return None
    s = str(s).replace(":", ".").replace("$", "").replace(",", "").replace(" ", "")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def iso(mm, dd, yy) -> str | None:
    try:
        mm, dd, yy = int(mm), int(dd), int(yy)
        if yy < 100:
            yy += 2000
        return date(yy, mm, dd).isoformat()
    except (ValueError, TypeError):
        return None


def parse_any_date(s: str | None) -> str | None:
    if not s:
        return None
    s = s.strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%Y%m%d", "%m%d%y", "%m%d%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def first(pattern: str, text: str, flags=re.I, group=1):
    m = re.search(pattern, text, flags)
    return m.group(group).strip() if m else None


def clean_name(s: str | None) -> str | None:
    if not s:
        return None
    s = re.sub(r"[^A-Za-z,'\- ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" ,")
    return s.title() if s else None


ICD_RE = r"\b([A-TV-Z]\d{2}\.?[0-9A-Z]{1,4})\b"
CPT_RE = r"\b(\d{5}|[A-V]\d{4}|U\d{3})\b"


# --------------------------------------------------------------------------
# classification
# --------------------------------------------------------------------------
def classify_page(text: str) -> str:
    sq = squash(text)
    if "BECAUSETHISFORMISUSEDBYVARIOUS" in sq:
        return "instructions"
    if "UB-04" in sq or "CMS-1450" in sq or ("REV.CD" in sq and "TOTALCHARGES" in sq):
        return "ub04"
    if "HEALTHINSURANCECLAIMFORM" in sq or "FORM1500" in sq:
        return "cms1500"
    if ("EXPLANATIONOFBENEFITS" in sq or "ELECTRONICREMITTANCE" in sq or "REASONCODE" in sq
            or "CLAIMADJUSTMENT" in sq or "CLAIMSTATUS" in sq or "PTRESP" in sq or "CHECK/EFT" in sq):
        return "eob"
    if "ITEMIZATIONOFYOURHOSPITAL" in sq or "THISISNOTABILL" in sq:
        return "itemized"
    if "PAYTHISAMOUNT" in sq or "STATEMENTDATE" in sq or "AMOUNTDUE" in sq:
        return "statement"
    if "ACCIDENT" in sq and "CLAIMFORM" in sq and "CLAIMANT" in sq:
        return "claim_form"
    return "other"


# --------------------------------------------------------------------------
# CMS-1500
# --------------------------------------------------------------------------
_NAME_STOP = {"INJURY", "ILLNESS", "PREGNANCY", "FIRST", "LAST", "NAME", "MIDDLE", "STREET", "CITY",
              "STATE", "OR", "DATE", "PLAN", "INSURED", "PATIENT", "SEX", "ADDRESS", "ID"}
_PATIENT_RE = re.compile(r"\b([A-Z][A-Z'\-]{1,24}),\s?([A-Z][A-Z'\-]{1,24})(?:[, ]\s?([A-Z]{1,20}))?")


def _valid_md(mm, dd):
    return 1 <= int(mm) <= 12 and 1 <= int(dd) <= 31


def parse_cms1500(text: str) -> dict:
    lines = [l for l in text.splitlines() if l.strip()]
    out: dict = {"doc_kind": "cms1500", "lines": []}

    # patient / insured name (first LAST,FIRST token after the form header)
    for m in _PATIENT_RE.finditer("\n".join(lines[:60])):
        words = {m.group(1), m.group(2)}
        if words & _NAME_STOP or any(len(w) > 16 or len(w) < 3 for w in words) or "TAMPA" in words:
            continue
        out["patient_name"] = clean_name(f"{m.group(2)} {m.group(3) or ''} {m.group(1)}")
        break

    # insured ID (1a) : alphanumeric token with 8+ digits near top, skip NUCC form number
    top = "\n".join(lines[:25])
    for tok in re.findall(r"\b([A-Z]{0,3}\d{8,12}[A-Z]?\d{0,3})\b", top):
        if not tok.startswith("0938") and not re.search(r"(19|20)\d\d$", tok) and not re.fullmatch(r"\d{8}", tok):
            out["insured_id"] = tok
            break

    # policy / group number (item 11)
    g = next((x for x in re.findall(r"\b([A-Z]{3,}[A-Z]*-\d{3,6})\b", text)
              if not x.startswith(("APPROVED", "OMB", "FORM", "NUCC", "CMS"))), None)
    if g:
        out["policy_group_no"] = g
    pol = first(r"POLICY\s*NO\.?\s*:?\s*([A-Z0-9\-]+)", text)
    if pol:
        out["policy_group_no"] = pol

    # diagnosis codes (item 21)
    dx = []
    seg = re.search(r"21\.?\s*DIAGNOSIS.*?(?=23\.|24\.)", text, re.I | re.S)
    seg_txt = seg.group(0) if seg else text
    for lab in re.findall(r"(?:^|\s)[A-L]\.?\s*[L\[\|]?\s*([A-TV-Z]\d{2}\.?[0-9A-Z]{1,4})\b", seg_txt):
        if lab not in dx:
            dx.append(lab)
    out["dx_codes"] = dx

    # service lines: a line holding two valid dates + a CPT/HCPCS code + charge
    for ln in lines:
        mcpt = re.search(r"\b(\d{5}|[A-V]\d{4}|U\d{3})\b(?:\s+([A-Z0-9]{2}))?", ln)
        if not mcpt:
            continue
        dates, last_end = [], -1
        for dm in re.finditer(r"(?=(?<!\d)(\d{2})\s*(\d{2})\s*(\d{2})(?!\d))", ln):
            if dm.start() < last_end:
                continue
            if _valid_md(dm.group(1), dm.group(2)) and 20 <= int(dm.group(3)) <= 40:
                dates.append(iso(*dm.groups()))
                last_end = dm.start() + 6
        if not dates:
            continue
        after = ln[mcpt.end():]
        nums = re.findall(r"(?<![\w.])(\d{1,6}(?:[.:]\d{2})?)(?![\w])", after)
        charge = None
        for n in nums:
            v = money(n)
            if v is not None and v >= 1:
                charge = v
                break
        # modifiers like QZ P1 AB are tokens directly after the code - skip them
        out["lines"].append({
            "dos_from": dates[0], "dos_thru": dates[1] if len(dates) > 1 else dates[0],
            "cpt_code": mcpt.group(1), "charge_amount": charge,
        })

    # box 25/26/28 line: TIN, patient account, total charge
    for i, ln in enumerate(lines):
        if re.search(r"25\.?\s*FEDERAL|FEDERALTAX", ln, re.I):
            window = lines[i:i + 6]
            for w in window:
                mt = re.search(r"\b(\d{9})\b\s+(\S+)\s+.*?(?:YES|NO).*?(\d[\d,]*[.:]\d{2})\s*$", w)
                if mt:
                    out["provider_tin"] = mt.group(1)
                    out["patient_account_no"] = mt.group(2)
                    out["total_charge"] = money(mt.group(3))
                    break
            break
    if "provider_tin" not in out:
        t = first(r"\b(\d{9})\b\s+\S+\s+X?\s*YES", text)
        if t:
            out["provider_tin"] = t
    if out.get("total_charge") is None and out["lines"]:
        out["total_charge"] = round(sum(l["charge_amount"] or 0 for l in out["lines"]), 2)

    # billing provider (box 33): the line with a business suffix
    for ln in lines:
        if re.search(r"\b(LLP|LLC|INC|GROUP|HOSPITAL|CLINIC|ASSOCIATES|SURGERY|PHYSICIAN|MD|P\.?C\.?|CENTER)\b", ln, re.I) \
                and not re.search(r"SIGNATURE|CERTIFY|APPLY|REVERSE|CARRIER|INSURANCE|PLAN|PROGRAM|ITEM|NUMBER|INSURED|PHYSICIAN\s*OR|SUPPLIER|INFORMATION", ln, re.I):
            out["provider_name"] = clean_name(re.sub(r"^\W*\d+\W*", "", ln.split("  ")[-1] if "  " in ln else ln))
            break
    return out


# --------------------------------------------------------------------------
# UB-04
# --------------------------------------------------------------------------
def _ub_amount(tok: str) -> float | None:
    tok = tok.strip()
    if re.fullmatch(r"[\d,]*\d[.:]\d{2}", tok):
        return money(tok)
    if tok.isdigit() and len(tok) >= 3:      # OCR dropped the decimal point
        return round(int(tok) / 100.0, 2)
    return None


def parse_ub04(text: str) -> dict:
    lines = [l for l in text.splitlines() if l.strip()]
    out: dict = {"doc_kind": "ub04", "lines": []}
    sq = squash(text)

    m = re.search(r"\*?([A-Z][A-Z'\-]+)\s+([A-Z][A-Z'\-]+)\s+(?:MARIETTA|[A-Z]{4,})", "\n".join(lines))
    pn = re.search(r"8\s*PATIENT\s*NAME.*?\n.*?\*?([A-Z]{2,})[ ,]+([A-Z]{2,})", text, re.S)
    for ln_i, ln in enumerate(lines):
        mm = re.search(r"\*([A-Z][A-Z'\-]+)\s+([A-Z][A-Z'\-]+)", ln)
        if mm:
            out["patient_name"] = clean_name(f"{mm.group(2)} {mm.group(1)}")
            break
    mid = first(r"\b([A-Z]\d{9})\b", text)
    if mid:
        out["insured_id"] = mid
    ins = re.search(r"INSURED'?S\s*NAME.*?\n.*?\n?.*?([A-Z]{3,}),\s*([A-Z]{3,})(?:\s+([A-Z]))?", text, re.S)
    if ins:
        out["member_name"] = clean_name(f"{ins.group(2)} {ins.group(3) or ''} {ins.group(1)}")
    else:
        mm = re.search(r"([A-Z]{3,}),\s?([A-Z]{3,})\s?([A-Z])?\s+\d{3}", text)
        if mm:
            out["member_name"] = clean_name(f"{mm.group(2)} {mm.group(3) or ''} {mm.group(1)}")

    fed = first(r"FED\.?\s*TAX\s*NO\.?.*?(\d{9})", text, re.I | re.S) or first(r"\b(\d{9})\s+\d{6}\s+\d{6}\b", text)
    if fed:
        out["provider_tin"] = fed
    out["dx_codes"] = list(dict.fromkeys(re.findall(r"\b([A-TV-Z]\d{3,6}[A-Z]?)\b", " ".join(l for l in lines if re.search(r"DX|S\d{4}|^[A-Z]\d{4}", l)))))[:12]
    # keep only plausible ICD-10 (letter + 2 digits + up to 4 alnum)
    out["dx_codes"] = [d for d in out["dx_codes"] if re.fullmatch(r"[A-TV-Z]\d{2}[0-9A-Z]{1,5}", d)]

    # statement period
    per = re.search(r"(\d{6})\s+(\d{6})\s*$", "\n".join(lines), re.M)
    pm = re.search(r"\b(\d{2})(\d{2})(\d{2})\s+(\d{2})(\d{2})(\d{2})\b", text)
    if pm:
        out["dos_from"] = iso(pm.group(1), pm.group(2), pm.group(3))
        out["dos_thru"] = iso(pm.group(4), pm.group(5), pm.group(6))

    # revenue lines
    for ln in lines:
        mr = re.match(r"^\s*(0\d{3})\s+(.*?)\s+(\d{2})(\d{2})(\d{2})\s+(\d+)\s+(\d[\d,.]*)", ln)
        if mr:
            desc = mr.group(2)
            cpt = None
            mc = re.search(r"\b(\d{5})(?:[A-Z]{2})?\s*$", desc) or re.search(r"(\d{5})", desc)
            if mc:
                cpt = mc.group(1)
                desc = desc[:mc.start()]
            out["lines"].append({
                "dos_from": iso(mr.group(3), mr.group(4), mr.group(5)),
                "dos_thru": iso(mr.group(3), mr.group(4), mr.group(5)),
                "cpt_code": cpt or mr.group(1),
                "procedure_desc": re.sub(r"[^A-Za-z ()\-]", " ", desc).strip(),
                "charge_amount": _ub_amount(mr.group(7)),
            })
    tot = re.search(r"TOTALS?\]?\s*(\d{3,}[.:]?\d{0,2})", text)
    if out["lines"]:
        out["total_charge"] = round(sum(l["charge_amount"] or 0 for l in out["lines"]), 2)
    return out


# --------------------------------------------------------------------------
# EOB / ERA remittance
# --------------------------------------------------------------------------
def _amt_after(label_re: str, text: str) -> float | None:
    m = re.search(label_re + r"\s*[:\-]?\s*\$?\s*(-?[\d,]*\d[.:oO]{1}\d{2})", text, re.I)
    if m:
        return money(m.group(1).replace("o", "0").replace("O", "0"))
    return None


def parse_eob(text: str) -> dict:
    out: dict = {"doc_kind": "eob"}
    t = text.replace("O.00", "0.00")
    out["payer"] = first(r"Payor\s*:?\s*([A-Za-z ]+?)(?:\s{2,}|\d|$)", t) or (
        "Highmark Blue Shield" if "HIGHMARK" in t.upper() else
        "Aetna" if "AETNA" in t.upper() else None)
    out["primary_claim_no"] = first(r"Claim\s*Number\s*[:#]?\s*(\d+)", t)
    out["patient_name_eob"] = clean_name(first(r"(?:PAT|Patient\s*Name)\s*:?\s*([A-Za-z]+\s*,\s*[A-Za-z ]+?)(?:\s{2}|\n|$)", t))
    out["provider_tin"] = first(r"ProvNo\s*:?\s*(\d{9})", t)
    out["patient_account_no"] = first(r"Acct\s*No\s*:?\s*(\d+)", t) or first(r"\b(\d{12})\b", t)
    out["total_charges"] = _amt_after(r"TOT\s*CHGS", t) or _amt_after(r"Billed", t) \
        or _amt_after(r"Total\s*Charges?", t) or _amt_after(r"Amount\s*Billed", t)
    out["allowed"] = _amt_after(r"ALLOWED", t) or _amt_after(r"Allowed\s*Amount", t)
    out["paid"] = _amt_after(r"AMT\s*PAID", t) or _amt_after(r"Plan\s*Paid", t) or _amt_after(r"Amount\s*Paid", t)
    out["pt_resp"] = _amt_after(r"PT\s*RESP", t) or _amt_after(r"PtResp", t) or _amt_after(r"Patient\s*Responsibility", t)
    out["date_paid"] = parse_any_date(first(r"DATE\s*PAID\s*:?\s*(\d{1,2}/\d{1,2}/\d{2,4})", t)
                                        or first(r"Issue\s*Date\s*:?\s*(\d{1,2}/\d{1,2}/\d{2,4})", t))
    ded = _amt_after(r"DEDUCTIBLE", t)
    coins = _amt_after(r"COINSURANCE", t)
    copay = None
    # CARC patient-responsibility groups: PR-1 deductible, PR-2 coinsurance, PR-3 copay
    for grp, val in re.findall(r"\bPR\s*([123])\s+([\d,]*\d[.:]\d{2})", t):
        v = money(val)
        if grp == "1":
            ded = ded or v
        elif grp == "2":
            coins = coins or v
        else:
            copay = copay or v
    out["deductible"], out["coinsurance"], out["copay"] = ded, coins, copay
    if "PR1" in squash(t) and ded is None and out["pt_resp"]:
        out["deductible"] = out["pt_resp"]
    # Fall back: allowed = billed - contractual adjustment when only adjustments are printed
    if out["allowed"] is None and out["total_charges"]:
        amts = [money(a) for a in re.findall(r"(?<![\d.])(\d{1,3}(?:,\d{3})*[.]\d{2})(?!\d)", t)]
        amts = [a for a in amts if a]
        for a in sorted(set(amts), key=lambda x: -amts.count(x)):
            if a < out["total_charges"] and round(out["total_charges"] - a, 2) in amts:
                out["allowed"] = a
                break
    if out["paid"] is None and out["allowed"] is not None and out["pt_resp"] is not None:
        out["paid"] = round(out["allowed"] - out["pt_resp"], 2)
    return out


# --------------------------------------------------------------------------
# Accident claim form (TPA/carrier)
# --------------------------------------------------------------------------
def parse_claim_form(text: str) -> dict:
    out: dict = {"doc_kind": "claim_form"}
    sq = squash(text)
    out["policy_no"] = first(r"(?:Policy\s*or\s*)?Certificate\s*No\.?\s*:?\s*([A-Za-z0-9\-]+)", text)
    inj = first(r"Date\s*&?\s*time\s*of\s*injury\s*:?\s*([A-Za-z]{3,9}\.?\s*\d{1,2},?\s*\d{4})", text)
    out["date_of_loss"] = parse_any_date((inj or "").replace(".", "")) if inj else None
    act = first(r"Type\s*of\s*activity\s*:?\s*([A-Za-z ]{3,30})", text)
    out["activity_text"] = act
    out["other_insurance"] = "Yes" if re.search(r"covered under any other insurance.*?\bYes\b", text, re.I | re.S) else None
    return out


# --------------------------------------------------------------------------
# Policy / certificate
# --------------------------------------------------------------------------
def parse_policy(text: str) -> dict:
    out: dict = {"doc_kind": "policy"}
    pn = first(r"POLICY\s*NUMBER\s*:\s*([A-Z0-9][A-Z0-9\- ]{5,30})", text) \
        or first(r"Group\s*Policy\s*Number\s*:\s*([A-Z0-9\-]+)", text)
    out["policy_id"] = re.sub(r"\s+", "", pn) if pn else None
    out["policyholder"] = first(r"POLICYHOLDER\s*:\s*\n?\s*(.+)", text) or first(r"has been issued to\s+(.+?)\s+which", text, re.I | re.S)
    eff = first(r"POLICY\s*EFFECTIVE\s*DATE\s*:\s*([\d/]+)", text) or first(r"Certificate\s*Effective\s*Date\s*:\s*([A-Za-z]+\s*\d{1,2},\s*\d{4})", text)
    out["effective_date"] = parse_any_date(eff)
    term = re.search(r"POLICY\s*TERM\s*:\s*([\d/]+)\s*(?:through|to|-)\s*([\d/]+)", text, re.I)
    if term:
        out["effective_date"] = out["effective_date"] or parse_any_date(term.group(1))
        out["term_end_date"] = parse_any_date(term.group(2))
    wk = re.search(r"(\d{2,3})\s*[- ]?\s*week\s*(?:Benefit\s*Period|period)?", text, re.I) or \
        re.search(r"Benefit\s*Period[^\n]{0,40}?(\d{2,3})\s*weeks?", text, re.I)
    out["benefit_period_weeks"] = int(wk.group(1)) if wk and int(wk.group(1)) in (26, 52, 104, 156) else None
    mx = first(r"Maximum\s*Total\s*Benefit\s*Amount[^\$]*\$\s*([\d,]+)", text) or first(r"Accident\s*Medical\s*Maximum[^\$]*\$\s*([\d,]+)", text)
    out["benefit_maximum"] = money(mx + ".00") if mx else None
    out["deductible"] = money(first(r"Deductible[^\$\n]{0,40}\$\s*([\d,]+)", text) + ".00") if first(r"Deductible[^\$\n]{0,40}\$\s*([\d,]+)", text) else None
    return out
