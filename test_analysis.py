from tenderrisk.schemas import TenderRequest
from tenderrisk.service import analyze_tender

request = TenderRequest(
    PROJECT_CONTEXT="Test contractor-side tender review for a construction project.",
    QUESTION_OR_MODE="FULL_RISK_SCAN",
    RISK_CATEGORIES=["Payment"],
    CONTEXT_CLAUSES=[{
        "clause_id": "PAY-001",
        "heading": "Payment Terms",
        "page": 12,
        "text": "The contractor shall submit monthly bills for work executed. Payment shall be released within 60 days from certification of the bill by the Engineer. No interest shall be payable for delayed payments."
    }]
)

result = analyze_tender(request)
print(result.model_dump_json(indent=2))