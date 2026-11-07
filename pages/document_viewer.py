"""Document viewer page matching the CBP reference (page 7).

Layout: breadcrumb + document nav; metadata strip; left thumbnail rail (page
type labels); center page image with page nav + zoom control; right rail with
Extracted fields / OCR text / JSON tabs, an extraction-confidence bar, and
per-field confidence dots. Opened from the Document Library via ?doc=<id>.
"""
from __future__ import annotations

import json

import streamlit as st

from claimparser import db, ui

ui.page_setup("Document Viewer")
ui.topbar()

docs = db.query_df("""SELECT doc_id, case_name, claim_number, file_name, file_path, doc_types, page_count,
                      extract_method FROM dbo.source_documents ORDER BY doc_id""")
if docs.empty:
    st.info("No documents loaded yet.")
    if st.button("← Back to Document Library"):
        st.switch_page("app.py")
    st.stop()

ids = [int(x) for x in docs["doc_id"].tolist()]
qp = st.query_params.get("doc")
try:
    current = int(qp) if qp is not None else ids[0]
except (TypeError, ValueError):
    current = ids[0]
if current not in ids:
    current = ids[0]
meta = docs[docs["doc_id"] == current].iloc[0]

# ---- breadcrumb + document navigation ----
nav = st.columns([1.4, 4, 1.3, 1.3])
if nav[0].button("← Back to Document Library", use_container_width=True):
    st.switch_page("app.py")
nav[1].markdown(f'<div class="cbp-crumb" style="padding-top:6px;">{meta["case_name"] or ""} &nbsp;/&nbsp; '
                f'Claim {meta["claim_number"] or "—"} &nbsp;/&nbsp; <b>Document #{current}</b></div>',
                unsafe_allow_html=True)
pos = ids.index(current)
if nav[2].button("‹ Previous document", use_container_width=True, disabled=pos == 0):
    st.query_params["doc"] = str(ids[pos - 1])
    st.rerun()
if nav[3].button("Next document ›", type="primary", use_container_width=True, disabled=pos >= len(ids) - 1):
    st.query_params["doc"] = str(ids[pos + 1])
    st.rerun()

# ---- metadata strip ----
full = db.query_df("SELECT file_path, parsed_json FROM dbo.source_documents WHERE doc_id=?", (current,)).iloc[0]
chips = ui.type_chips(meta["doc_types"], limit=4)
st.markdown(f'<div style="font-weight:800;font-size:1.0rem;margin:6px 0;">&#128462; Document #{current} &nbsp; '
            f'{meta["file_name"]}</div>'
            f'<div class="cbp-meta">'
            f'<div><div class="l">Detected types</div><div class="v">{chips}</div></div>'
            f'<div><div class="l">Case</div><div class="v">{meta["case_name"] or "—"}</div></div>'
            f'<div><div class="l">Claim #</div><div class="v">{meta["claim_number"] or "—"}</div></div>'
            f'<div><div class="l">Pages</div><div class="v">{int(meta["page_count"]) if meta["page_count"] and meta["page_count"]==meta["page_count"] else "—"}</div></div>'
            f'<div><div class="l">Method</div><div class="v">{ui.method_chip(meta["extract_method"])}</div></div>'
            f'<div style="flex:1;"><div class="l">Source path</div>'
            f'<div class="v" style="font-weight:500;font-size:.78rem;word-break:break-all;">{full["file_path"]}</div></div>'
            f'</div>', unsafe_allow_html=True)

pages = db.query_df("SELECT page_no, page_type, page_text FROM dbo.document_pages WHERE doc_id=? ORDER BY page_no",
                    (current,))
if pages.empty:
    st.info("This document has no indexed pages (for example, a spreadsheet).")
    ui.footer()
    st.stop()

n = len(pages)
key = f"viewer_page_{current}"
if key not in st.session_state or st.session_state[key] >= n:
    st.session_state[key] = 0

rail, center, right = st.columns([1, 3, 2], gap="medium")

