"""Screenshot one or more screens of the running app for visual QA.

  python tools/shot.py intake claims lines accum docs viewer

Writes PNGs into design/_shots/. Requires the app running on :8501.
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "design" / "_shots"
OUT.mkdir(parents=True, exist_ok=True)
URL = "http://localhost:8501"
TAB = {"intake": "Intake", "claims": "Claims Review", "lines": "Service Lines",
       "accum": "Accumulator Check", "docs": "Document Library"}


def settle(page, ms=1600):
    for _ in range(50):
        if page.locator('[data-testid="stStatusWidget"]').count() == 0:
            break
        page.wait_for_timeout(200)
    page.wait_for_timeout(ms)


def main():
    targets = sys.argv[1:] or ["intake"]
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1500, "height": 950}, device_scale_factor=2)
        pg.goto(URL, wait_until="networkidle")
        settle(pg, 2500)
        for t in targets:
            if t == "viewer":
                pg.goto(f"{URL}/document_viewer?doc=176", wait_until="networkidle")
                settle(pg, 2000)
            elif t in TAB:
                pg.goto(URL, wait_until="networkidle")
                settle(pg)
                pg.get_by_role("tab", name=TAB[t]).first.click()
                settle(pg)
            pg.screenshot(path=str(OUT / f"{t}.png"), full_page=True)
            print("shot", t)
        b.close()


if __name__ == "__main__":
    main()
