"""CBPInsure Claim Parser POC - main page.

Run:  streamlit run app.py
Tabs: Intake, Claims Review, Service Lines, Accumulator Check, Document Library.
Clicking a Document ID or Case Name in the Document Library opens a dedicated
viewer page (pages/document_viewer.py).
"""
from __future__ import annotations

import tempfile
from html import escape as html_escape
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
    th1, th2 = st.columns([6, 1])
    with th1:
        ui.page_title("Claims Review",
                      "Claims flagged <b>Needs review</b> are missing details such as activity code or date of loss. "
                      "Select a claim to complete it.")
    claims = db.query_df("SELECT * FROM dbo.claims ORDER BY case_name, claim_number")
    if claims.empty:
        st.info("No claims yet. Load a claim folder on the Intake tab.")
    else:
        th2.download_button("⤓ Download CSV", claims.to_csv(index=False).encode(),
                            "claims.csv", "text/csv", use_container_width=True)
        with st.container(border=True):
            f1, f2, f3 = st.columns([2, 3, 3])
            cases = ["All cases"] + sorted(claims["case_name"].dropna().unique().tolist())
            pick_case = f1.selectbox("Case", cases, label_visibility="collapsed")
            n_review = int((claims["needs_review"] == True).sum())
            seg = f2.radio("filter", ["All", f"Needs review ({n_review})", "Complete"],
                           horizontal=True, label_visibility="collapsed")
            search = f3.text_input("search", placeholder="Search claim #, claimant, provider...",
                                   label_visibility="collapsed")

            view = claims.copy()
            if pick_case != "All cases":
                view = view[view["case_name"] == pick_case]
            if seg.startswith("Needs review"):
                view = view[view["needs_review"] == True]
            elif seg == "Complete":
                view = view[view["needs_review"] == False]
            if search:
                s = search.lower()
                mask = view.apply(lambda r: s in " ".join(
                    str(r[c]).lower() for c in ["claim_number", "claimant_name", "provider_name", "case_name"]), axis=1)
                view = view[mask]

            nr = int((view["needs_review"] == True).sum())
            st.markdown(f'<div style="margin:2px 0 6px;">{ui.chip("•", "chip-review")} '
                        f'<b>Needs review ({nr})</b></div>', unsafe_allow_html=True)

            rows = []
            for _, r in view.iterrows():
                status = ui.chip("● Needs review", "chip-review") if r["needs_review"] else ui.chip("● Complete", "chip-ok")
                rows.append(
                    "<tr>"
                    f'<td>{status}</td>'
                    f'<td><b>{r["claim_number"]}</b></td>'
                    f'<td style="color:var(--mute);">{r["case_name"] or "—"}</td>'
                    f'<td><span class="cbp-ava" style="width:22px;height:22px;font-size:.62rem;display:inline-flex;'
                    f'margin-right:6px;vertical-align:middle;">{ui.initials(r["claimant_name"])}</span>'
                    f'{ui.text_or_missing(r["claimant_name"])}</td>'
                    f'<td>{ui.date_or_missing(r["date_of_service_from"])}</td>'
                    f'<td>{ui.date_or_missing(r["date_of_service_thru"])}</td>'
                    f'<td>{ui.text_or_missing(r["diagnosis_code"])}</td>'
                    f'<td>{ui.text_or_missing(r["activity_code"])}</td>'
                    f'<td>{ui.text_or_missing(r["provider_tin"])}</td>'
                    f'<td>{ui.text_or_missing(r["provider_name"])}</td>'
                    f'<td class="cbp-num">{ui.money(r["total_charges"])}</td>'
                    f'<td class="cbp-num">{ui.money(r["total_cob_allowable"])}</td>'
                    f'<td class="cbp-num">{ui.money(r["total_primary_paid"])}</td>'
                    "</tr>")
            headers = ["Status", "Claim #", "Case", "Claimant", "DOS from", "DOS thru", "Dx", "Activity",
                       "TIN", "Provider", "Charges", "COB allowable", "Primary paid"]
            aligns = [""] * 10 + ["r", "r", "r"]
            st.markdown(f'<div style="overflow-x:auto;">{ui.html_table(headers, rows, aligns)}</div>',
                        unsafe_allow_html=True)
            st.caption(f"Showing {len(view)} of {len(claims)} claims")

        st.subheader("Complete missing claim details")
        view_full = view
        labels = {r["claim_number"]: f'{r["claim_number"]}  -  {r["claimant_name"] or "?"}'
                  f'  ({"needs review" if r["needs_review"] else "reviewed"})'
                  for _, r in view_full.iterrows()} if not view_full.empty else {}
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
    tl1, tl2 = st.columns([6, 1])
    with tl1:
        ui.page_title("Service Lines", "Procedure-level detail extracted from each bill (CPT/HCPCS, dates of service, charges).")
    li = db.query_df("""SELECT l.claim_number, l.bill_file, l.line_no, l.dos_from, l.dos_thru, l.cpt_code,
                        l.procedure_desc, l.provider_tin, l.provider_name, l.charge_amount, l.allowed_amount,
                        l.paid_amount, c.claimant_name
                        FROM dbo.claim_line_items l
                        LEFT JOIN dbo.claims c ON c.claim_number = l.claim_number
                        ORDER BY l.claim_number, l.bill_file, l.line_no""")
    if li.empty:
        st.info("No service lines yet. Load a claim folder on the Intake tab.")
    else:
        tl2.download_button("⤓ Download CSV", li.drop(columns=["claimant_name"]).to_csv(index=False).encode(),
                            "service_lines.csv", "text/csv", use_container_width=True)
        with st.container(border=True):
            s1, s2, s3 = st.columns([2, 3, 2])
            claim_opts = ["All claims"] + sorted(li["claim_number"].unique().tolist())
            pick = s1.selectbox("Claim", claim_opts, key="line_claim", label_visibility="collapsed")
            search = s2.text_input("search_lines", placeholder="Search bill, CPT, provider...",
                                   label_visibility="collapsed")
            lv = li if pick == "All claims" else li[li["claim_number"] == pick]
            if search:
                s = search.lower()
                lv = lv[lv.apply(lambda r: s in " ".join(
                    str(r[c]).lower() for c in ["bill_file", "cpt_code", "procedure_desc", "provider_name"]), axis=1)]
            s3.markdown(f'<div style="text-align:right;color:var(--mute);padding-top:6px;">'
                        f'Showing {len(lv)} of {len(li)} lines</div>', unsafe_allow_html=True)

            headers = ["Line #", "Bill file", "DOS from", "DOS thru", "CPT", "Procedure", "TIN",
                       "Provider", "Charge", "Allowed", "Paid"]
            aligns = [""] * 8 + ["r", "r", "r"]
            rows = []
            for cnum, grp in lv.groupby("claim_number", sort=False):
                claimant = grp["claimant_name"].iloc[0] or "—"
                subtotal = grp["charge_amount"].dropna().sum()
                nlines = len(grp)
                rows.append(
                    f'<tr class="cbp-grp"><td colspan="8">▾ <b>{cnum}</b> &nbsp;'
                    f'<span class="cbp-ava" style="width:20px;height:20px;font-size:.58rem;display:inline-flex;'
                    f'vertical-align:middle;">{ui.initials(claimant)}</span> '
                    f'<span style="color:var(--mute);font-weight:600;">{html_escape(claimant)} · {nlines} line'
                    f'{"s" if nlines != 1 else ""}</span></td>'
                    f'<td colspan="3" class="cbp-sub-amt">Subtotal {ui.money(subtotal)}</td></tr>')
                for _, r in grp.iterrows():
                    rows.append(
                        "<tr>"
                        f'<td>L{int(r["line_no"]) if r["line_no"] else "-"}</td>'
                        f'<td>&#128462; {html_escape(r["bill_file"])}</td>'
                        f'<td>{ui.date_or_missing(r["dos_from"])}</td>'
                        f'<td>{ui.date_or_missing(r["dos_thru"])}</td>'
                        f'<td>{ui.text_or_missing(r["cpt_code"])}</td>'
                        f'<td>{ui.text_or_missing(r["procedure_desc"])}</td>'
                        f'<td>{ui.text_or_missing(r["provider_tin"])}</td>'
                        f'<td>{ui.text_or_missing(r["provider_name"])}</td>'
                        f'<td class="cbp-num">{ui.money(r["charge_amount"])}</td>'
                        f'<td class="cbp-num">{ui.money(r["allowed_amount"])}</td>'
                        f'<td class="cbp-num">{ui.money(r["paid_amount"])}</td>'
                        "</tr>")
            st.markdown(f'<div style="overflow-x:auto;">{ui.html_table(headers, rows, aligns)}</div>',
                        unsafe_allow_html=True)

