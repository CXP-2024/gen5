#!/usr/bin/env python3
"""Generate a polished PDF edition of the Tidal 1R1W report."""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


NAVY = colors.HexColor("#172033")
BLUE = colors.HexColor("#2563EB")
TEAL = colors.HexColor("#079B83")
PURPLE = colors.HexColor("#7C3AED")
MUTED = colors.HexColor("#607087")
SURFACE = colors.HexColor("#F3F6FA")
BORDER = colors.HexColor("#CCD6E3")
WHITE = colors.white


def register_fonts() -> None:
    font_dir = Path("C:/Windows/Fonts")
    faces = {
        "TidalSans": "arial.ttf",
        "TidalSans-Bold": "arialbd.ttf",
        "TidalSans-Italic": "ariali.ttf",
        "TidalMono": "consola.ttf",
    }
    for name, filename in faces.items():
        path = font_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Required font not found: {path}")
        pdfmetrics.registerFont(TTFont(name, str(path)))
    pdfmetrics.registerFontFamily(
        "TidalSans",
        normal="TidalSans",
        bold="TidalSans-Bold",
        italic="TidalSans-Italic",
    )


def inline_markup(text: str) -> str:
    text = text.strip()
    text = text.replace("–", "-").replace("—", "-").replace("‑", "-")
    text = text.replace("\\times", "×").replace("\\in", "∈")
    text = text.replace("\\approx", "≈").replace("\\text", "")
    text = text.replace("\\(", "").replace("\\)", "")
    text = html.escape(text, quote=False)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda match: f'<font color="#2563EB">{match.group(1)}</font>',
        text,
    )
    tick = chr(96)
    text = re.sub(
        tick + "([^" + tick + "]+)" + tick,
        lambda match: (
            '<font name="TidalMono" color="#7C3AED">'
            + match.group(1)
            + "</font>"
        ),
        text,
    )
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", text)
    return text


def make_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName="TidalSans",
            fontSize=9.2,
            leading=13.2,
            textColor=NAVY,
            spaceAfter=5.5,
            allowWidows=0,
            allowOrphans=0,
        ),
        "h2": ParagraphStyle(
            "H2",
            fontName="TidalSans-Bold",
            fontSize=15.5,
            leading=19,
            textColor=BLUE,
            spaceBefore=10,
            spaceAfter=6,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "H3",
            fontName="TidalSans-Bold",
            fontSize=11.5,
            leading=14.5,
            textColor=TEAL,
            spaceBefore=7,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "bullet": ParagraphStyle(
            "Bullet",
            fontName="TidalSans",
            fontSize=8.9,
            leading=12.7,
            textColor=NAVY,
        ),
        "table": ParagraphStyle(
            "Table",
            fontName="TidalSans",
            fontSize=7.7,
            leading=10,
            textColor=NAVY,
        ),
        "table_head": ParagraphStyle(
            "TableHead",
            fontName="TidalSans-Bold",
            fontSize=7.7,
            leading=10,
            textColor=WHITE,
        ),
        "equation": ParagraphStyle(
            "Equation",
            fontName="TidalSans-Italic",
            fontSize=11,
            leading=16,
            alignment=TA_CENTER,
            textColor=PURPLE,
            spaceBefore=5,
            spaceAfter=8,
        ),
        "code": ParagraphStyle(
            "Code",
            fontName="TidalMono",
            fontSize=7.6,
            leading=10,
            textColor=NAVY,
            backColor=SURFACE,
            borderColor=BORDER,
            borderWidth=0.5,
            borderPadding=7,
            spaceBefore=4,
            spaceAfter=8,
        ),
        "cover_kicker": ParagraphStyle(
            "CoverKicker",
            fontName="TidalSans-Bold",
            fontSize=10,
            leading=13,
            textColor=TEAL,
        ),
        "cover_title": ParagraphStyle(
            "CoverTitle",
            fontName="TidalSans-Bold",
            fontSize=30,
            leading=35,
            textColor=NAVY,
            spaceBefore=12,
            spaceAfter=13,
        ),
        "cover_sub": ParagraphStyle(
            "CoverSub",
            fontName="TidalSans",
            fontSize=13,
            leading=18,
            textColor=MUTED,
            spaceAfter=20,
        ),
        "cover_fact": ParagraphStyle(
            "CoverFact",
            fontName="TidalSans-Bold",
            fontSize=11,
            leading=14,
            alignment=TA_CENTER,
            textColor=NAVY,
        ),
        "small": ParagraphStyle(
            "Small",
            fontName="TidalSans",
            fontSize=7.7,
            leading=10,
            textColor=MUTED,
        ),
    }


