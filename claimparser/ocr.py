"""Text extraction for PDFs: native text layer first, OCR fallback per page.

OCR engines (in order of preference):
  * Tesseract via pytesseract, if the tesseract.exe binary is found
  * RapidOCR (pure pip, ONNX) - default, no admin install required
Results are cached on disk (ocr_cache/) keyed by file path + size + mtime so
re-runs are fast.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import warnings
from pathlib import Path

import numpy as np
import pymupdf

warnings.filterwarnings("ignore")

CACHE_DIR = Path(__file__).resolve().parent.parent / "ocr_cache"
CACHE_DIR.mkdir(exist_ok=True)

_rapid = None
_tess_ok = None


def _tesseract_available() -> bool:
    global _tess_ok
    if _tess_ok is None:
        cmd = os.getenv("TESSERACT_CMD") or shutil.which("tesseract")
        if not cmd:
            for p in (r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                      r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"):
                if os.path.exists(p):
                    cmd = p
                    break
        if cmd and os.path.exists(cmd):
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = cmd
            _tess_ok = True
        else:
            _tess_ok = False
    return _tess_ok


def _rapid_engine():
    global _rapid
    if _rapid is None:
        from rapidocr_onnxruntime import RapidOCR
        _rapid = RapidOCR()
    return _rapid


def _ocr_image(img: np.ndarray) -> str:
    """OCR one page image, return text with layout-ish line grouping."""
    if _tesseract_available():
        import pytesseract
        from PIL import Image
        return pytesseract.image_to_string(Image.fromarray(img), config="--psm 6")
    res, _ = _rapid_engine()(img)
    rows: dict[int, list] = {}
    for box, txt, _score in (res or []):
        ys = [p[1] for p in box]
        y = int(round(float(np.mean(ys)) / 14.0))
        rows.setdefault(y, []).append((box[0][0], txt))
    lines = ["  ".join(t for _, t in sorted(rows[y])) for y in sorted(rows)]
    return "\n".join(lines)


def _cache_path(pdf: Path, max_pages: int | None) -> Path:
    st = pdf.stat()
    key = f"{pdf.resolve()}|{st.st_size}|{int(st.st_mtime)}|{max_pages}"
    return CACHE_DIR / (hashlib.md5(key.encode()).hexdigest() + ".json")


def extract_pdf(path: str | Path, max_pages: int | None = None, dpi: int = 200) -> dict:
    """Return {'pages': [str,...], 'method': 'text'|'ocr'|'mixed', 'page_count': n}."""
    pdf = Path(path)
    cp = _cache_path(pdf, max_pages)
    if cp.exists():
        return json.loads(cp.read_text(encoding="utf-8"))

    doc = pymupdf.open(pdf)
    pages: list[str] = []
    used = set()
    for i, page in enumerate(doc):
        if max_pages is not None and i >= max_pages:
            break
        txt = page.get_text().strip()
        if len(txt) >= 40:
            pages.append(txt)
            used.add("text")
            continue
        pix = page.get_pixmap(dpi=dpi)
        img = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3]
        pages.append(_ocr_image(img))
        used.add("ocr")
    method = "mixed" if len(used) > 1 else (used.pop() if used else "text")
    out = {"pages": pages, "method": method, "page_count": len(doc)}
    cp.write_text(json.dumps(out), encoding="utf-8")
    return out
