"""Builds the final PDF output file."""

from __future__ import annotations

import os
from datetime import datetime

from fpdf import FPDF

from transcriber import format_timestamp

# ── Color palette ─────────────────────────────────────────────────────────────
_DARK = (30, 30, 30)
_GRAY = (100, 100, 100)
_LIGHT_GRAY = (180, 180, 180)
_ACCENT = (66, 99, 235)


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