def make_table(
    rows: list[list[str]], styles: dict[str, ParagraphStyle]
) -> Table:
    columns = max(len(row) for row in rows)
    padded = [row + [""] * (columns - len(row)) for row in rows]
    data = []
    for row_index, row in enumerate(padded):
        style = styles["table_head"] if row_index == 0 else styles["table"]
        data.append([Paragraph(inline_markup(cell), style) for cell in row])
    usable = A4[0] - 36 * mm
    table = Table(
        data,
        colWidths=[usable / columns] * columns,
        repeatRows=1,
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("GRID", (0, 0), (-1, -1), 0.35, BORDER),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SURFACE]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def is_special(line: str) -> bool:
    value = line.strip()
    return (
        not value
        or value.startswith("#")
        or value.startswith("- ")
        or bool(re.match(r"^\d+\.\s", value))
        or value.startswith("|")
        or value.startswith("~~~")
        or value.startswith("\\[")
    )


def parse_markdown(
    source: str, styles: dict[str, ParagraphStyle]
) -> list[object]:
    lines = source.replace(chr(96) * 3, "~~~").splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    story: list[object] = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            index += 1
            continue
        if stripped.startswith("## "):
            heading = stripped[3:]
            if heading.startswith(
                "4. Garnet Implementation"
            ) or heading.startswith("6. Division of Labor"):
                story.append(PageBreak())
            story.append(Paragraph(inline_markup(heading), styles["h2"]))
            index += 1
            continue
        if stripped.startswith("### "):
            story.append(Paragraph(inline_markup(stripped[4:]), styles["h3"]))
            index += 1
            continue
        if stripped.startswith("~~~"):
            index += 1
            code_lines = []
            while index < len(lines) and not lines[index].strip().startswith(
                "~~~"
            ):
                code_lines.append(html.escape(lines[index]))
                index += 1
            index += 1
            story.append(Paragraph("<br/>".join(code_lines), styles["code"]))
            continue
        if stripped.startswith("\\["):
            equation = stripped.removeprefix("\\[").strip()
            index += 1
            while index < len(lines) and not lines[index].strip().endswith(
                "\\]"
            ):
                equation += " " + lines[index].strip()
                index += 1
            if index < len(lines):
                equation += " " + lines[index].strip().removesuffix("\\]")
                index += 1
            equation = equation.replace("\\text{ flits/cycle}", " flits/cycle")
            story.append(
                Paragraph(inline_markup(equation), styles["equation"])
            )
            continue
        if stripped.startswith("|"):
            raw_rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                raw_rows.append(
                    [
                        cell.strip()
                        for cell in lines[index].strip().strip("|").split("|")
                    ]
                )
                index += 1
            rows = [
                row
                for row in raw_rows
                if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in row)
            ]
            story.extend(
                [Spacer(1, 3), make_table(rows, styles), Spacer(1, 7)]
            )
            continue
        unordered = stripped.startswith("- ")
        ordered = bool(re.match(r"^\d+\.\s", stripped))
        if unordered or ordered:
            items = []
            while index < len(lines):
                current = lines[index].strip()
                matches = (
                    bool(re.match(r"^\d+\.\s", current))
                    if ordered
                    else current.startswith("- ")
                )
                if not matches:
                    break
                item = re.sub(r"^(?:- |\d+\.\s+)", "", current)
                index += 1
                while (
                    index < len(lines)
                    and lines[index].strip()
                    and not is_special(lines[index])
                ):
                    item += " " + lines[index].strip()
                    index += 1
                items.append(
                    ListItem(
                        Paragraph(inline_markup(item), styles["bullet"]),
                        leftIndent=11,
                    )
                )
            list_options = {
                "bulletType": "1" if ordered else "bullet",
                "leftIndent": 17,
                "bulletFontName": "TidalSans-Bold",
                "bulletFontSize": 7.5,
                "bulletColor": TEAL,
                "spaceBefore": 2,
                "spaceAfter": 6,
            }
            if ordered:
                list_options["start"] = "1"
            story.append(ListFlowable(items, **list_options))
            continue
        paragraph = stripped
        index += 1
        while index < len(lines) and not is_special(lines[index]):
            paragraph += " " + lines[index].strip()
            index += 1
        story.append(Paragraph(inline_markup(paragraph), styles["body"]))
    return story


