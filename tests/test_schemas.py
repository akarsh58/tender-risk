import pytest
from pydantic import ValidationError

from tenderrisk.schemas import TenderRequest


def clause(page: object = 12, text: str = "Payment terms are stated here.") -> dict:
    return {
        "clause_id": "C-1",
        "heading": "Payment",
        "page": page,
        "text": text,
    }


def request(clauses: list[dict]) -> dict:
    return {
        "PROJECT_CONTEXT": "Smoke test",
        "QUESTION_OR_MODE": "FULL_RISK_SCAN",
        "RISK_CATEGORIES": ["Payment"],
        "CONTEXT_CLAUSES": clauses,
    }


def test_page_values_are_stored_as_strings() -> None:
    assert TenderRequest.model_validate(request([clause(12)])).context_clauses[0].page == "12"
    assert TenderRequest.model_validate(request([clause(" 12 ")])).context_clauses[0].page == "12"


def test_rejects_oversized_clause_text() -> None:
    with pytest.raises(ValidationError):
        TenderRequest.model_validate(request([clause(text="x" * 10001)]))


def test_rejects_more_than_200_clauses() -> None:
    clauses = [clause(page=index) | {"clause_id": f"C-{index}"} for index in range(201)]

    with pytest.raises(ValidationError):
        TenderRequest.model_validate(request(clauses))
