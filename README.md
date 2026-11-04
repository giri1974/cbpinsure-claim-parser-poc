# CBPInsure Claim Parser POC

Parses the sample claim packages (policy, claim form, scanned CMS-1500/UB-04 bills, EOB/ERA pages,
accumulator xls) and loads them into SQL Server LocalDB database **CBPInsureClaims**.

## Run
```
.venv\Scripts\python run_ingest.py --reset      # CLI: parse samples and load DB
.venv\Scripts\streamlit run app.py              # UI
```
First OCR run is slow (~20 s per scanned file); results are cached in `ocr_cache/`.

## Notes
* POC cap: 10 files per case folder (`MAX_FILES_PER_CASE`), policy/claim form/accumulator first, then bills.
* OCR: RapidOCR (pip only). If Tesseract is installed it is used automatically.
* Tables: policies, members, claimants, claims (19 import fields + review flags), claim_line_items,
  source_documents (doc_id), document_pages (OCR text per page by doc_id), accumulator_lines.
* UI tab 5 retrieves any document by Document ID, shows page image + OCR text, and searches all OCR text.
* Extraction is rule-based on noisy OCR: activity code / date of loss / TIN are flagged `needs_review`
  when missing; fix them in the "Claims" tab. Tab 4 compares parsed lines to the Klein accumulator.
