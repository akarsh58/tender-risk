"""Minimal offline verification of the empty-context path."""

from tenderrisk.grounding import empty_context_analysis
from tenderrisk.main import app
from tenderrisk.schemas import TenderRequest


request = TenderRequest.model_validate(
    {
        "PROJECT_CONTEXT": "Contractor-side tender review.",
        "QUESTION_OR_MODE": "FULL_RISK_SCAN",
        "RISK_CATEGORIES": ["Payment"],
        "CONTEXT_CLAUSES": [],
    }
)
analysis = empty_context_analysis(request)
assert analysis.project_summary.overall_risk_level == "Not_assessed"
assert analysis.per_category_analysis[0].category == "Payment"
assert app.title == "TenderRisk API"
print("offline smoke test passed")