class TidalReport(BaseDocTemplate):
    def __init__(self, output: Path):
        super().__init__(
            str(output),
            pagesize=A4,
            rightMargin=18 * mm,
            leftMargin=18 * mm,
            topMargin=20 * mm,
            bottomMargin=18 * mm,
            title="Tidal: Direction-Paired Buffer Pooling with a 1R1W Shared Pool",
            author="Wang Liming and CXP-2024",
            subject="Architecture, implementation, evaluation, and teamwork",
        )
        frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id="body",
        )
        self.addPageTemplates(
            [
                PageTemplate(
                    id="all",
                    frames=frame,
                    onPage=self.draw_page,
                )
            ]
        )

    def draw_page(self, canvas, doc) -> None:
        if doc.page == 1:
            self.cover_page(canvas, doc)
        else:
            self.body_page(canvas, doc)

    def cover_page(self, canvas, doc) -> None:
        canvas.saveState()
        canvas.setFillColor(BLUE)
        canvas.rect(0, A4[1] - 12 * mm, A4[0], 12 * mm, fill=1, stroke=0)
        canvas.setFillColor(TEAL)
        canvas.rect(0, 0, A4[0], 6 * mm, fill=1, stroke=0)
        canvas.restoreState()

    def body_page(self, canvas, doc) -> None:
        canvas.saveState()
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(18 * mm, A4[1] - 14 * mm, A4[0] - 18 * mm, A4[1] - 14 * mm)
        canvas.setFont("TidalSans", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(
            18 * mm,
            A4[1] - 11 * mm,
            "TIDAL · 1R1W DIRECTION-PAIRED BUFFER POOLING",
        )
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, str(doc.page))
        canvas.restoreState()


def cover_story(styles: dict[str, ParagraphStyle]) -> list[object]:
    facts = [
        Paragraph(
            "1R1W<br/><font color='#607087'>Pool service</font>",
            styles["cover_fact"],
        ),
        Paragraph(
            "8<br/><font color='#607087'>equal slots / pair</font>",
            styles["cover_fact"],
        ),
        Paragraph(
            "651<br/><font color='#607087'>main runs</font>",
            styles["cover_fact"],
        ),
        Paragraph(
            "50 / 50<br/><font color='#607087'>contribution</font>",
            styles["cover_fact"],
        ),
    ]
    fact_table = Table([facts], colWidths=[41 * mm] * 4, rowHeights=[30 * mm])
    fact_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
                ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return [
        Spacer(1, 28 * mm),
        Paragraph(
            "TECHNICAL REPORT · PRELIMINARY EVALUATION", styles["cover_kicker"]
        ),
        HRFlowable(
            width=50 * mm,
            thickness=2.2,
            color=TEAL,
            spaceBefore=7,
            spaceAfter=13,
        ),
        Paragraph(
            "Tidal: Direction-Paired Buffer Pooling with a 1R1W Shared Pool",
            styles["cover_title"],
        ),
        Paragraph(
            "Architecture, Garnet implementation, Pool-credit policy, "
            "evaluation, limitations, and reproducibility.",
            styles["cover_sub"],
        ),
        Spacer(1, 9 * mm),
        fact_table,
        Spacer(1, 17 * mm),
        KeepTogether(
            [
                Paragraph(
                    "<b>Authors</b><br/>Wang Liming (50%) · CXP-2024 (50%)",
                    ParagraphStyle(
                        "CoverAuthors",
                        parent=styles["body"],
                        fontSize=11,
                        leading=16,
                        textColor=NAVY,
                    ),
                ),
                Spacer(1, 5),
                Paragraph(
                    "Equal-storage comparison · one-flit vnet-0 traffic · "
                    "zero-delay owner-grant caveat retained",
                    styles["small"],
                ),
            ]
        ),
        PageBreak(),
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).with_name("report_1r1w.md"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[3]
        / "output"
        / "pdf"
        / "tidal_1r1w_report.pdf",
    )
    args = parser.parse_args()
    register_fonts()
    source = args.source.resolve()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    styles = make_styles()
    story = cover_story(styles)
    story.extend(parse_markdown(source.read_text(encoding="utf-8"), styles))
    TidalReport(output).build(story)
    print(output)


if __name__ == "__main__":
    main()
