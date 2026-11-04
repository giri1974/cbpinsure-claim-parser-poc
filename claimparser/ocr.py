"""Text extraction for PDFs: native text layer first, OCR fallback per page.

OCR engine is selectable (config.OCR_ENGINE / OCR_ENGINE env var / set_engine()):
  * "auto"      - Tesseract if the binary is found, else RapidOCR  (default)
  * "tesseract" - force Tesseract (pytesseract); raises if the binary is missing
  * "rapidocr"  - force RapidOCR (pure pip, ONNX; no external install)
Results are cached on disk (ocr_cache/) keyed by file path + size + mtime + engine,
so switching engines does not overwrite the other engine's cached text.
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

from .config import ocr_engine

warnings.filterwarnings("ignore")

CACHE_DIR = Path(__file__).resolve().parent.parent / "ocr_cache"
CACHE_DIR.mkdir(exist_ok=True)

_rapid = None
_tess_cmd = None
_tess_checked = False


def _tesseract_cmd() -> str | None:
    global _tess_cmd, _tess_checked
    if not _tess_checked:
        cmd = os.getenv("TESSERACT_CMD") or shutil.which("tesseract")
        if not cmd:
            for p in (os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
                      r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                      r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"):
                if os.path.exists(p):
                    cmd = p
                    break
        _tess_cmd = cmd if cmd and os.path.exists(cmd) else None
        _tess_checked = True
    return _tess_cmd


def tesseract_available() -> bool:
    return _tesseract_cmd() is not None


def active_engine() -> str:
    """Resolve 'auto' to the engine that will actually run."""
    eng = ocr_engine()
    if eng == "auto":
        return "tesseract" if tesseract_available() else "rapidocr"
    return eng


def _rapid_engine():
    global _rapid
    if _rapid is None:
        from rapidocr_onnxruntime import RapidOCR
        _rapid = RapidOCR()
    return _rapid


def _ocr_tesseract(img: np.ndarray) -> str:
    import pytesseract
    from PIL import Image
    pytesseract.pytesseract.tesseract_cmd = _tesseract_cmd()
    # psm 6 = assume a uniform block of text; good for form/table scans
    return pytesseract.image_to_string(Image.fromarray(img), config="--psm 6")


def _ocr_rapid(img: np.ndarray) -> str:
    res, _ = _rapid_engine()(img)
    rows: dict[int, list] = {}
    for box, txt, _score in (res or []):
        ys = [p[1] for p in box]
        y = int(round(float(np.mean(ys)) / 14.0))
        rows.setdefault(y, []).append((box[0][0], txt))
    return "\n".join("  ".join(t for _, t in sorted(rows[y])) for y in sorted(rows))


def _ocr_image(img: np.ndarray) -> str:
    if active_engine() == "tesseract":
        return _ocr_tesseract(img)
    return _ocr_rapid(img)


def _cache_path(pdf: Path, max_pages: int | None) -> Path:
    st = pdf.stat()
    key = f"{pdf.resolve()}|{st.st_size}|{int(st.st_mtime)}|{max_pages}|{active_engine()}"
    return CACHE_DIR / (hashlib.md5(key.encode()).hexdigest() + ".json")


def extract_pdf(path: str | Path, max_pages: int | None = None, dpi: int = 200) -> dict:
    """Return {'pages': [str,...], 'method': 'text'|'ocr'|'mixed', 'page_count': n, 'engine': ...}."""
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
    out = {"pages": pages, "method": method, "page_count": len(doc), "engine": active_engine()}
    cp.write_text(json.dumps(out), encoding="utf-8")
    return out