# ------------------------------------------------------------------ validation
with tab_val:
    ui.page_title("Accumulator Check", "Compares extracted service lines with the client's claims-accumulator spreadsheet.")
    val = db.query_df("""
        SELECT a.claim_no, a.line_number, a.procedure_code AS acc_cpt, a.total_charges AS acc_charges,
               l.cpt_code AS parsed_cpt, l.charge_amount AS parsed_charges,
               CASE WHEN l.line_id IS NULL THEN 'Missing in parsed'
                    WHEN l.charge_amount = a.total_charges THEN 'Match'
                    ELSE 'Charge differs' END AS status
        FROM dbo.accumulator_lines a
        LEFT JOIN dbo.claim_line_items l
          ON l.claim_number = a.claim_no AND l.cpt_code = LTRIM(RTRIM(a.procedure_code))
        ORDER BY a.claim_no, a.line_number""")
    if val.empty:
        st.info("No accumulator spreadsheet was provided for the loaded cases, so there is nothing to compare.")
    else:
        total = len(val)
        n_match = int((val.status == "Match").sum())
        n_diff = int((val.status == "Charge differs").sum())
        n_miss = int((val.status == "Missing in parsed").sum())
        rate = int(n_match / total * 100)

        c1, c2, c3, c4 = st.columns([1.1, 1.1, 1.3, 2])
        c1.markdown(f'<div class="cbp-card"><div class="cbp-kpi-l">Accumulator lines</div>'
                    f'<div class="cbp-kpi-n">{total}</div></div>', unsafe_allow_html=True)
        c2.markdown(f'<div class="cbp-card"><div class="cbp-kpi-l">Charge matched</div>'
                    f'<div class="cbp-kpi-n">{n_match}</div></div>', unsafe_allow_html=True)
        gauge_color = ui.GREEN if rate >= 70 else (ui.AMBER if rate >= 40 else ui.RED)
        c3.markdown(f'<div class="cbp-card" style="display:flex;align-items:center;justify-content:space-between;">'
                    f'<div><div class="cbp-kpi-l">Match rate</div>'
                    f'<div class="cbp-kpi-n" style="color:{gauge_color};">{rate}%</div></div>'
                    f'{ui.donut(rate, gauge_color)}</div>', unsafe_allow_html=True)
        c4.markdown(f'<div class="cbp-card"><div class="cbp-kpi-l">Status breakdown</div>'
                    + ui.seg_bar([("Match", n_match, ui.GREEN), ("Charge differs", n_diff, ui.AMBER),
                                  ("Missing in parsed", n_miss, ui.RED)]) + '</div>', unsafe_allow_html=True)

        if st.session_state.get("hide_acc_info") is not True:
            ib1, ib2 = st.columns([20, 1])
            ib1.markdown('<div class="cbp-info"><b>&#9432; Why some lines differ</b> &nbsp; Facility bills (UB-04) use '
                         'revenue codes that differ from the accumulator\'s adjudicated procedure codes, so some lines '
                         'may show as differing even when the extraction is correct.</div>', unsafe_allow_html=True)
            if ib2.button("✕", key="dismiss_acc"):
                st.session_state["hide_acc_info"] = True
                st.rerun()

        with st.container(border=True):
            seg = st.radio("accfilter", [f"All  {total}", f"Match  {n_match}",
                                         f"Charge differs  {n_diff}", f"Missing in parsed  {n_miss}"],
                           horizontal=True, label_visibility="collapsed")
            fv = val
            if seg.startswith("Match"):
                fv = val[val.status == "Match"]
            elif seg.startswith("Charge differs"):
                fv = val[val.status == "Charge differs"]
            elif seg.startswith("Missing"):
                fv = val[val.status == "Missing in parsed"]

            status_chip = {"Match": ui.chip("● Match", "chip-ok"),
                           "Charge differs": ui.chip("● Charge differs", "chip-review"),
                           "Missing in parsed": ui.chip("● Missing in parsed", "chip-red")}
            def _num(x):
                return float(x) if x is not None and x == x else 0.0
            _vars = [abs(_num(r["parsed_charges"]) - _num(r["acc_charges"])) for _, r in fv.iterrows()]
            max_var = max(_vars) if _vars and max(_vars) > 0 else 1.0
            rows = []
            for _, r in fv.iterrows():
                bad = r["status"] != "Match"
                pc, ac = r["parsed_charges"], r["acc_charges"]
                var = None
                if pc is not None and pc == pc and ac is not None and ac == ac:
                    var = round(float(pc) - float(ac), 2)
                if var is None or var == 0:
                    var_html = '<span style="color:#B6C0CE;">—</span>'
                else:
                    w = int(abs(var) / max_var * 90)
                    var_html = (f'<span style="color:{ui.RED};font-weight:700;">{"+" if var > 0 else ""}'
                                f'${var:,.2f}</span><span class="cbp-varbar" style="width:{w}px;"></span>')
                rows.append(
                    f'<tr class="{"cbp-row-bad" if bad else ""}">'
                    f'<td><b>{r["claim_no"]}</b></td>'
                    f'<td>L{int(r["line_number"]) if r["line_number"] else "-"}</td>'
                    f'<td>{ui.text_or_missing(r["acc_cpt"])}</td>'
                    f'<td class="cbp-num">{ui.money(r["acc_charges"])}</td>'
                    f'<td>{ui.text_or_missing(r["parsed_cpt"])}</td>'
                    f'<td class="cbp-num">{ui.money(r["parsed_charges"])}</td>'
                    f'<td class="cbp-num">{var_html}</td>'
                    f'<td>{status_chip.get(r["status"], r["status"])}</td>'
                    "</tr>")
            # super-header row
            super_hd = ('<tr><th></th><th></th>'
                        '<th colspan="2" style="text-align:center;color:var(--brand-dark);">Accumulator '
                        '<span style="font-weight:400;color:var(--mute);">client spreadsheet</span></th>'
                        '<th colspan="2" style="text-align:center;color:var(--brand-dark);">Extracted '
                        '<span style="font-weight:400;color:var(--mute);">parsed service line</span></th>'
                        '<th></th><th></th></tr>')
            headers = ["Claim #", "Line", "CPT", "Charge", "Parsed CPT", "Parsed charge", "Variance", "Status"]
            aligns = ["", "", "", "r", "", "r", "r", ""]
            th = "".join(f'<th class="{"cbp-num" if a == "r" else ""}">{h}</th>' for h, a in zip(headers, aligns))
            tbl = (f'<table class="cbp-tbl"><thead>{super_hd}<tr>{th}</tr></thead>'
                   f'<tbody>{"".join(rows)}</tbody></table>')
            st.markdown(f'<div style="overflow-x:auto;">{tbl}</div>', unsafe_allow_html=True)
            st.caption(f"Showing {len(fv)} of {total} lines")

