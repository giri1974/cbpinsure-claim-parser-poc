"""Shared Streamlit chrome matching the CBP Figma design.

Provides: page_setup (CSS + config), topbar (white app bar with logo, title,
POC pill, search/bell/user chip and a Settings popover holding the DB + OCR
switches), KPI cards, icon tabs, chips/pills, and small HTML widgets (donut,
status bar). Imported by app.py and pages/document_viewer.py."""
from __future__ import annotations

import base64
import html
import sys
from pathlib import Path

import streamlit as st

from . import config, db

ROOT = Path(__file__).resolve().parent.parent
LOGO = ROOT / "CBInsureLogo.png"

# ----- design tokens ------------------------------------------------------------------------------
BRAND = "#0B5CAB"
BRAND_DARK = "#083B6E"
INK = "#1F2A37"
MUTE = "#64748B"
LINE = "#E6EAF0"
PAGE_BG = "#F5F7FA"
AMBER = "#D08400"
AMBER_BG = "#FEF3E2"
GREEN = "#1F8A4C"
GREEN_BG = "#E3F3E8"
RED = "#D64550"
RED_BG = "#FCEBEC"

_CSS = f"""
<style>
:root {{
  --brand:{BRAND}; --brand-dark:{BRAND_DARK}; --ink:{INK}; --mute:{MUTE};
  --line:{LINE}; --page:{PAGE_BG}; --amber:{AMBER}; --amber-bg:{AMBER_BG};
  --green:{GREEN}; --green-bg:{GREEN_BG}; --red:{RED}; --red-bg:{RED_BG};
}}
html, body, [class*="st-"], .stMarkdown, p, span, div, label {{
  font-family: "Inter","Segoe UI",system-ui,-apple-system,sans-serif; }}
[data-testid="stAppViewContainer"] {{ background: var(--page); overflow-x: hidden; }}
[data-testid="stHeader"] {{ display:none; }}
section[data-testid="stSidebar"] {{ display:none; }}
.block-container {{ padding: 0.4rem 2rem 2rem 2rem; max-width: 100%; }}
h1,h2,h3,h4 {{ color: var(--ink) !important; }}

/* ---- top app bar ---- */
.cbp-topbar {{ display:flex; align-items:center; gap:16px; background:#FFFFFF;
  border:1px solid var(--line); border-radius:12px; padding:10px 18px; margin-bottom:14px;
  box-shadow:0 1px 2px rgba(16,24,40,.04); }}
.cbp-topbar img {{ height:42px; }}
.cbp-tb-title {{ font-size:1.02rem; font-weight:700; color:var(--ink); }}
.cbp-pill {{ display:inline-block; font-size:.62rem; font-weight:700; letter-spacing:.06em;
  color:var(--mute); background:#EEF2F7; border:1px solid var(--line); border-radius:6px;
  padding:1px 7px; margin-left:8px; vertical-align:middle; }}
.cbp-tb-right {{ margin-left:auto; display:flex; align-items:center; gap:16px; color:var(--mute); }}
.cbp-ic {{ font-size:1.05rem; color:var(--mute); position:relative; }}
.cbp-dot {{ position:absolute; top:-2px; right:-3px; width:7px; height:7px; border-radius:50%;
  background:var(--red); border:1px solid #fff; }}
.cbp-user {{ display:flex; align-items:center; gap:9px; }}
.cbp-ava {{ width:34px; height:34px; border-radius:50%; background:var(--brand-dark); color:#fff;
  display:flex; align-items:center; justify-content:center; font-weight:700; font-size:.82rem; }}
.cbp-uname {{ font-size:.84rem; font-weight:700; color:var(--ink); line-height:1.05; }}
.cbp-urole {{ font-size:.72rem; color:var(--mute); }}

/* ---- KPI cards ---- */
.cbp-kpi {{ display:flex; align-items:center; gap:14px; background:#FFFFFF; border:1px solid var(--line);
  border-radius:12px; padding:14px 16px; box-shadow:0 1px 2px rgba(16,24,40,.04); }}
.cbp-kpi.warn {{ border-left:4px solid var(--amber); }}
.cbp-kpi-ic {{ width:40px; height:40px; border-radius:10px; background:#EEF4FB; display:flex;
  align-items:center; justify-content:center; font-size:1.2rem; }}
.cbp-kpi.warn .cbp-kpi-ic {{ background:var(--amber-bg); }}
.cbp-kpi-l {{ font-size:.78rem; color:var(--mute); }}
.cbp-kpi-n {{ font-size:1.5rem; font-weight:800; color:var(--ink); line-height:1.1; }}

/* ---- cards / sections ---- */
.cbp-card {{ background:#FFFFFF; border:1px solid var(--line); border-radius:12px; padding:18px 20px;
  box-shadow:0 1px 2px rgba(16,24,40,.04); margin-bottom:14px; }}
.cbp-h {{ font-size:1.6rem; font-weight:800; color:var(--ink); margin:2px 0 0 0; }}
.cbp-sub {{ color:var(--mute); font-size:.92rem; margin-bottom:12px; }}
.cbp-secure {{ color:var(--green); font-size:.82rem; font-weight:600; }}

/* ---- chips / pills ---- */
.cbp-chip {{ display:inline-block; font-size:.72rem; font-weight:700; border-radius:9px; padding:2px 9px; }}
.chip-review {{ background:var(--amber-bg); color:var(--amber); }}
.chip-ok {{ background:var(--green-bg); color:var(--green); }}
.chip-miss {{ background:var(--amber-bg); color:var(--amber); }}
.chip-red {{ background:var(--red-bg); color:var(--red); }}
.chip-type {{ background:#EAF1FB; color:var(--brand); border:1px solid #D5E3F6; margin-right:4px; }}
.chip-dim {{ background:#EEF2F7; color:var(--mute); }}
.cbp-badge {{ display:inline-block; padding:2px 10px; border-radius:11px; font-size:.74rem; font-weight:700; }}
.cbp-badge.review {{ background:var(--amber-bg); color:var(--amber); }}
.cbp-badge.ok {{ background:var(--green-bg); color:var(--green); }}

/* ---- tabs ---- */
.stTabs [data-baseweb="tab-list"] {{ gap:6px; border-bottom:1px solid var(--line); }}
button[data-baseweb="tab"] {{ font-weight:600; padding:10px 16px; color:var(--mute); }}
button[data-baseweb="tab"][aria-selected="true"] {{ color:var(--brand) !important; }}
.stTabs [data-baseweb="tab-highlight"] {{ background:var(--brand); }}

/* ---- data tables (styled HTML) ---- */
.cbp-tbl {{ width:100%; border-collapse:collapse; font-size:.85rem; }}
.cbp-tbl th {{ text-align:left; color:var(--mute); font-weight:600; font-size:.74rem;
  text-transform:uppercase; letter-spacing:.03em; padding:9px 10px; border-bottom:1px solid var(--line); }}
.cbp-tbl td {{ padding:9px 10px; border-bottom:1px solid #F1F4F8; color:var(--ink); }}
.cbp-tbl tr:hover td {{ background:#FAFBFD; }}
.cbp-grp td {{ background:#F4F7FB; font-weight:700; color:var(--ink); }}
.cbp-row-bad td {{ background:#FDF4F5; }}
.cbp-num {{ text-align:right; font-variant-numeric:tabular-nums; }}
.cbp-sub-amt {{ text-align:right; font-weight:800; color:var(--brand-dark); }}

/* ---- info banner ---- */
.cbp-info {{ background:#EAF2FB; border:1px solid #D4E4F6; border-radius:10px; padding:10px 14px;
  color:var(--ink); font-size:.9rem; margin-bottom:12px; }}
.cbp-info b {{ color:var(--brand-dark); }}

/* ---- buttons ---- */
.stButton > button[kind="primary"] {{ background:var(--brand); border:0; font-weight:700; border-radius:8px; }}
.stButton > button[kind="primary"]:hover {{ background:var(--brand-dark); }}
.stButton > button[kind="secondary"] {{ border:1px solid var(--line); border-radius:8px; color:var(--ink); }}
.stDownloadButton > button {{ border:1px solid var(--line); border-radius:8px; }}

/* ---- misc ---- */
div[data-testid="stDataFrame"] {{ border:1px solid var(--line); border-radius:10px; }}
.cbp-progress {{ height:7px; background:#E9EEF5; border-radius:4px; overflow:hidden; }}
.cbp-progress > span {{ display:block; height:100%; background:var(--brand); }}
.cbp-footer {{ color:#93A1B5; font-size:.78rem; text-align:center; margin-top:22px; }}
.cbp-varbar {{ display:inline-block; height:6px; background:var(--red); border-radius:3px; vertical-align:middle;
  margin-left:6px; }}
</style>
"""


