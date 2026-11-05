"""Shared Streamlit chrome: page config, full-width header, CSS, sidebar controls.
Imported by app.py (main) and pages/document_viewer.py so both look identical."""
from __future__ import annotations

import base64
import sys
from pathlib import Path

import streamlit as st

from . import config, db

LOGO = Path(__file__).resolve().parent.parent / "CBInsureLogo.png"

_CSS = """
<style>
:root { --brand:#0A5AA0; --brand-dark:#073B6B; --brand-light:#EEF3F9; --ink:#1B2A41; --line:#D5DEEA; }
/* full width, tight padding, no horizontal scroll */
.block-container { padding-top: 0.6rem; padding-left: 1.6rem; padding-right: 1.6rem; max-width: 100%; }
[data-testid="stAppViewContainer"] { overflow-x: hidden; }
/* narrow sidebar that fits its text */
section[data-testid="stSidebar"] { width: 232px !important; min-width: 232px !important; }
section[data-testid="stSidebar"] .block-container { padding-top: 1rem; }
h1,h2,h3,h4 { color: var(--brand-dark) !important; font-weight: 650; }
/* header banner spans the whole content width (incl. the strip above the sidebar) */
.cbp-header { display:flex; align-items:center; gap:22px; padding:12px 26px; margin:0 0 14px 0;
  background:linear-gradient(90deg,#FFFFFF 0%,#EEF3F9 100%); border:1px solid var(--line);
  border-left:6px solid var(--brand); border-radius:10px; }
.cbp-header img { height:58px; }
.cbp-title { font-size:1.5rem; font-weight:700; color:var(--brand-dark); line-height:1.15; }
.cbp-sub { color:#51627C; font-size:.92rem; }
.cbp-kpi { background:#FFFFFF; border:1px solid var(--line); border-top:4px solid var(--brand);
  border-radius:8px; padding:10px 16px; }
.cbp-kpi .n { font-size:1.7rem; font-weight:700; color:var(--brand-dark); }
.cbp-kpi .l { font-size:.8rem; color:#51627C; text-transform:uppercase; letter-spacing:.04em; }
.cbp-kpi.warn { border-top-color:#C77700; } .cbp-kpi.warn .n { color:#9A5B00; }
.cbp-kpi.ok { border-top-color:#2E7D32; } .cbp-kpi.ok .n { color:#2E7D32; }
.cbp-hint { background:var(--brand-light); border-left:4px solid var(--brand); padding:8px 14px;
  border-radius:6px; color:var(--ink); font-size:.92rem; margin:4px 0 14px 0; }
.cbp-badge { display:inline-block; padding:2px 10px; border-radius:11px; font-size:.74rem; font-weight:700; }
.cbp-badge.review { background:#FBE9D0; color:#9A5B00; } .cbp-badge.ok { background:#DCEFDD; color:#216B25; }
button[data-baseweb="tab"] { font-weight:600; padding:10px 18px; }
button[data-baseweb="tab"][aria-selected="true"] { color:var(--brand) !important; }
div[data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:8px; }
.stButton > button[kind="primary"] { background:var(--brand); border:0; font-weight:600; }
.stButton > button[kind="primary"]:hover { background:var(--brand-dark); }
.cbp-footer { color:#7A8AA0; font-size:.78rem; text-align:center; margin-top:26px; }
/* pull the header up into the empty strip above the sidebar */
[data-testid="stHeader"] { background: transparent; }
</style>
"""


def page_setup(title: str) -> None:
    st.set_page_config(page_title=f"CBP | {title}", layout="wide",
                       page_icon=str(LOGO) if LOGO.exists() else None,
                       initial_sidebar_state="expanded")
    st.markdown(_CSS, unsafe_allow_html=True)


def hint(text: str) -> None:
    st.markdown(f'<div class="cbp-hint">{text}</div>', unsafe_allow_html=True)


def kpi(col, label: str, value, kind: str = "") -> None:
    col.markdown(f'<div class="cbp-kpi {kind}"><div class="n">{value}</div><div class="l">{label}</div></div>',
                 unsafe_allow_html=True)


def badge(kind: str, text: str) -> str:
    return f'<span class="cbp-badge {kind}">{text}</span>'


def header() -> None:
    logo_html = ""
    if LOGO.exists():
        b64 = base64.b64encode(LOGO.read_bytes()).decode()
        logo_html = f'<img src="data:image/png;base64,{b64}" alt="Co-Ordinated Benefit Plans">'
    st.markdown(f"""
    <div class="cbp-header">{logo_html}
      <div><div class="cbp-title">Claims Intake &amp; Document Extraction</div>
      <div class="cbp-sub">Proof of concept &nbsp;|&nbsp; {config.mode().title()} database:
      <b>{config.database_name()}</b> on {config.server_label()}</div></div>
    </div>""", unsafe_allow_html=True)


def footer() -> None:
    st.markdown('<div class="cbp-footer">Co-Ordinated Benefit Plans, a subsidiary of ONE80 Intermediaries'
                ' &nbsp;|&nbsp; POC build for demonstration</div>', unsafe_allow_html=True)


def sidebar_controls() -> None:
    """Database + OCR engine switches, shared by every page. Also connects/inits the DB."""
    from .ocr import tesseract_available
    with st.sidebar:
        st.markdown("### Environment")
        db_opts = ["Cloud database", "Local database"]
        if sys.platform == "win32":
            choice = st.radio("Database", db_opts, index=0 if config.mode() == "cloud" else 1,
                              help="Cloud = hosted SQL Server for web deployment. Local = LocalDB on this PC.")
        else:
            choice = db_opts[0]
            st.info("Hosted server: using the cloud database.")
        config.set_mode("cloud" if choice == db_opts[0] else "local")

        st.markdown("### OCR engine")
        eng_opts = ["RapidOCR (recommended)", "Tesseract"]
        eng = st.radio("Engine", eng_opts, index=0,
                       help="RapidOCR scored better on the sample scans. Tesseract is optional.")
        if eng == eng_opts[1] and not tesseract_available():
            st.warning("Tesseract is not installed. Run scripts/install_tesseract.ps1, then restart.")
            config.set_engine("rapidocr")
        else:
            config.set_engine("tesseract" if eng == eng_opts[1] else "rapidocr")

        if config.mode() == "cloud" and not config.cloud_configured():
            st.warning("Cloud credentials are not configured (see .streamlit/secrets.toml.example).")
        st.caption(f"Server: `{config.server_label() or 'not set'}`")
        st.caption(f"Database: `{config.database_name() or 'not set'}`")

    ok, msg = db.test_connection()
    if not ok:
        st.error(f"Cannot connect to the {config.mode()} database. {msg}")
        st.info("Check the network, server name and port, and that your IP is allowed. "
                "You can switch databases in the sidebar.")
        st.stop()
    db.init_db()
    with st.sidebar:
        st.success("Connected", icon=":material/check_circle:")


def open_document(doc_id: int) -> None:
    """Navigate to the dedicated viewer page for a document."""
    st.query_params["doc"] = str(int(doc_id))
    st.switch_page("pages/document_viewer.py")
