"""Render a TenderRisk analysis as a downloadable PDF report."""

from io import BytesIO

import fitz

from .schemas import TenderAnalysis


def render_analysis_pdf(analysis: TenderAnalysis) -> bytes:
    """Create a simple, readable PDF without requiring a separate report engine."""
    document = fitz.open()
    page = document.new_page()
    cursor_y = 48

    def write(text: str, size: float = 10, bold: bool = False) -> None:
        nonlocal page, cursor_y
        if cursor_y > 740:
            page = document.new_page()
            cursor_y = 48
        font = "hebo" if bold else "helv"
        page.insert_text((48, cursor_y), text[:180], fontsize=size, fontname=font)
        cursor_y += size + 7

    summary = analysis.project_summary
    write("TenderRisk Analysis Report", size=18, bold=True)
    write(f"Project context: {summary.project_context}", size=10)
    write(f"Overall risk: {summary.overall_risk_level.value}", size=11, bold=True)
    write(summary.overall_comment)
    cursor_y += 8

    for category in analysis.per_category_analysis:
        write(
            f"{category.category} - {category.category_risk_level.value}",
            size=13,
            bold=True,
        )
        for finding in category.findings:
            write(f"{finding.clause_id} | {finding.heading} | page {finding.page}", bold=True)
            write(f"Risk: {finding.risk_flag.value} - {finding.summary}")
            write(f"Reason: {finding.risk_reason}")
            write(f"Evidence: {finding.raw_excerpt}")
            for missing_point in finding.missing_points:
                write(f"Missing: {missing_point}")
        cursor_y += 5

    if analysis.key_risks_overall:
        write("Key risks", size=13, bold=True)
        for risk in analysis.key_risks_overall:
            write(f"{risk.category} | {risk.clause_id} | {risk.risk_level.value}", bold=True)
            write(risk.summary)
            write(f"Attention: {risk.suggested_attention}")

    write("Data quality", size=13, bold=True)
    write(analysis.data_quality_notes.notes)

    output = BytesIO()
    document.save(output)
    document.close()
    return output.getvalue()
