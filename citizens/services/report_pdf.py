"""PDF rendering of the assembly report (fpdf2, mirrors render_markdown).

DejaVu Sans (fonts-dejavu-core in the image) provides Unicode coverage for
assembly languages and the curly quotes used in evidence excerpts; when the
font is unavailable (bare dev host) the renderer falls back to Helvetica.
"""

from pathlib import Path

from fpdf import FPDF

from citizens.services.report import TYPE_LABELS

_FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")

INK = (34, 34, 34)
MUTED = (107, 107, 107)
ACCENT = (0, 103, 158)  # NC blue
LIGHT = (238, 240, 243)


class _ReportPDF(FPDF):
    def __init__(self) -> None:
        super().__init__(format="A4")
        self.set_margins(18, 16, 18)
        self.set_auto_page_break(auto=True, margin=18)
        self.family = "helvetica"
        regular = _FONT_DIR / "DejaVuSans.ttf"
        bold = _FONT_DIR / "DejaVuSans-Bold.ttf"
        if regular.is_file() and bold.is_file():
            self.add_font("DejaVu", "", str(regular))
            self.add_font("DejaVu", "B", str(bold))
            self.family = "DejaVu"

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font(self.family, "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 6, f"{self.page_no()}", align="C")

    # helpers -----------------------------------------------------------

    def text_block(self, text: str, size: float = 10.5, style: str = "",
                   color: tuple = INK, height: float = 5.2) -> None:
        self.set_font(self.family, style, size)
        self.set_text_color(*color)
        # explicit new position: multi_cell otherwise parks x at the right
        # margin, which zeroes the width of the next block
        self.multi_cell(0, height, text, new_x="LMARGIN", new_y="NEXT")

    def eyebrow(self, text: str) -> None:
        self.set_font(self.family, "B", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 5, text.upper(), new_x="LMARGIN", new_y="NEXT")

    def section(self, title: str) -> None:
        if self.get_y() > self.h - 45:
            self.add_page()
        self.ln(4)
        self.set_fill_color(*LIGHT)
        self.set_font(self.family, "B", 13)
        self.set_text_color(*INK)
        self.cell(0, 9, f"  {title}", fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def subheading(self, title: str) -> None:
        self.ln(2)
        self.set_font(self.family, "B", 11)
        self.set_text_color(*ACCENT)
        self.cell(0, 6, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)


def _finding(pdf: _ReportPDF, finding: dict, cross: bool) -> None:
    label = TYPE_LABELS.get(finding["type"], finding["type"])
    label = label[:-1] if label.endswith("s") else label
    draft = "  (DRAFT — not yet reviewed)" if finding["is_draft"] else ""
    pdf.ln(1)
    pdf.text_block(f"{label}: {finding['title']}{draft}", size=10.5, style="B")
    if cross and finding["mentioned_table_count"]:
        pdf.text_block(
            f"Mentioned at {finding['mentioned_table_count']} table(s).",
            size=9, color=MUTED, height=4.6,
        )
    pdf.text_block(finding["summary"], height=5)
    for evidence in finding["evidence"][:5]:
        speaker = evidence["speaker"] or "Speaker"
        pdf.set_x(pdf.l_margin + 6)
        pdf.text_block(
            f"[{evidence['timestamp']}] {speaker}: “{evidence['text']}”",
            size=9, color=MUTED, height=4.6,
        )
    pdf.ln(1.5)


def render_pdf(report: dict, logo_path: Path | None = None) -> bytes:
    pdf = _ReportPDF()
    pdf.add_page()
    assembly = report["assembly"]

    if logo_path is not None and logo_path.is_file():
        # top-right, 16 mm tall, width scaled automatically
        pdf.image(str(logo_path), x=pdf.w - pdf.r_margin - 34, y=12, h=16, w=34, keep_aspect_ratio=True)

    pdf.set_font(pdf.family, "B", 19)
    pdf.set_text_color(*INK)
    pdf.multi_cell(
        pdf.w - pdf.l_margin - pdf.r_margin - 40, 8.5, f"{assembly['name']}",
        new_x="LMARGIN", new_y="NEXT",
    )
    pdf.set_font(pdf.family, "B", 12)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 8, "Assembly Report", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    pdf.text_block(
        f"{assembly['participants']} participants (expected "
        f"{assembly['expected_participants']}) · {assembly['tables']} tables · "
        f"{assembly['language'].upper()}",
        size=9.5, color=MUTED,
    )
    pdf.ln(2)
    if assembly["description"]:
        pdf.text_block(assembly["description"])
        pdf.ln(2)
    pdf.eyebrow("Method")
    pdf.text_block(report["method"], size=9.5, color=MUTED, height=4.8)

    for round_ in report["rounds"]:
        pdf.section(f"Round {round_['position']} — {round_['title'] or 'Untitled'}")
        if round_["question"]:
            pdf.text_block(f"“{round_['question']}”", size=11, style="B", color=ACCENT)
            pdf.ln(1.5)
        if round_["summary"]:
            pdf.eyebrow("AI summary")
            pdf.text_block(round_["summary"], height=5)
            pdf.ln(1)
        if round_["cross_table"]:
            pdf.subheading("Across all tables")
            for finding in round_["cross_table"]:
                _finding(pdf, finding, cross=True)
        for table in round_["tables"]:
            if not table["findings"] and not table["summary"]:
                continue
            pdf.subheading(f"Table {table['table_number']}")
            if table["summary"]:
                pdf.eyebrow("AI summary")
                pdf.text_block(table["summary"], height=5)
                pdf.ln(1)
            for finding in table["findings"]:
                _finding(pdf, finding, cross=False)
        if (
            not round_["summary"]
            and not round_["cross_table"]
            and not any(t["findings"] or t["summary"] for t in round_["tables"])
        ):
            pdf.text_block("No findings for this round yet.", color=MUTED)

    pdf.ln(5)
    pdf.set_draw_color(*MUTED)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)
    pdf.text_block(report["methodology_note"], size=8.5, color=MUTED, height=4.4)

    return bytes(pdf.output())
