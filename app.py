"""Streamlit UI: ingest claim packages into SQL Server LocalDB, inspect and fix records.

Run:  streamlit run app.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from claimparser import db, ingest
from claimparser import config
from claimparser.config import DEFAULT_SAMPLES

LOGO = Path(__file__).parent / "CBInsureLogo.png"
st.set_page_config(page_title="Co-Ordinated Benefit Plans | Claims Intake", page_icon=str(LOGO) if LOGO.exists() else None,
                   layout="wide")

st.markdown("""
<style>
:root { --brand:#0A5AA0; --brand-dark:#073B6B; --brand-light:#EEF3F9; --ink:#1B2A41; --line:#D5DEEA; }
/* Use the full width: no max-width cap, tight side padding so content extends to the edge */
.block-container { padding-top: 1.0rem; padding-left: 2.2rem; padding-right: 2.2rem; max-width: 100%; }
[data-testid="stAppViewContainer"] { overflow-x: hidden; }
h1, h2, h3, h4 { color: var(--brand-dark) !important; font-weight: 650; }
.cbp-badge { display:inline-block; padding:2px 10px; border-radius:11px; font-size:.74rem; font-weight:700; }
.cbp-badge.review { background:#FBE9D0; color:#9A5B00; }
.cbp-badge.ok { background:#DCEFDD; color:#216B25; }
.cbp-pagebar { display:flex; align-items:center; gap:10px; background:var(--brand-light);
  border:1px solid var(--line); border-radius:8px; padding:6px 12px; margin-bottom:8px; }
.cbp-header { display:flex; align-items:center; gap:22px; padding:14px 22px; margin-bottom:14px;
  background:linear-gradient(90deg,#FFFFFF 0%,#EEF3F9 100%); border:1px solid var(--line);
  border-left:6px solid var(--brand); border-radius:10px; }
.cbp-header img { height:62px; }
.cbp-title { font-size:1.45rem; font-weight:700; color:var(--brand-dark); line-height:1.2; }
.cbp-sub { color:#51627C; font-size:.92rem; }
.cbp-kpi { background:#FFFFFF; border:1px solid var(--line); border-top:4px solid var(--brand);
  border-radius:8px; padding:10px 16px; }
.cbp-kpi .n { font-size:1.7rem; font-weight:700; color:var(--brand-dark); }
.cbp-kpi .l { font-size:.8rem; color:#51627C; text-transform:uppercase; letter-spacing:.04em; }
.cbp-kpi.warn { border-top-color:#C77700; } .cbp-kpi.warn .n { color:#9A5B00; }
.cbp-kpi.ok { border-top-color:#2E7D32; } .cbp-kpi.ok .n { color:#2E7D32; }
.cbp-hint { background:var(--brand-light); border-left:4px solid var(--brand); padding:8px 14px;
  border-radius:6px; color:var(--ink); font-size:.92rem; margin:4px 0 14px 0; }
button[data-baseweb="tab"] { font-weight:600; padding:10px 18px; }
button[data-baseweb="tab"][aria-selected="true"] { color:var(--brand) !important; }
div[data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:8px; }
.stButton > button[kind="primary"] { background:var(--brand); border:0; font-weight:600; }
.stButton > button[kind="primary"]:hover { background:var(--brand-dark); }
.cbp-footer { color:#7A8AA0; font-size:.78rem; text-align:center; margin-top:28px; }
</style>
""", unsafe_allow_html=True)


def hint(text: str) -> None:
    st.markdown(f'<div class="cbp-hint">{text}</div>', unsafe_allow_html=True)


def kpi(col, label: str, value, kind: str = "") -> None:
    col.markdown(f'<div class="cbp-kpi {kind}"><div class="n">{value}</div><div class="l">{label}</div></div>',
                 unsafe_allow_html=True)


# ---- database switch (Local SQL Server  <->  Cloud SQL Server) -----------------------------------
import sys
_opts = ["Cloud database", "Local database"]
_default = 0 if config.mode() == "cloud" else 1
with st.sidebar:
    st.markdown("### Environment")
    if sys.platform == "win32":
        _choice = st.radio("Database", _opts, index=_default,
                           help="Cloud = hosted SQL Server used for web deployment. Local = SQL Server LocalDB on this PC.")
    else:
        _choice = _opts[0]
        st.info("Running on a hosted server: using the cloud database.")
    config.set_mode("cloud" if _choice == _opts[0] else "local")
    st.markdown("### OCR engine")
    from claimparser.ocr import tesseract_available
    _eng_opts = ["RapidOCR (recommended)", "Tesseract"]
    _eng = st.radio("Engine", _eng_opts, index=0,
                    help="RapidOCR scored better on the sample scans. Tesseract is optional and must be installed.")
    if _eng == _eng_opts[1] and not tesseract_available():
        st.warning("Tesseract is not installed. Run scripts/install_tesseract.ps1, then restart.")
        config.set_engine("rapidocr")
    else:
        config.set_engine("tesseract" if _eng == _eng_opts[1] else "rapidocr")
    if config.mode() == "cloud" and not config.cloud_configured():
        st.warning("Cloud credentials are not configured. Add a [cloud] section to Streamlit secrets "
                   "(see .streamlit/secrets.toml.example).")
    st.caption(f"Server: `{config.server_label() or 'not set'}`")
    st.caption(f"Database: `{config.database_name() or 'not set'}`")

_ok, _msg = db.test_connection()
if not _ok:
    st.error(f"Cannot connect to the {config.mode()} database. {_msg}")
    st.info("Check the network/VPN, the server name and port, and that your IP is allowed by the database host. "
            "You can switch databases in the sidebar.")
    st.stop()
db.init_db()
with st.sidebar:
    st.success("Connected", icon=":material/check_circle:")
DB_NAME = config.database_name()
_server = config.server_label()

import base64
logo_html = ""
if LOGO.exists():
    logo_html = f'<img src="data:image/png;base64,{base64.b64encode(LOGO.read_bytes()).decode()}" alt="Co-Ordinated Benefit Plans">'
st.markdown(f"""
<div class="cbp-header">{logo_html}
  <div><div class="cbp-title">Claims Intake &amp; Document Extraction</div>
  <div class="cbp-sub">Proof of concept &nbsp;|&nbsp; {config.mode().title()} database: <b>{DB_NAME}</b> on {_server}</div></div>
</div>""", unsafe_allow_html=True)

_k = db.query_df("""SELECT (SELECT COUNT(*) FROM dbo.claims) AS claims,
                           (SELECT COUNT(*) FROM dbo.claims WHERE needs_review = 1) AS review,
                           (SELECT COUNT(*) FROM dbo.claim_line_items) AS lines,
                           (SELECT COUNT(*) FROM dbo.source_documents) AS docs,
                           (SELECT COUNT(*) FROM dbo.document_pages) AS pages""").iloc[0]
k1, k2, k3, k4, k5 = st.columns(5)
kpi(k1, "Claims", int(_k["claims"]))
kpi(k2, "Need review", int(_k["review"]), "warn" if _k["review"] else "ok")
kpi(k3, "Service lines", int(_k["lines"]))
kpi(k4, "Documents", int(_k["docs"]))
kpi(k5, "Indexed pages", int(_k["pages"]))
st.write("")

tab_ing, tab_claims, tab_lines, tab_val, tab_docs = st.tabs(
    ["Intake", "Claims Review", "Service Lines", "Accumulator Check", "Document Library"])

# ------------------------------------------------------------------ ingest
with tab_ing:
    hint("Load a claim package folder. Scanned bills are read with OCR and stored against a Document ID.")
    st.subheader("Process claim folder")
    folder = st.text_input("Folder with case sub-folders", str(DEFAULT_SAMPLES))
    if not Path(folder).exists():
        st.warning("This folder is not available on this server. Use the upload option below.")
    reset = st.checkbox("Clear existing data first", value=False)
    if st.button("Parse folder and load to SQL Server", type="primary", disabled=not Path(folder).exists()):
        log = st.empty()
        lines: list[str] = []

        def progress(msg: str) -> None:
            lines.append(msg)
            log.code("\n".join(lines[-25:]))

        with st.spinner("Parsing (scanned PDFs are OCR'd, first run is slow; results are cached)..."):
            summary = ingest.ingest_root(Path(folder), progress, reset=reset)
        st.success(f"Loaded: {summary}")

    st.divider()
    st.subheader("Upload a document")
    up = st.file_uploader("PDF, XLS/XLSX, or ZIP of a case folder", type=["pdf", "xls", "xlsx", "zip"])
    if up and st.button("Parse uploaded file"):
        tmp = Path(tempfile.mkdtemp(prefix="claims_"))
        p = tmp / up.name
        p.write_bytes(up.getbuffer())
        with st.spinner("Parsing..."):
            summary = ingest.ingest_upload(p, tmp / "work", st.write)
        st.success(f"Loaded: {summary}")

# ------------------------------------------------------------------ claims
with tab_claims:
    hint("Claims flagged <b>Needs review</b> are missing items such as activity code or date of loss. Pick a claim to complete it.")
    claims = db.query_df("SELECT * FROM dbo.claims ORDER BY case_name, claim_number")
    if claims.empty:
        st.info("No claims yet. Load a claim folder on the Intake tab.")
    else:
        fc1, fc2 = st.columns([2, 3])
        cases = ["All cases"] + sorted(claims["case_name"].dropna().unique().tolist())
        pick_case = fc1.selectbox("Filter by case", cases)
        only_review = fc2.toggle("Show only claims that need review", value=False)
        view = claims.copy()
        if pick_case != "All cases":
            view = view[view["case_name"] == pick_case]
        if only_review:
            view = view[view["needs_review"] == True]
        view = view.assign(Status=view["needs_review"].map(lambda r: "Needs review" if r else "Reviewed"))
        show_cols = ["Status", "claim_number", "case_name", "claimant_name", "date_of_service_from",
                     "date_of_service_thru", "diagnosis_code", "activity_code", "provider_tin",
                     "provider_name", "total_charges", "total_cob_allowable", "total_primary_paid",
                     "deductible_amount", "copay_amount", "review_notes"]
        st.dataframe(
            view[show_cols], use_container_width=True, hide_index=True,
            column_config={
                "Status": st.column_config.TextColumn("Status", width="small"),
                "claim_number": st.column_config.TextColumn("Claim #", width="small"),
                "case_name": st.column_config.TextColumn("Case"),
                "claimant_name": "Claimant",
                "date_of_service_from": st.column_config.DateColumn("DOS from"),
                "date_of_service_thru": st.column_config.DateColumn("DOS thru"),
                "diagnosis_code": "Dx", "activity_code": "Activity", "provider_tin": "TIN",
                "provider_name": "Provider",
                "total_charges": st.column_config.NumberColumn("Charges", format="$%.2f"),
                "total_cob_allowable": st.column_config.NumberColumn("COB allowable", format="$%.2f"),
                "total_primary_paid": st.column_config.NumberColumn("Primary paid", format="$%.2f"),
                "deductible_amount": st.column_config.NumberColumn("Deductible", format="$%.2f"),
                "copay_amount": st.column_config.NumberColumn("Copay", format="$%.2f"),
                "review_notes": st.column_config.TextColumn("Review notes", width="large"),
            })
        st.download_button("Download claims (CSV)", claims.to_csv(index=False).encode(),
                           "claims.csv", "text/csv")

        st.divider()
        st.subheader("Complete missing claim details")
        labels = {r["claim_number"]: f'{r["claim_number"]}  -  {r["claimant_name"] or "?"}'
                  f'  ({"needs review" if r["needs_review"] else "reviewed"})'
                  for _, r in view.iterrows()} if not view.empty else {}
        if not labels:
            st.info("No claims match the current filter.")
        else:
            cn = st.selectbox("Claim", list(labels), format_func=lambda c: labels[c])
            cur = claims[claims["claim_number"] == cn].iloc[0]
            badge = ("review", "Needs review") if cur["needs_review"] else ("ok", "Reviewed")
            st.markdown(f'<span class="cbp-badge {badge[0]}">{badge[1]}</span>', unsafe_allow_html=True)
            if cur["review_notes"]:
                st.caption(f"Flagged because: {cur['review_notes']}")
            with st.form("edit_claim"):
                c1, c2, c3 = st.columns(3)
                act = c1.text_input("Activity code", cur["activity_code"] or "")
                dol = c2.text_input("Date of loss (YYYY-MM-DD)", str(cur["date_of_loss"] or ""))
                dx = c3.text_input("Diagnosis code", cur["diagnosis_code"] or "")
                tin = c1.text_input("Provider TIN", cur["provider_tin"] or "")
                pname = c2.text_input("Provider name", cur["provider_name"] or "")
                reviewed = c3.checkbox("Mark as reviewed", value=not bool(cur["needs_review"]))
                if st.form_submit_button("Save changes", type="primary"):
                    db.update_claim_fields(cn, {
                        "activity_code": act or None, "date_of_loss": dol or None, "diagnosis_code": dx or None,
                        "provider_tin": tin or None, "provider_name": pname or None,
                        "needs_review": 0 if reviewed else 1})
                    st.success("Saved.")
                    st.rerun()

# ------------------------------------------------------------------ lines
with tab_lines:
    hint("Procedure-level detail extracted from each bill (CPT/HCPCS, dates of service, charges).")
    li = db.query_df("""SELECT claim_number, bill_file, line_no, dos_from, dos_thru, cpt_code,
                        procedure_desc, provider_tin, provider_name, charge_amount, allowed_amount,
                        paid_amount FROM dbo.claim_line_items ORDER BY claim_number, bill_file, line_no""")
    if li.empty:
        st.info("No service lines yet. Load a claim folder on the Intake tab.")
    else:
        lc1, lc2 = st.columns([2, 3])
        claim_opts = ["All claims"] + sorted(li["claim_number"].unique().tolist())
        pick = lc1.selectbox("Filter by claim", claim_opts, key="line_claim")
        lv = li if pick == "All claims" else li[li["claim_number"] == pick]
        lc2.metric("Lines shown", f"{len(lv)}  /  {len(li)}")
        st.dataframe(
            lv, use_container_width=True, hide_index=True,
            column_config={
                "claim_number": st.column_config.TextColumn("Claim #", width="small"),
                "bill_file": "Bill file", "line_no": st.column_config.NumberColumn("#", width="small"),
                "dos_from": st.column_config.DateColumn("DOS from"),
                "dos_thru": st.column_config.DateColumn("DOS thru"),
                "cpt_code": "CPT", "procedure_desc": "Procedure",
                "provider_tin": "TIN", "provider_name": "Provider",
                "charge_amount": st.column_config.NumberColumn("Charge", format="$%.2f"),
                "allowed_amount": st.column_config.NumberColumn("Allowed", format="$%.2f"),
                "paid_amount": st.column_config.NumberColumn("Paid", format="$%.2f"),
            })
        st.download_button("Download service lines (CSV)", lv.to_csv(index=False).encode(),
                           "service_lines.csv", "text/csv")

# ------------------------------------------------------------------ validation
with tab_val:
    hint("Compares extracted service lines with the client claims-accumulator spreadsheet, where one was provided.")
    val = db.query_df("""
        SELECT a.claim_no, a.line_number, a.procedure_code AS acc_cpt, a.total_charges AS acc_charges,
               l.cpt_code AS parsed_cpt, l.charge_amount AS parsed_charges,
               CASE WHEN l.line_id IS NULL THEN 'MISSING in parsed'
                    WHEN l.charge_amount = a.total_charges THEN 'MATCH'
                    ELSE 'CHARGE DIFFERS' END AS status
        FROM dbo.accumulator_lines a
        LEFT JOIN dbo.claim_line_items l
          ON l.claim_number = a.claim_no AND l.cpt_code = LTRIM(RTRIM(a.procedure_code))
        ORDER BY a.claim_no, a.line_number""")
    if val.empty:
        st.info("No accumulator spreadsheet was provided for the loaded cases, so there is nothing to compare.")
    else:
        matched = int((val.status == "MATCH").sum())
        m1, m2, m3 = st.columns(3)
        m1.metric("Accumulator lines", len(val))
        m2.metric("Charge matched", matched)
        m3.metric("Match rate", f"{matched / len(val) * 100:.0f}%")
        st.dataframe(
            val, use_container_width=True, hide_index=True,
            column_config={
                "claim_no": st.column_config.TextColumn("Claim #", width="small"),
                "line_number": st.column_config.NumberColumn("Line", width="small"),
                "acc_cpt": "Accum CPT",
                "acc_charges": st.column_config.NumberColumn("Accum charge", format="$%.2f"),
                "parsed_cpt": "Parsed CPT",
                "parsed_charges": st.column_config.NumberColumn("Parsed charge", format="$%.2f"),
                "status": "Status",
            })
        st.caption("Facility bills (UB-04) use revenue/CPT codes that differ from the accumulator's "
                   "adjudicated procedure codes, so some lines show as differing even when the extraction is correct.")

# ------------------------------------------------------------------ docs
with tab_docs:
    hint("Every scanned document is indexed by Document ID. Search the text of all pages or open a document to see the original page beside its extracted text.")
    q = st.text_input("Search all OCR / extracted text (e.g. a claim no., name, CPT, TIN)")
    if q:
        hits = db.query_df("""
            SELECT d.doc_id, d.case_name, d.file_name, p.page_no, p.page_type,
                   SUBSTRING(p.page_text, CASE WHEN CHARINDEX(?, p.page_text) > 60 THEN CHARINDEX(?, p.page_text) - 60 ELSE 1 END, 160) AS snippet
            FROM dbo.document_pages p JOIN dbo.source_documents d ON d.doc_id = p.doc_id
            WHERE p.page_text LIKE ? ORDER BY d.doc_id, p.page_no""", (q, q, f"%{q}%"))
        st.caption(f"{len(hits)} matching page(s)")
        st.dataframe(
            hits, use_container_width=True, hide_index=True,
            column_config={
                "doc_id": st.column_config.NumberColumn("Doc ID", width="small"),
                "case_name": "Case", "file_name": "File",
                "page_no": st.column_config.NumberColumn("Page", width="small"),
                "page_type": "Type", "snippet": st.column_config.TextColumn("Match", width="large"),
            })

    docs = db.query_df("""SELECT doc_id, case_name, claim_number, file_name, doc_types, page_count,
                          extract_method, processed_at FROM dbo.source_documents ORDER BY doc_id""")
    if docs.empty:
        st.info("No documents yet. Load a claim folder on the Intake tab.")
    else:
        st.dataframe(
            docs, use_container_width=True, hide_index=True,
            column_config={
                "doc_id": st.column_config.NumberColumn("Doc ID", width="small"),
                "case_name": "Case", "claim_number": st.column_config.TextColumn("Claim #", width="small"),
                "file_name": "File", "doc_types": "Detected types",
                "page_count": st.column_config.NumberColumn("Pages", width="small"),
                "extract_method": "Method",
                "processed_at": st.column_config.DatetimeColumn("Processed"),
            })

        st.divider()
        st.subheader("Document viewer")
        dlabels = {int(r["doc_id"]): f'#{int(r["doc_id"])}  -  {r["file_name"]}  ({r["case_name"]})'
                   for _, r in docs.iterrows()}
        did = int(st.selectbox("Open Document ID", list(dlabels), format_func=lambda d: dlabels[d]))
        meta = db.query_df("SELECT file_path, parsed_json FROM dbo.source_documents WHERE doc_id=?", (did,)).iloc[0]
        pages = db.query_df(
            "SELECT page_no, page_type, page_text FROM dbo.document_pages WHERE doc_id=? ORDER BY page_no", (did,))

        with st.expander("Parsed fields (JSON)"):
            st.json(meta["parsed_json"])

        if pages.empty:
            st.info("This document has no indexed pages (e.g. a spreadsheet).")
        else:
            n = len(pages)
            key = f"docpage_{did}"
            if key not in st.session_state or st.session_state[key] >= n:
                st.session_state[key] = 0

            bar = st.container()
            bc1, bc2, bc3, bc4 = bar.columns([1, 1, 4, 3])
            if bc1.button("◀ Prev", disabled=st.session_state[key] == 0, use_container_width=True):
                st.session_state[key] -= 1
                st.rerun()
            if bc2.button("Next ▶", disabled=st.session_state[key] >= n - 1, use_container_width=True):
                st.session_state[key] += 1
                st.rerun()
            jump = bc3.select_slider("Page", options=list(range(1, n + 1)),
                                     value=st.session_state[key] + 1) if n > 1 else 1
            if jump - 1 != st.session_state[key]:
                st.session_state[key] = jump - 1
                st.rerun()
            idx = st.session_state[key]
            pg = pages.iloc[idx]
            bc4.markdown(f'Page **{idx + 1}** of **{n}** &nbsp; '
                         f'<span class="cbp-badge ok">{pg["page_type"]}</span>', unsafe_allow_html=True)
            st.caption(f"Source file: `{meta['file_path']}`")

            img_col, txt_col = st.columns([1, 1], gap="medium")
            with img_col:
                st.markdown("**Original page**")
                try:
                    import pymupdf
                    pdf = pymupdf.open(meta["file_path"])
                    st.image(pdf[int(pg["page_no"]) - 1].get_pixmap(dpi=110).tobytes("png"),
                             use_container_width=True)
                except Exception:
                    st.info("Original page image unavailable (file not on this machine).")
            with txt_col:
                st.markdown("**Extracted / OCR text**")
                st.text_area("page text", pg["page_text"] or "(no text)", height=560,
                             label_visibility="collapsed")

st.markdown('<div class="cbp-footer">Co-Ordinated Benefit Plans, a subsidiary of ONE80 Intermediaries &nbsp;|&nbsp; POC build for demonstration</div>', unsafe_allow_html=True)