# ------------------------------------------------------------------ document library
with tab_docs:
    ui.page_title("Document Library",
                  "Every scanned document is indexed by Document ID. Search the extracted text or open a "
                  "document to see the original pages beside the extracted data.")
    docs = db.query_df("""SELECT doc_id, case_name, claim_number, file_name, file_path, doc_types,
                          page_count, extract_method FROM dbo.source_documents ORDER BY doc_id""")
    if docs.empty:
        st.info("No documents yet. Load a claim folder on the Intake tab.")
    else:
        with st.container(border=True):
            srow = st.columns([6, 1])
            q = srow[0].text_input("docsearch", placeholder="Search all OCR / extracted text — claim #, name, CPT, TIN...",
                                   label_visibility="collapsed")
            show_filters = srow[1].toggle("Filters", value=False)
            all_types = sorted({t.strip() for dt in docs["doc_types"].dropna() for t in str(dt).split(",")
                                if t.strip() and t.strip() != "instructions"})
            type_pick, method_pick = "All types", "All methods"
            if show_filters:
                fr = st.columns([2, 2, 6])
                type_pick = fr[0].selectbox("Document type", ["All types"] + all_types)
                method_pick = fr[1].selectbox("Extraction method", ["All methods", "text", "ocr", "mixed"])

        # text search across pages
        if q:
            hits = db.query_df("""
                SELECT d.doc_id, d.case_name, d.file_name, p.page_no, p.page_type,
                       SUBSTRING(p.page_text, CASE WHEN CHARINDEX(?, p.page_text) > 60 THEN CHARINDEX(?, p.page_text)-60 ELSE 1 END, 160) AS snippet
                FROM dbo.document_pages p JOIN dbo.source_documents d ON d.doc_id = p.doc_id
                WHERE p.page_text LIKE ? ORDER BY d.doc_id, p.page_no""", (q, q, f"%{q}%"))
            st.markdown(f'<div class="cbp-info">{len(hits)} matching page(s) for "<b>{html_escape(q)}</b>"</div>',
                        unsafe_allow_html=True)
            if not hits.empty:
                hrows = [f'<tr><td><b>#{int(r["doc_id"])}</b></td><td>{html_escape(r["case_name"] or "")}</td>'
                         f'<td>{html_escape(r["file_name"])}</td><td>p{int(r["page_no"])}</td>'
                         f'<td>{ui.chip(r["page_type"], "chip-type")}</td>'
                         f'<td style="color:var(--mute);">…{html_escape(str(r["snippet"]).strip())}…</td></tr>'
                         for _, r in hits.iterrows()]
                st.markdown(ui.html_table(["Doc ID", "Case", "File", "Page", "Type", "Match"], hrows),
                            unsafe_allow_html=True)

        dv = docs.copy()
        if type_pick != "All types":
            dv = dv[dv["doc_types"].fillna("").str.contains(type_pick)]
        if method_pick != "All methods":
            dv = dv[dv["extract_method"] == method_pick]

        tv1, tv2 = st.columns([6, 1])
        tv1.markdown(f'<div style="color:var(--mute);padding-top:6px;">{len(dv)} documents</div>',
                     unsafe_allow_html=True)
        view_mode = tv2.radio("view", ["List", "Grid"], horizontal=True, label_visibility="collapsed")

        if view_mode == "List":
            rows = []
            for _, r in dv.iterrows():
                rows.append(
                    "<tr>"
                    f'<td>{ui.page_thumb(r["file_path"], int(r["doc_id"]))}</td>'
                    f'<td><b>#{int(r["doc_id"])}</b></td>'
                    f'<td>{html_escape(r["case_name"] or "—")}</td>'
                    f'<td>{ui.text_or_missing(r["claim_number"])}</td>'
                    f'<td>&#128462; {html_escape(r["file_name"])}</td>'
                    f'<td>{ui.type_chips(r["doc_types"])}</td>'
                    f'<td>{int(r["page_count"]) if r["page_count"] and r["page_count"] == r["page_count"] else "—"}</td>'
                    f'<td>{ui.method_chip(r["extract_method"])}</td>'
                    "</tr>")
            st.markdown(ui.html_table(
                ["Preview", "Doc ID", "Case", "Claim #", "File name", "Detected types", "Pages", "Method"], rows),
                unsafe_allow_html=True)
        else:
            cols = st.columns(4)
            for i, (_, r) in enumerate(dv.iterrows()):
                with cols[i % 4]:
                    st.markdown(
                        f'<div class="cbp-card" style="text-align:center;padding:12px;">'
                        f'{ui.page_thumb(r["file_path"], int(r["doc_id"]), width=120)}'
                        f'<div style="margin-top:8px;font-weight:700;">#{int(r["doc_id"])}</div>'
                        f'<div style="font-size:.78rem;color:var(--mute);">{html_escape(r["file_name"])}</div>'
                        f'<div style="margin-top:6px;">{ui.type_chips(r["doc_types"])}</div></div>',
                        unsafe_allow_html=True)

        # open-in-viewer (styled HTML tables can't capture clicks, so a compact picker drives navigation)
        st.divider()
        o1, o2 = st.columns([3, 1])
        dlabels = {int(r["doc_id"]): f'#{int(r["doc_id"])} — {r["file_name"]} ({r["case_name"]})'
                   for _, r in dv.iterrows()}
        if dlabels:
            pick_doc = o1.selectbox("Open a document in the viewer", list(dlabels),
                                    format_func=lambda d: dlabels[d])
            o2.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if o2.button("Open in viewer  ↗", type="primary", use_container_width=True):
                ui.open_document(int(pick_doc))

ui.footer()
