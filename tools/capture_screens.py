"""Capture full-page screenshots of every screen and combine them into one PDF.

The Streamlit app must already be running (streamlit run app.py). Usage:

    python tools/capture_screens.py --url http://localhost:8501 --doc 176 --out CBPInsure_POC_Screens.pdf

Uses Playwright (Chromium). Each Streamlit tab is clicked in turn; the Document
Viewer page is captured via its ?doc= URL. Output is an A-wide PDF, one screen
per page.
"""
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import img2pdf
from playwright.sync_api import sync_playwright

TABS = ["Intake", "Claims Review", "Service Lines", "Accumulator Check", "Document Library"]


def _settle(page, ms: int = 1400) -> None:
    try:
        page.wait_for_selector("text=Claims Intake & Document Extraction", timeout=20000)
    except Exception:
        pass
    # wait until Streamlit's "running" spinner is gone
    for _ in range(40):
        if page.locator('[data-testid="stStatusWidget"]').count() == 0:
            break
        page.wait_for_timeout(200)
    page.wait_for_timeout(ms)


def capture(url: str, doc_id: int, out: Path) -> Path:
    shots: list[str] = []
    tmp = Path(tempfile.mkdtemp(prefix="cbp_shots_"))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=2)

        page.goto(url, wait_until="networkidle")
        _settle(page, 2000)

        for i, label in enumerate(TABS):
            tab = page.get_by_role("tab", name=label).first
            tab.click()
            _settle(page)
            # expand the "Parsed fields" expander etc. are page-specific; default view is fine
            f = tmp / f"{i:02d}_{label.replace(' ', '_')}.png"
            page.screenshot(path=str(f), full_page=True)
            shots.append(str(f))

        # Document Viewer (dedicated page)
        page.goto(f"{url}/document_viewer?doc={doc_id}", wait_until="networkidle")
        _settle(page, 2000)
        f = tmp / "05_Document_Viewer.png"
        page.screenshot(path=str(f), full_page=True)
        shots.append(str(f))

        browser.close()

    out.write_bytes(img2pdf.convert(shots))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8501")
    ap.add_argument("--doc", type=int, default=176)
    ap.add_argument("--out", default="CBPInsure_POC_Screens.pdf")
    a = ap.parse_args()
    out = capture(a.url.rstrip("/"), a.doc, Path(a.out))
    print("WROTE", out.resolve())


if __name__ == "__main__":
    main()