def page_setup(title: str) -> None:
    st.set_page_config(page_title=f"CBP | {title}", layout="wide",
                       page_icon=str(LOGO) if LOGO.exists() else None,
                       initial_sidebar_state="collapsed")
    st.markdown(_CSS, unsafe_allow_html=True)


# ----- small helpers ------------------------------------------------------------------------------
def chip(text: str, cls: str) -> str:
    return f'<span class="cbp-chip {cls}">{html.escape(str(text))}</span>'


def badge(kind: str, text: str) -> str:
    return f'<span class="cbp-badge {kind}">{html.escape(str(text))}</span>'


def hint(text: str) -> None:
    st.markdown(f'<div class="cbp-info">{text}</div>', unsafe_allow_html=True)


def _logo_b64() -> str:
    return base64.b64encode(LOGO.read_bytes()).decode() if LOGO.exists() else ""


def donut(pct: int, color: str = RED, size: int = 62) -> str:
    """Small conic-gradient donut gauge as inline HTML."""
    pct = max(0, min(100, int(pct)))
    return (f'<div style="width:{size}px;height:{size}px;border-radius:50%;'
            f'background:conic-gradient({color} {pct*3.6:.0f}deg,#EceFF3 0);'
            f'display:flex;align-items:center;justify-content:center;">'
            f'<div style="width:{size-16}px;height:{size-16}px;border-radius:50%;background:#fff;'
            f'display:flex;align-items:center;justify-content:center;font-weight:800;'
            f'font-size:.8rem;color:{color};">{pct}%</div></div>')