# ---- left: thumbnail rail ----
with rail:
    st.markdown("**Pages**")
    try:
        import pymupdf
        pdf = pymupdf.open(full["file_path"])
    except Exception:
        pdf = None
    for i, (_, pg) in enumerate(pages.iterrows()):
        sel = "sel" if i == st.session_state[key] else ""
        img_html = ""
        if pdf is not None:
            import base64
            png = pdf[int(pg["page_no"]) - 1].get_pixmap(dpi=28).tobytes("png")
            img_html = f'<img src="data:image/png;base64,{base64.b64encode(png).decode()}" style="width:100%;">'
        st.markdown(f'<div class="cbp-thumb {sel}">{img_html}<div class="lbl">{pg["page_type"]}</div></div>',
                    unsafe_allow_html=True)
        if st.button(f"Page {i + 1}", key=f"thumb_{current}_{i}", use_container_width=True):
            st.session_state[key] = i
            st.rerun()

idx = st.session_state[key]
pg = pages.iloc[idx]

# ---- center: page image + nav/zoom ----
with center:
    nc = st.columns([1, 1, 3, 2])
    if nc[0].button("‹", key="pg_prev", disabled=idx == 0, use_container_width=True):
        st.session_state[key] -= 1
        st.rerun()
    if nc[1].button("›", key="pg_next", disabled=idx >= n - 1, use_container_width=True):
        st.session_state[key] += 1
        st.rerun()
    nc[2].markdown(f'<div style="padding-top:6px;">Page <b>{idx + 1}</b> of <b>{n}</b></div>',
                   unsafe_allow_html=True)
    zoom = nc[3].select_slider("zoom", options=[60, 80, 100, 130, 160], value=100,
                               label_visibility="collapsed")
    try:
        import pymupdf
        doc2 = pymupdf.open(full["file_path"])
        png = doc2[int(pg["page_no"]) - 1].get_pixmap(dpi=140).tobytes("png")
        st.image(png, width=int(640 * zoom / 100))
    except Exception:
        st.info("Original page image unavailable (file not on this machine).")

# ---- right: extracted fields / OCR text / JSON ----
with right:
    parsed = {}
    try:
        parsed = json.loads(full["parsed_json"]) if full["parsed_json"] else {}
    except Exception:
        parsed = {}

    # heuristic extraction confidence = populated fields / fields attempted on this doc
    tracked = {k: v for k, v in parsed.items()
               if k not in ("lines", "eobs", "page_kinds", "dx_codes", "doc_kind") and not isinstance(v, (list, dict))}
    filled = [k for k, v in tracked.items() if v not in (None, "", [])]
    conf = int(len(filled) / len(tracked) * 100) if tracked else 0

    t_fields, t_ocr, t_json = st.tabs(["Extracted fields", "OCR text", "JSON"])
    with t_fields:
        st.markdown(f'<div style="display:flex;justify-content:space-between;">'
                    f'<span style="color:var(--mute);font-size:.8rem;">Extraction confidence</span>'
                    f'<b>{conf}%</b></div>'
                    f'<div class="cbp-conf"><span style="width:{conf}%"></span></div>'
                    f'<div style="color:var(--mute);font-size:.74rem;margin:3px 0 10px;">'
                    f'{len(filled)} of {len(tracked)} tracked fields detected (heuristic)</div>',
                    unsafe_allow_html=True)

        def dot(v):
            return ui.confidence_dot(v not in (None, "", []))

        groups = {
            "Patient / Claimant": [("Name", parsed.get("patient_name") or parsed.get("claimant_name"))],
            "Insured / Member": [("ID", parsed.get("insured_id") or parsed.get("member_id")),
                                 ("Member name", parsed.get("member_name")),
                                 ("Policy / group", parsed.get("policy_group_no") or parsed.get("policy_no"))],
            "Claim": [("Provider", parsed.get("provider_name")),
                      ("Provider TIN", parsed.get("provider_tin")),
                      ("Patient account", parsed.get("patient_account_no")),
                      ("Total charge", parsed.get("total_charge"))],
        }
        html_parts = []
        for gname, fields in groups.items():
            if not any(v for _, v in fields):
                continue
            html_parts.append(f'<div class="cbp-grp-h">{gname}</div>')
            for lbl, val in fields:
                html_parts.append(ui.field_block(lbl, val, dot(val)))
        if parsed.get("dx_codes"):
            html_parts.append('<div class="cbp-grp-h">Diagnoses</div>')
            html_parts.append(ui.field_block("ICD-10 codes", ", ".join(parsed["dx_codes"]), ui.confidence_dot(True)))
        st.markdown("".join(html_parts) or "No structured fields on this document.", unsafe_allow_html=True)

    with t_ocr:
        st.text_area("ocr", pg["page_text"] or "(no text)", height=520, label_visibility="collapsed")
    with t_json:
        st.json(parsed)

ui.footer()
