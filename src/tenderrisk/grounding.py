"""Grounding validation for TenderRisk analyses."""

from .schemas import TenderAnalysis, TenderRequest, OverallRiskLevel, ProjectSummary, DataQualityNotes


class GroundingError(Exception):
    """Raised when analysis grounding validation fails."""


def empty_context_analysis(request: TenderRequest) -> TenderAnalysis:
    """Return a deterministic analysis when no clauses are provided."""
    return TenderAnalysis(
        project_summary=ProjectSummary(
            project_context=request.project_context,
            overall_risk_level=OverallRiskLevel.NOT_ASSESSED,
            overall_comment="Not assessed - no clauses provided for analysis.",
        ),
        per_category_analysis=[
            {
                "category": category,
                "category_risk_level": OverallRiskLevel.NOT_ASSESSED,
                "findings": [],
            }
            for category in request.risk_categories
        ],
        key_risks_overall=[],
        data_quality_notes=DataQualityNotes(
            missing_categories=request.risk_categories,
            ambiguous_clauses=[],
            notes="Analysis not performed due to missing context clauses.",
        ),
    )


def validate_grounding(analysis: TenderAnalysis, request: TenderRequest) -> TenderAnalysis:
    """Validate that all cited clauses in the analysis exist in the request."""
    clause_lookup = {c.clause_id: c for c in request.context_clauses}

    for category in analysis.per_category_analysis:
        for finding in category.findings:
            if finding.clause_id not in clause_lookup:
                raise GroundingError(
                    f"Finding cites clause '{finding.clause_id}' which was not provided."
                )

            clause = clause_lookup[finding.clause_id]
            if finding.raw_excerpt and finding.raw_excerpt not in clause.text:
                raise GroundingError(
                    "The literal excerpt for clause "
                    f"'{finding.clause_id}' does not appear in the provided clause text."
                )

    for key_risk in analysis.key_risks_overall:
        if key_risk.clause_id not in clause_lookup:
            raise GroundingError(
                f"Key risk cites clause '{key_risk.clause_id}' which was not provided."
            )

    for ambiguous in analysis.data_quality_notes.ambiguous_clauses:
        if ambiguous.clause_id not in clause_lookup:
            raise GroundingError(
                f"Ambiguous clause reference '{ambiguous.clause_id}' was not provided."
            )

    return analysis
