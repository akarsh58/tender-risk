"""Deterministic safeguards for clause-level grounding."""

from __future__ import annotations

import re

from .schemas import TenderAnalysis, TenderRequest


class GroundingError(ValueError):
    """Raised when a model response cites evidence outside supplied clauses."""


def _normalize_page(page: str | int) -> str:
    """Normalize numeric page labels while preserving non-numeric labels."""
    value = str(page).strip()
    if re.fullmatch(r"\d+", value):
        return str(int(value))
    return value.casefold()


def _normalize_excerpt(text: str) -> str:
    return " ".join(text.split()).casefold()


def empty_context_analysis(request: TenderRequest) -> TenderAnalysis:
    """Produce the required non-model response when no clauses are provided."""
    return TenderAnalysis.model_validate(
        {
            "project_summary": {
                "project_context": request.project_context,
                "overall_risk_level": "Not_assessed",
                "overall_comment": (
                    "No tender clauses were provided. Contractor-side risk analysis "
                    "could not be performed."
                ),
            },
            "per_category_analysis": [
                {
                    "category": category,
                    "category_risk_level": "Not_assessed",
                    "findings": [],
                }
                for category in request.risk_categories
            ],
            "key_risks_overall": [],
            "data_quality_notes": {
                "missing_categories": request.risk_categories,
                "ambiguous_clauses": [],
                "notes": (
                    "No CONTEXT_CLAUSES were supplied; tender risk assessment could "
                    "not be performed."
                ),
            },
        }
    )


def validate_grounding(analysis: TenderAnalysis, request: TenderRequest) -> TenderAnalysis:
    """Reject analyses that do not faithfully reference the supplied clause set."""
    violations: list[str] = []

    if analysis.project_summary.project_context != request.project_context:
        violations.append("project_context does not match the submitted request")

    returned_categories = [item.category for item in analysis.per_category_analysis]
    if len(returned_categories) != len(request.risk_categories):
        violations.append(
            "per_category_analysis must contain exactly one entry per requested category"
        )
    elif returned_categories != request.risk_categories:
        violations.append("per_category_analysis must contain requested categories in order")

    clause_by_id = {clause.clause_id: clause for clause in request.context_clauses}

    def check_reference(clause_id: str, heading: str, page: str | int) -> None:
        clause = clause_by_id.get(clause_id)
        if clause is None:
            violations.append(f"unknown clause ID: {clause_id}")
            return
        if heading != clause.heading:
            violations.append(f"heading does not match clause {clause_id}")
        if _normalize_page(page) != _normalize_page(clause.page):
            violations.append(f"page does not match clause {clause_id}")

    for category in analysis.per_category_analysis:
        for finding in category.findings:
            check_reference(finding.clause_id, finding.heading, finding.page)
            clause = clause_by_id.get(finding.clause_id)
            if clause is None:
                continue
            source_text = clause.text
            if not finding.raw_excerpt or _normalize_excerpt(finding.raw_excerpt) not in _normalize_excerpt(source_text):
                violations.append(
                    f"raw_excerpt is not a literal excerpt from clause {finding.clause_id}"
                )
            if len(finding.raw_excerpt.split()) > 60:
                violations.append(
                    f"raw_excerpt must not exceed 60 words in clause {finding.clause_id}"
                )
    for key_risk in analysis.key_risks_overall:
        check_reference(key_risk.clause_id, key_risk.heading, key_risk.page)

    for ambiguous_clause in analysis.data_quality_notes.ambiguous_clauses:
        clause = clause_by_id.get(ambiguous_clause.clause_id)
        if clause is None or ambiguous_clause.heading != clause.heading:
            violations.append(
                "ambiguous_clauses must cite a supplied clause exactly: "
                f"{ambiguous_clause.clause_id}"
            )

    if violations:
        raise GroundingError("Grounding validation failed:\n- " + "\n- ".join(violations))

    return analysis