def seg_bar(segments: list[tuple[str, int, str]]) -> str:
    """segments: list of (label, value, color). Renders a stacked bar + legend."""
    total = sum(v for _, v, _ in segments) or 1
    bars = "".join(f'<span style="width:{v/total*100:.1f}%;background:{c};"></span>'
                   for _, v, c in segments if v)
    legend = " &nbsp; ".join(f'<span style="color:{c};font-weight:700;">&#9632;</span> '
                             f'<span style="font-size:.78rem;color:var(--mute);">{l} {v}</span>'
                             for l, v, c in segments)
    return (f'<div style="display:flex;height:9px;border-radius:5px;overflow:hidden;'
            f'margin:8px 0;">{bars}</div><div>{legend}</div>')


# ----- chrome -------------------------------------------------------------------------------------
def topbar() -> None:
    """White app bar + Settings popover carrying the DB/OCR switches. Also connects the DB."""
    from .ocr import tesseract_available
    logo = _logo_b64()
    logo_html = f'<img src="data:image/png;base64,{logo}">' if logo else ""
    bar, settings = st.columns([9, 1])
    with bar:
        st.markdown(f"""
        <div class="cbp-topbar">{logo_html}
          <span class="cbp-tb-title">Claims Intake &amp; Document Extraction</span>
          <span class="cbp-pill">POC</span>
          <div class="cbp-tb-right">
            <span class="cbp-ic">&#128269;</span>
            <span class="cbp-ic">&#128276;<span class="cbp-dot"></span></span>
            <span class="cbp-user"><span class="cbp-ava">AK</span>
              <span><span class="cbp-uname">Alex Kim</span><br><span class="cbp-urole">Claims Examiner</span></span>
            </span>
          </div>
        </div>""", unsafe_allow_html=True)
    with settings:
        with st.popover("⚙ Settings", use_container_width=True):
            st.markdown("**Environment**")
            db_opts = ["Cloud database", "Local database"]
            if sys.platform == "win32":
                choice = st.radio("Database", db_opts, index=0 if config.mode() == "cloud" else 1,
                                  help="Cloud = hosted SQL Server. Local = LocalDB on this PC.")
            else:
                choice = db_opts[0]
                st.info("Hosted server: using the cloud database.")
            config.set_mode("cloud" if choice == db_opts[0] else "local")

            st.markdown("**OCR engine**")
            eng_opts = ["RapidOCR (recommended)", "Tesseract"]
            eng = st.radio("Engine", eng_opts, index=0,
                           help="RapidOCR scored better on the sample scans. Tesseract is optional.")
            if eng == eng_opts[1] and not tesseract_available():
                st.warning("Tesseract is not installed. Run scripts/install_tesseract.ps1, then restart.")
                config.set_engine("rapidocr")
            else:
                config.set_engine("tesseract" if eng == eng_opts[1] else "rapidocr")
            if config.mode() == "cloud" and not config.cloud_configured():
                st.warning("Cloud credentials not configured (see .streamlit/secrets.toml.example).")
            st.caption(f"Server: `{config.server_label() or 'not set'}`")
            st.caption(f"Database: `{config.database_name() or 'not set'}`")

    ok, msg = db.test_connection()
    if not ok:
        st.error(f"Cannot connect to the {config.mode()} database. {msg}")
        st.info("Check the network, server name and port. Switch databases in Settings.")
        st.stop()
    db.init_db()


