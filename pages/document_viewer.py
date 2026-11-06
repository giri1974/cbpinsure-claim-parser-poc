"""Dedicated document viewer page. Opened from the Document Library by clicking a
row (or the Open button); the document id arrives in the ?doc= query param.

Shows one page at a time (Prev/Next + slider) with the original scan beside the
extracted/OCR text, plus the parsed fields and page navigation by type.
"""
from __future__ import annotations

import streamlit as st

from claimparser import db, ui

ui.page_setup("Document Viewer")
ui.topbar()

# ---- resolve which document to show ---------------------------------------------------------------
docs = db.query_df("""SELECT doc_id, case_name, claim_number, file_name, doc_types, page_count,
                      extract_method FROM dbo.source_documents ORDER BY doc_id""")
if docs.empty:
    st.info("No documents loaded yet.")
    if st.button("← Back to Claims workspace"):
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

# ---- top bar: back + document picker --------------------------------------------------------------
top1, top2, top3 = st.columns([1.3, 4, 1.4])
if top1.button("← Back to workspace", use_container_width=True):
    st.switch_page("app.py")

dlabels = {int(r["doc_id"]): f'#{int(r["doc_id"])}  -  {r["file_name"]}  ({r["case_name"]})'
           for _, r in docs.iterrows()}
chosen = top2.selectbox("Document", ids, index=ids.index(current),
                        format_func=lambda d: dlabels[d], label_visibility="collapsed")
if chosen != current:
    st.query_params["doc"] = str(chosen)
    st.rerun()

pos = ids.index(current)
if top3.button("Next document →", use_container_width=True, disabled=pos >= len(ids) - 1):
    st.query_params["doc"] = str(ids[pos + 1])
    st.rerun()

meta = db.query_df("""SELECT case_name, claim_number, file_name, file_path, doc_types, page_count,
                      extract_method, parsed_json FROM dbo.source_documents WHERE doc_id=?""", (current,)).iloc[0]

st.markdown(f"### Document #{current} &nbsp; {ui.badge('ok', meta['doc_types'] or 'document')}",
            unsafe_allow_html=True)
mc1, mc2, mc3, mc4 = st.columns(4)
mc1.markdown(f"**Case**\n\n{meta['case_name'] or '-'}")
mc2.markdown(f"**Claim #**\n\n{meta['claim_number'] or '-'}")
mc3.markdown(f"**Pages**\n\n{int(meta['page_count']) if meta['page_count'] else '-'}")
mc4.markdown(f"**OCR method**\n\n{meta['extract_method'] or '-'}")
st.caption(f"Source file: `{meta['file_path']}`")

with st.expander("Parsed fields (JSON)"):
    st.json(meta["parsed_json"])

pages = db.query_df("SELECT page_no, page_type, page_text FROM dbo.document_pages WHERE doc_id=? ORDER BY page_no",
                    (current,))
if pages.empty:
    st.info("This document has no indexed pages (for example, a spreadsheet).")
    ui.footer()
    st.stop()

# ---- page pager -----------------------------------------------------------------------------------
n = len(pages)
key = f"viewer_page_{current}"
if key not in st.session_state or st.session_state[key] >= n:
    st.session_state[key] = 0

b1, b2, b3, b4 = st.columns([1, 1, 4, 3])
if b1.button("◀ Prev", disabled=st.session_state[key] == 0, use_container_width=True):
    st.session_state[key] -= 1
    st.rerun()
if b2.button("Next ▶", disabled=st.session_state[key] >= n - 1, use_container_width=True):
    st.session_state[key] += 1
    st.rerun()
jump = b3.select_slider("Page", options=list(range(1, n + 1)), value=st.session_state[key] + 1) if n > 1 else 1
if jump - 1 != st.session_state[key]:
    st.session_state[key] = jump - 1
    st.rerun()

idx = st.session_state[key]
pg = pages.iloc[idx]
b4.markdown(f"Page **{idx + 1}** of **{n}** &nbsp; {ui.badge('ok', pg['page_type'])}", unsafe_allow_html=True)

img_col, txt_col = st.columns([1, 1], gap="medium")
with img_col:
    st.markdown("**Original page**")
    try:
        import pymupdf
        pdf = pymupdf.open(meta["file_path"])
        st.image(pdf[int(pg["page_no"]) - 1].get_pixmap(dpi=120).tobytes("png"), use_container_width=True)
    except Exception:
        st.info("Original page image unavailable (file not on this machine).")
with txt_col:
    st.markdown("**Extracted / OCR text**")
    st.text_area("page text", pg["page_text"] or "(no text)", height=640, label_visibility="collapsed")

ui.footer()
