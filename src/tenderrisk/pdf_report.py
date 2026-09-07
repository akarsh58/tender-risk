"""Render a TenderRisk analysis as a readable downloadable PDF report."""

from __future__ import annotations

import re

import fitz

from .schemas import TenderAnalysis


PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN_X = 54
TOP_MARGIN = 54
BOTTOM_MARGIN = 52
CONTENT_WIDTH = PAGE_WIDTH - (MARGIN_X * 2)


def _wrap_text(text: str, font: str, size: float, width: float) -> list[str]:
    words = re.split(r"\s+", str(text).strip())
    lines: list[str] = []
    current = ""
    for word in words:
        if not word:
            continue
        candidate = f"{current} {word}".strip()
        if current and fitz.get_text_length(candidate, fontname=font, fontsize=size) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def render_analysis_pdf(analysis: TenderAnalysis) -> bytes:
    """Create a paginated report with stable margins and wrapped content."""
    document = fitz.open()
    page_number = 0
    page: fitz.Page | None = None
    cursor_y = TOP_MARGIN

    def add_page() -> None:
        nonlocal page, page_number, cursor_y
        page = document.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        page_number += 1
        cursor_y = TOP_MARGIN

    def add_footer() -> None:
        assert page is not None
        footer_y = PAGE_HEIGHT - 27
        page.draw_line(
            (MARGIN_X, footer_y - 9),
            (PAGE_WIDTH - MARGIN_X, footer_y - 9),
            color=(0.78, 0.81, 0.82),
            width=0.6,
        )
        page.insert_text(
            (MARGIN_X, footer_y),
            f"TenderRisk | Contractor-side tender review | Page {page_number}",
            fontsize=8,
            fontname="helv",
            color=(0.36, 0.40, 0.41),
        )

    def ensure_space(height: float) -> None:
        nonlocal page
        if page is None:
            add_page()
        if cursor_y + height > PAGE_HEIGHT - BOTTOM_MARGIN:
            add_footer()
            add_page()

    def write(
        text: str,
        *,
        size: float = 10,
        bold: bool = False,
        color: tuple[float, float, float] = (0.14, 0.18, 0.19),
        gap_after: float = 5,
    ) -> None:
        nonlocal cursor_y
        font = "hebo" if bold else "helv"
        line_height = size * 1.35
        for line in _wrap_text(text, font, size, CONTENT_WIDTH):
            ensure_space(line_height)
            assert page is not None
            page.insert_text(
                (MARGIN_X, cursor_y),
                line,
                fontsize=size,
                fontname=font,
                color=color,
            )
            cursor_y += line_height
        cursor_y += gap_after

    def rule() -> None:
        nonlocal cursor_y
        ensure_space(12)
        assert page is not None
        page.draw_line(
            (MARGIN_X, cursor_y),
            (PAGE_WIDTH - MARGIN_X, cursor_y),
            color=(0.78, 0.81, 0.82),
            width=0.7,
        )
        cursor_y += 12

    add_page()
    write("TenderRisk Analysis Report", size=20, bold=True, color=(0.07, 0.20, 0.24), gap_after=10)
    write(
        f"Project context: {analysis.project_summary.project_context}",
        size=10,
        color=(0.36, 0.40, 0.41),
        gap_after=10,
    )
    write(
        f"Overall risk: {analysis.project_summary.overall_risk_level.value}",
        size=13,
        bold=True,
        color=(0.07, 0.20, 0.24),
        gap_after=5,
    )
    write(analysis.project_summary.overall_comment, gap_after=10)
    rule()

    for category in analysis.per_category_analysis:
        write(
            f"{category.category}  |  {category.category_risk_level.value}",
            size=14,
            bold=True,
            color=(0.07, 0.20, 0.24),
            gap_after=7,
        )
        if not category.findings:
            write("No grounded findings were returned for this category.", color=(0.36, 0.40, 0.41))
        for finding in category.findings:
            write(
                f"{finding.clause_id}  |  {finding.heading}  |  Page {finding.page}",
                size=10,
                bold=True,
                color=(0.10, 0.25, 0.28),
                gap_after=3,
            )
            write(f"Risk: {finding.risk_flag.value} - {finding.summary}", gap_after=3)
            write(f"Reason: {finding.risk_reason}", gap_after=3)
            write(f"Evidence: {finding.raw_excerpt}", color=(0.28, 0.32, 0.33), gap_after=3)
            for missing_point in finding.missing_points:
                write(f"Missing: {missing_point}", color=(0.36, 0.40, 0.41), gap_after=3)
            cursor_y += 5
        rule()

    if analysis.key_risks_overall:
        write("Key risks", size=14, bold=True, color=(0.07, 0.20, 0.24), gap_after=7)
        for risk in analysis.key_risks_overall:
            write(
                f"{risk.category}  |  {risk.clause_id}  |  {risk.risk_level.value}",
                size=10,
                bold=True,
                color=(0.10, 0.25, 0.28),
                gap_after=3,
            )
            write(risk.summary, gap_after=3)
            write(f"Attention: {risk.suggested_attention}", color=(0.36, 0.40, 0.41), gap_after=5)

    write("Data quality", size=14, bold=True, color=(0.07, 0.20, 0.24), gap_after=7)
    write(analysis.data_quality_notes.notes)
    if analysis.data_quality_notes.missing_categories:
        write(
            "Missing categories: " + ", ".join(analysis.data_quality_notes.missing_categories),
            color=(0.36, 0.40, 0.41),
        )

    if page is not None:
        add_footer()
    output = document.tobytes(garbage=4, deflate=True)
    document.close()
    return output
