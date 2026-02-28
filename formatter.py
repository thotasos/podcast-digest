"""Builds the final PDF output file."""

from __future__ import annotations

import os
import textwrap
from datetime import datetime

from fpdf import FPDF

from transcriber import Segment, format_timestamp

# ── Color palette ─────────────────────────────────────────────────────────────
_DARK = (30, 30, 30)
_GRAY = (100, 100, 100)
_LIGHT_GRAY = (180, 180, 180)
_ACCENT = (66, 99, 235)
_BG_LIGHT = (245, 245, 250)


def _sanitize_text(text: str) -> str:
    """Encode text to latin-1 safe characters for PDF core fonts."""
    # Encode to latin-1, replacing anything that can't be represented
    return text.encode("latin-1", errors="replace").decode("latin-1")


class _DigestPDF(FPDF):
    """Custom PDF with header/footer styling."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self._doc_title = title

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*_LIGHT_GRAY)
        self.cell(0, 10, f"podcast-digest  |  page {self.page_no()}/{{nb}}", align="C")


def build_pdf(
    title: str,
    duration_seconds: float,
    whisper_model: str,
    ollama_model: str,
    summary: str,
    chapters: list[str],
    segments: list[Segment],
    output_dir: str,
) -> str:
    """Build and save a PDF digest. Returns the output file path."""
    duration_str = format_timestamp(duration_seconds)
    date_str = datetime.now().strftime("%Y-%m-%d")

    pdf = _DigestPDF(title)
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    pw = pdf.w - pdf.l_margin - pdf.r_margin  # printable width

    # ── Title ─────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(*_DARK)
    pdf.multi_cell(pw, 10, _sanitize_text(title))
    pdf.ln(2)

    # Subtitle / metadata
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*_GRAY)
    meta = (
        f"{duration_str}  |  Whisper ({whisper_model})  |  {ollama_model}  |  {date_str}"
    )
    pdf.cell(pw, 5, meta)
    pdf.ln(8)

    # Divider
    _draw_divider(pdf, pw)

    # ── Summary ───────────────────────────────────────────────────────
    _section_heading(pdf, pw, "Summary")
    if summary:
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(*_DARK)
        pdf.multi_cell(pw, 6, _sanitize_text(summary))
    else:
        pdf.set_font("Helvetica", "I", 11)
        pdf.set_text_color(*_GRAY)
        pdf.cell(pw, 6, "No summary generated.")
    pdf.ln(6)

    _draw_divider(pdf, pw)

    # ── Chapters ──────────────────────────────────────────────────────
    _section_heading(pdf, pw, "Chapters")
    if chapters:
        for ch in chapters:
            ts_part, title_part = _split_chapter(_sanitize_text(ch))
            pdf.set_font("Courier", "B", 10)
            pdf.set_text_color(*_ACCENT)
            ts_w = pdf.get_string_width(ts_part + "  ") + 2
            pdf.cell(ts_w, 6, ts_part)
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(*_DARK)
            pdf.cell(pw - ts_w, 6, title_part)
            pdf.ln(6)
    else:
        pdf.set_font("Helvetica", "I", 11)
        pdf.set_text_color(*_GRAY)
        pdf.cell(pw, 6, "No chapters detected.")
    pdf.ln(6)

    _draw_divider(pdf, pw)

    # ── Full Transcript ───────────────────────────────────────────────
    _section_heading(pdf, pw, "Full Transcript")
    pdf.set_font("Helvetica", "", 8)
    ts_col_w = 22
    text_col_w = pw - ts_col_w

    for seg in segments:
        ts = f"[{format_timestamp(seg.start)}]"
        text = _sanitize_text(seg.text.strip())
        if not text:
            continue

        # Wrap long lines
        wrapped = textwrap.wrap(text, width=100)
        line_h = 4.5
        block_h = len(wrapped) * line_h

        # Page break check
        if pdf.get_y() + block_h > pdf.h - 20:
            pdf.add_page()

        y_start = pdf.get_y()
        pdf.set_font("Courier", "", 7)
        pdf.set_text_color(*_ACCENT)
        pdf.set_xy(pdf.l_margin, y_start)
        pdf.cell(ts_col_w, line_h, ts)

        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(*_DARK)
        for j, wline in enumerate(wrapped):
            pdf.set_xy(pdf.l_margin + ts_col_w, y_start + j * line_h)
            pdf.cell(text_col_w, line_h, wline)

        pdf.set_y(y_start + block_h + 1)

    # ── Save ──────────────────────────────────────────────────────────
    expanded_dir = os.path.expanduser(output_dir)
    os.makedirs(expanded_dir, exist_ok=True)

    safe_title = "".join(c if c.isalnum() or c in "-_ " else "" for c in title)
    safe_title = safe_title.strip().replace(" ", "_")[:80]
    filename = f"{safe_title}_{date_str}.pdf"
    filepath = os.path.join(expanded_dir, filename)

    pdf.output(filepath)
    return filepath


# ── Helpers ───────────────────────────────────────────────────────────────────

def _section_heading(pdf: FPDF, pw: float, text: str) -> None:
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*_ACCENT)
    pdf.cell(pw, 8, text)
    pdf.ln(10)


def _draw_divider(pdf: FPDF, pw: float) -> None:
    y = pdf.get_y()
    pdf.set_draw_color(*_LIGHT_GRAY)
    pdf.line(pdf.l_margin, y, pdf.l_margin + pw, y)
    pdf.ln(6)


def _split_chapter(ch: str) -> tuple[str, str]:
    """Split a chapter string into (timestamp, title)."""
    for sep in ["–", "-"]:
        if sep in ch:
            ts, title = ch.split(sep, 1)
            return ts.strip(), title.strip()
    return "", ch
