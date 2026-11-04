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

## Database switch (Local / Cloud)
* The sidebar has a **Database** switch: *Cloud database* (hosted SQL Server) or *Local database* (LocalDB on this PC).
  On a hosted/Linux server only the cloud option is used.
* CLI: `python run_ingest.py --db cloud --reset` (or `--db local`). Env var `DB_MODE=cloud|local` also works.
* Credentials are never in the repo: cloud settings come from Streamlit secrets `[cloud]`
  (see `.streamlit/secrets.toml.example`), then `CLOUD_SQL_*` env vars, then `../Connection_String.txt`.
* Cloud mode uses `pymssql` (no ODBC driver needed), local mode uses `pyodbc`.

## Deploy to Streamlit Community Cloud
1. Repo on GitHub (connect GitHub access for private repos), main file `app.py`, Python 3.11.
2. App -> Settings -> Secrets: paste the `[cloud]` block from `.streamlit/secrets.toml.example` with real values.
3. The database host must accept connections from the internet (allow-list / remote access enabled).
4. Sample files are not in the repo: load data once with `python run_ingest.py --db cloud --reset`
   from a PC that can reach the cloud database; deployed users can also upload PDFs/ZIPs.