def kpi_row(need_review: int, service_lines: int, documents: int, pages: int) -> None:
    cols = st.columns(4)
    data = [("warn", "&#9889;", "Need review", need_review),
            ("", "&#9776;", "Service lines", service_lines),
            ("", "&#128462;", "Documents", documents),
            ("", "&#128209;", "Indexed pages", pages)]
    for col, (cls, ic, label, val) in zip(cols, data):
        col.markdown(f'<div class="cbp-kpi {cls}"><div class="cbp-kpi-ic">{ic}</div>'
                     f'<div><div class="cbp-kpi-l">{label}</div><div class="cbp-kpi-n">{val}</div></div></div>',
                     unsafe_allow_html=True)
    st.write("")


def page_title(title: str, subtitle: str, secure: bool = False) -> None:
    right = '<span class="cbp-secure">&#128274; Secure document processing</span>' if secure else ""
    st.markdown(f'<div style="display:flex;align-items:flex-start;">'
                f'<div><div class="cbp-h">{html.escape(title)}</div>'
                f'<div class="cbp-sub">{subtitle}</div></div>'
                f'<div style="margin-left:auto;">{right}</div></div>', unsafe_allow_html=True)


def footer() -> None:
    st.markdown('<div class="cbp-footer">Co-Ordinated Benefit Plans, a subsidiary of ONE80 Intermediaries'
                ' &nbsp;|&nbsp; POC build for demonstration</div>', unsafe_allow_html=True)


def open_document(doc_id: int) -> None:
    st.query_params["doc"] = str(int(doc_id))
    st.switch_page("pages/document_viewer.py")


# ----- value formatting for styled HTML tables ----------------------------------------------------
def money(v, missing_chip: bool = False) -> str:
    if v is None or (isinstance(v, float) and v != v):
        return chip("Missing", "chip-miss") if missing_chip else '<span style="color:#B6C0CE;">—</span>'
    return f"${float(v):,.2f}"


def text_or_missing(v) -> str:
    if v is None or str(v).strip() == "" or str(v).lower() == "none":
        return chip("Missing", "chip-miss")
    return html.escape(str(v))


def date_or_missing(v) -> str:
    if v is None or str(v).strip() in ("", "NaT", "None"):
        return chip("Missing", "chip-miss")
    try:
        import pandas as pd
        return pd.to_datetime(v).strftime("%b %-d, %Y")
    except Exception:
        try:
            import pandas as pd
            return pd.to_datetime(v).strftime("%b %d, %Y").replace(" 0", " ")
        except Exception:
            return html.escape(str(v))


def initials(name) -> str:
    if not name:
        return "?"
    parts = [p for p in str(name).replace(",", " ").split() if p]
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper()


_THUMB_DIR = ROOT / "ocr_cache" / "thumbs"


def page_thumb(file_path: str, doc_id: int, width: int = 54) -> str:
    """Return an <img> data-URI of the first page, cached on disk. Falls back to an icon."""
    try:
        _THUMB_DIR.mkdir(parents=True, exist_ok=True)
        cache = _THUMB_DIR / f"{doc_id}.png"
        if not cache.exists():
            p = Path(file_path)
            if p.suffix.lower() != ".pdf" or not p.exists():
                return '<span style="font-size:1.1rem;">&#128202;</span>'
            import pymupdf
            doc = pymupdf.open(p)
            doc[0].get_pixmap(dpi=36).save(str(cache))
        b64 = base64.b64encode(cache.read_bytes()).decode()
        return (f'<img src="data:image/png;base64,{b64}" '
                f'style="width:{width}px;border:1px solid var(--line);border-radius:4px;">')
    except Exception:
        return '<span style="font-size:1.1rem;">&#128462;</span>'


def type_chips(doc_types: str | None, limit: int = 2) -> str:
    if not doc_types:
        return ""
    parts = [t.strip() for t in str(doc_types).split(",") if t.strip() and t.strip() != "instructions"]
    shown = parts[:limit]
    extra = len(parts) - len(shown)
    html_ = "".join(chip(t.upper() if t in ("eob", "ub04") else t.replace("_", " ").title(), "chip-type")
                    for t in shown)
    if extra > 0:
        html_ += chip(f"+{extra}", "chip-dim")
    return html_


def method_chip(method: str | None) -> str:
    m = (method or "").lower()
    if m == "text":
        return chip("● Text", "chip-ok")
    if m in ("ocr", "mixed"):
        return chip("● OCR", "chip-type")
    return chip(method or "—", "chip-dim")


def html_table(headers: list[str], rows_html: list[str], aligns: list[str] | None = None) -> str:
    aligns = aligns or [""] * len(headers)
    th = "".join(f'<th class="{"cbp-num" if a == "r" else ""}">{html.escape(h)}</th>'
                 for h, a in zip(headers, aligns))
    return f'<table class="cbp-tbl"><thead><tr>{th}</tr></thead><tbody>{"".join(rows_html)}</tbody></table>'
