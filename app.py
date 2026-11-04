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
.block-container { padding-top: 1.2rem; max-width: 1400px; }
h1, h2, h3, h4 { color: var(--brand-dark) !important; font-weight: 650; }
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
    hint("Claims flagged <b>needs_review</b> are missing items such as activity code or date of loss. Complete them below.")
    claims = db.query_df("SELECT * FROM dbo.claims ORDER BY case_name, claim_number")
    st.dataframe(claims, use_container_width=True)
    if not claims.empty:
        st.subheader("Complete missing claim details")
        cn = st.selectbox("Claim", claims["claim_number"])
        cur = claims[claims["claim_number"] == cn].iloc[0]
        c1, c2, c3 = st.columns(3)
        act = c1.text_input("Activity code", cur["activity_code"] or "")
        dol = c2.text_input("Date of loss (YYYY-MM-DD)", str(cur["date_of_loss"] or ""))
        dx = c3.text_input("Diagnosis code", cur["diagnosis_code"] or "")
        tin = c1.text_input("Provider TIN", cur["provider_tin"] or "")
        pname = c2.text_input("Provider name", cur["provider_name"] or "")
        reviewed = c3.checkbox("Mark as reviewed", value=not bool(cur["needs_review"]))
        if st.button("Save changes"):
            db.update_claim_fields(cn, {
                "activity_code": act or None, "date_of_loss": dol or None, "diagnosis_code": dx or None,
                "provider_tin": tin or None, "provider_name": pname or None,
                "needs_review": 0 if reviewed else 1})
            st.success("Saved. Reload the tab to see it.")

# ------------------------------------------------------------------ lines
with tab_lines:
    hint("Procedure-level detail extracted from each bill (CPT/HCPCS, dates of service, charges).")
    st.dataframe(db.query_df("SELECT * FROM dbo.claim_line_items ORDER BY claim_number, bill_file, line_no"),
                 use_container_width=True)

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
        st.info("No accumulator data loaded.")
    else:
        st.metric("Accumulator lines matched", f"{(val.status == 'MATCH').sum()} / {len(val)}")
        st.dataframe(val, use_container_width=True)

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
        st.write(f"{len(hits)} matching page(s)")
        st.dataframe(hits, use_container_width=True)

    docs = db.query_df("""SELECT doc_id, case_name, claim_number, file_name, doc_types, page_count,
                          extract_method, processed_at FROM dbo.source_documents ORDER BY doc_id""")
    st.dataframe(docs, use_container_width=True)
    if not docs.empty:
        did = int(st.selectbox("Open Document ID", docs["doc_id"]))
        meta = db.query_df("SELECT file_path, parsed_json FROM dbo.source_documents WHERE doc_id=?", (did,)).iloc[0]
        pages = db.query_df("SELECT page_no, page_type, page_text FROM dbo.document_pages WHERE doc_id=? ORDER BY page_no", (did,))
        st.caption(f"Source file: `{meta['file_path']}`")
        with st.expander("Parsed fields (JSON)"):
            st.json(meta["parsed_json"])
        for _, pg in pages.iterrows():
            with st.expander(f"Page {pg['page_no']}  [{pg['page_type']}]"):
                c1, c2 = st.columns(2)
                try:
                    import pymupdf
                    pdf = pymupdf.open(meta["file_path"])
                    c1.image(pdf[int(pg["page_no"]) - 1].get_pixmap(dpi=80).tobytes("png"))
                except Exception:
                    c1.info("Original page image unavailable.")
                c2.text(pg["page_text"])

st.markdown('<div class="cbp-footer">Co-Ordinated Benefit Plans, a subsidiary of ONE80 Intermediaries &nbsp;|&nbsp; POC build for demonstration</div>', unsafe_allow_html=True)
