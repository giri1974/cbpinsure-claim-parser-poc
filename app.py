"""CBPInsure Claim Parser POC - main page.

Run:  streamlit run app.py
Tabs: Intake, Claims Review, Service Lines, Accumulator Check, Document Library.
Clicking a Document ID or Case Name in the Document Library opens a dedicated
viewer page (pages/document_viewer.py).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from claimparser import db, ingest, ui
from claimparser.config import DEFAULT_SAMPLES

ui.page_setup("Claims Intake")
ui.topbar()

# ---- KPI strip -----------------------------------------------------------------------------------
_k = db.query_df("""SELECT (SELECT COUNT(*) FROM dbo.claims WHERE needs_review = 1) AS review,
                           (SELECT COUNT(*) FROM dbo.claim_line_items) AS lines,
                           (SELECT COUNT(*) FROM dbo.source_documents) AS docs,
                           (SELECT COUNT(*) FROM dbo.document_pages) AS pages""").iloc[0]
_review = int(_k["review"])
ui.kpi_row(_review, int(_k["lines"]), int(_k["docs"]), int(_k["pages"]))

tab_ing, tab_claims, tab_lines, tab_val, tab_docs = st.tabs(
    [":material/upload: Intake",
     f":material/fact_check: Claims Review  ({_review})" if _review else ":material/fact_check: Claims Review",
     ":material/table_rows: Service Lines",
     ":material/verified: Accumulator Check",
     ":material/folder_open: Document Library"])

# ------------------------------------------------------------------ intake
with tab_ing:
    ui.page_title("Intake", "Load a claim package. Scanned bills are read with OCR and stored against a Document ID.",
                  secure=True)
    lc, rc = st.columns(2, gap="medium")
    with lc:
        with st.container(border=True):
            st.markdown("####  Process claim folder")
            folder = st.text_input("Folder with case sub-folders", str(DEFAULT_SAMPLES))
            if not Path(folder).exists():
                st.warning("This folder is not available on this server. Use the upload option on the right.")
            reset = st.checkbox("Clear existing data before loading", value=False,
                                help="This replaces all previously indexed claim data.")
            if reset:
                st.markdown('<span style="color:#D64550;font-size:.8rem;">'
                            'This replaces all previously indexed claim data.</span>', unsafe_allow_html=True)
            if st.button("▶  Parse & load folder", type="primary", disabled=not Path(folder).exists()):
                log = st.empty()
                lines: list[str] = []

                def progress(msg: str) -> None:
                    lines.append(msg)
                    log.code("\n".join(lines[-25:]))

                with st.spinner("Parsing (scanned PDFs are OCR'd, first run is slow; results are cached)..."):
                    summary = ingest.ingest_root(Path(folder), progress, reset=reset)
                st.success(f"Loaded: {summary}")
                st.rerun()
    with rc:
        with st.container(border=True):
            st.markdown("####  Upload a document")
            up = st.file_uploader("PDF, XLS, XLSX or ZIP of a case folder - up to 200 MB",
                                  type=["pdf", "xls", "xlsx", "zip"])
            if up and st.button("Parse uploaded file", type="primary"):
                tmp = Path(tempfile.mkdtemp(prefix="claims_"))
                p = tmp / up.name
                p.write_bytes(up.getbuffer())
                with st.spinner("Parsing..."):
                    summary = ingest.ingest_upload(p, tmp / "work", st.write)
                st.success(f"Loaded: {summary}")
                st.rerun()

    # ---- Recent activity (real data from source_documents) ----
    act = db.query_df("""
        SELECT d.case_name,
               COUNT(*) AS docs,
               SUM(COALESCE(d.page_count,0)) AS pages,
               SUM(CASE WHEN d.extract_method IN ('ocr','mixed') THEN COALESCE(d.page_count,0) ELSE 0 END) AS ocr_pages,
               (SELECT MAX(CASE WHEN c.needs_review = 1 THEN 1 ELSE 0 END)
                  FROM dbo.claims c WHERE c.case_name = d.case_name) AS needs_review
        FROM dbo.source_documents d
        GROUP BY d.case_name ORDER BY d.case_name""")
    with st.container(border=True):
        hd1, hd2 = st.columns([6, 1])
        hd1.markdown("####  Recent activity")
        hd2.caption("Processing status")
        if act.empty:
            st.info("No claim packages loaded yet.")
        else:
            rows = ""
            for _, r in act.iterrows():
                docs_n, pages_n, ocr_n = int(r["docs"]), int(r["pages"]), int(r["ocr_pages"])
                pct = int(ocr_n / pages_n * 100) if pages_n else 100
                status = (ui.chip("Needs review", "chip-review") if r["needs_review"]
                          else ui.chip("Complete", "chip-ok"))
                detail = f"{docs_n} documents · {ocr_n} of {pages_n} pages OCR'd" if ocr_n else \
                         f"{docs_n} documents · {pages_n} pages indexed"
                rows += (f'<tr><td>&#128462; <b>{r["case_name"]}</b></td>'
                         f'<td style="color:var(--mute);">{detail}</td>'
                         f'<td style="width:180px;"><div class="cbp-progress"><span style="width:{pct}%"></span></div></td>'
                         f'<td style="text-align:right;">{status}</td></tr>')
            st.markdown(f'<table class="cbp-tbl">{rows}</table>', unsafe_allow_html=True)

# ------------------------------------------------------------------ claims
with tab_claims:
    ui.hint("Claims flagged <b>Needs review</b> are missing items such as activity code or date of loss. "
            "Pick a claim to complete it.")
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
            b = ("review", "Needs review") if cur["needs_review"] else ("ok", "Reviewed")
            st.markdown(ui.badge(*b), unsafe_allow_html=True)
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
    ui.hint("Procedure-level detail extracted from each bill (CPT/HCPCS, dates of service, charges).")
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
    ui.hint("Compares extracted service lines with the client claims-accumulator spreadsheet, where one was provided.")
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

# ------------------------------------------------------------------ document library
with tab_docs:
    ui.hint("Every scanned document is indexed by Document ID. Search page text, or click a row and "
            "<b>Open in viewer</b> to see the original pages beside the extracted text on a dedicated page.")
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
                          extract_method FROM dbo.source_documents ORDER BY doc_id""")
    if docs.empty:
        st.info("No documents yet. Load a claim folder on the Intake tab.")
    else:
        st.markdown("##### Click a document to open the viewer")
        # Row-selectable table: selecting a row navigates to the dedicated viewer page.
        event = st.dataframe(
            docs, use_container_width=True, hide_index=True,
            on_select="rerun", selection_mode="single-row",
            column_config={
                "doc_id": st.column_config.NumberColumn("Doc ID", width="small"),
                "case_name": "Case", "claim_number": st.column_config.TextColumn("Claim #", width="small"),
                "file_name": "File", "doc_types": "Detected types",
                "page_count": st.column_config.NumberColumn("Pages", width="small"),
                "extract_method": "Method",
            })
        sel = event.selection.rows if event and event.selection else []
        if sel:
            ui.open_document(int(docs.iloc[sel[0]]["doc_id"]))

        st.write("")
        c1, c2 = st.columns([2, 5])
        dlabels = {int(r["doc_id"]): f'#{int(r["doc_id"])}  -  {r["file_name"]}  ({r["case_name"]})'
                   for _, r in docs.iterrows()}
        pick_doc = c1.selectbox("or pick a Document ID", list(dlabels), format_func=lambda d: dlabels[d])
        if c2.button("Open in viewer  ↗", type="primary"):
            ui.open_document(int(pick_doc))

ui.footer()
