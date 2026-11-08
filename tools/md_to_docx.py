"""Convert the solution-architecture Markdown into a formatted Word .docx.

Handles: # / ## / ### headings, pipe tables (with header row + --- separator),
fenced code blocks, bullet (-, *) and numbered lists, **bold**, and blockquotes.
Not a general Markdown engine - tuned for this document.

  python tools/md_to_docx.py <input.md> <output.docx>
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor, Inches

BRAND = RGBColor(0x0B, 0x5C, 0xAB)
DARK = RGBColor(0x08, 0x3B, 0x6E)
MUTE = RGBColor(0x55, 0x5555 // 256, 0x6B)  # placeholder, set below
MUTE = RGBColor(0x55, 0x62, 0x7C)


def add_runs_with_bold(p, text):
    """Add text to paragraph, honoring **bold** and `code` spans."""
    for part in re.split(r"(\*\*.+?\*\*|`.+?`)", text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            r = p.add_run(part[2:-2]); r.bold = True
        elif part.startswith("`") and part.endswith("`"):
            r = p.add_run(part[1:-1]); r.font.name = "Consolas"; r.font.size = Pt(9.5)
        else:
            p.add_run(part)


def style_doc(doc: Document):
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = src.read_text(encoding="utf-8").splitlines()

    doc = Document()
    style_doc(doc)

    # ---- title page ----
    logo = Path(__file__).resolve().parent.parent / "CBInsureLogo.png"
    if logo.exists():
        try:
            doc.add_picture(str(logo), width=Inches(2.2))
            doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        except Exception:
            pass
    t = doc.add_paragraph(); t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = t.add_run("CBPInsure Claims Automation"); r.bold = True; r.font.size = Pt(26); r.font.color.rgb = DARK
    s = doc.add_paragraph(); s.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = s.add_run("AWS Solution Architecture, Phased Plan & Cost Model"); r.font.size = Pt(14); r.font.color.rgb = BRAND
    m = doc.add_paragraph(); m.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = m.add_run("Prepared by Trigent  |  AWS Solution Architect + Application Architect view")
    r.font.size = Pt(10); r.font.color.rgb = MUTE
    doc.add_page_break()

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]

        # fenced code block
        if line.strip().startswith("```"):
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i]); i += 1
            i += 1
            p = doc.add_paragraph()
            run = p.add_run("\n".join(buf))
            run.font.name = "Consolas"; run.font.size = Pt(8.5)
            continue

        # table block
        if line.strip().startswith("|") and i + 1 < n and set(lines[i + 1].replace("|", "").strip()) <= set("-: "):
            header = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2
            body = []
            while i < n and lines[i].strip().startswith("|"):
                body.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            tbl = doc.add_table(rows=1, cols=len(header))
            tbl.style = "Light Grid Accent 1"
            tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
            for j, h in enumerate(header):
                cell = tbl.rows[0].cells[j]
                cell.text = ""
                add_runs_with_bold(cell.paragraphs[0], h)
                for rn in cell.paragraphs[0].runs:
                    rn.bold = True; rn.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF); rn.font.size = Pt(9)
            for row in body:
                cells = tbl.add_row().cells
                for j in range(len(header)):
                    txt = row[j] if j < len(row) else ""
                    cells[j].text = ""
                    add_runs_with_bold(cells[j].paragraphs[0], txt)
                    for rn in cells[j].paragraphs[0].runs:
                        rn.font.size = Pt(9)
            doc.add_paragraph()
            continue

        stripped = line.strip()
        if not stripped:
            i += 1
            continue

        # headings
        if stripped.startswith("### "):
            h = doc.add_heading(level=3); r = h.add_run(stripped[4:]); r.font.color.rgb = BRAND
        elif stripped.startswith("## "):
            h = doc.add_heading(level=2); r = h.add_run(stripped[3:]); r.font.color.rgb = DARK
        elif stripped.startswith("# "):
            h = doc.add_heading(level=1); r = h.add_run(stripped[2:]); r.font.color.rgb = DARK
        elif stripped == "---":
            doc.add_paragraph().add_run("").add_break()
        elif stripped.startswith(">"):
            p = doc.add_paragraph(); p.paragraph_format.left_indent = Inches(0.3)
            add_runs_with_bold(p, stripped.lstrip("> ").strip())
            for rn in p.runs:
                rn.italic = True; rn.font.color.rgb = MUTE
        elif re.match(r"^\d+\.\s", stripped):
            p = doc.add_paragraph(style="List Number")
            add_runs_with_bold(p, re.sub(r"^\d+\.\s", "", stripped))
        elif stripped.startswith(("- ", "* ")):
            p = doc.add_paragraph(style="List Bullet")
            add_runs_with_bold(p, stripped[2:])
        else:
            p = doc.add_paragraph()
            add_runs_with_bold(p, stripped)
        i += 1

    doc.save(out)
    print("WROTE", out)


if __name__ == "__main__":
    main()
