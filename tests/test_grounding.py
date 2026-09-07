import json
from types import SimpleNamespace

import pytest

from tenderrisk.grounding import GroundingError, validate_grounding
from tenderrisk.schemas import TenderAnalysis, TenderRequest
from tenderrisk.service import analyze_tender


def request_with_clause() -> TenderRequest:
    return TenderRequest.model_validate(
        {
            "PROJECT_CONTEXT": "Residential build. Perspective: contractor/bidder.",
            "QUESTION_OR_MODE": "FULL_RISK_SCAN",
            "RISK_CATEGORIES": ["Payment"],
            "CONTEXT_CLAUSES": [
                {
                    "clause_id": "C-1",
                    "heading": "Payment",
                    "page": "2",
                    "text": "Payment is due within 21 days after certification.",
                }
            ],
        }
    )


def valid_payload() -> dict:
    return {
        "project_summary": {
            "project_context": "Residential build. Perspective: contractor/bidder.",
            "overall_risk_level": "Medium",
            "overall_comment": "The supplied payment clause sets a certification trigger. It does not state a payment consequence for delay.",
        },
        "per_category_analysis": [
            {
                "category": "Payment",
                "category_risk_level": "Medium",
                "findings": [
                    {
                        "clause_id": "C-1",
                        "heading": "Payment",
                        "page": "2",
                        "raw_excerpt": "Payment is due within 21 days after certification.",
                        "summary": "Payment depends on certification.",
                        "risk_flag": "Medium",
                        "risk_reason": "The clause makes certification the payment trigger.",
                        "missing_points": [
                            "Not found in provided clauses: certification process clarification."
                        ],
                    }
                ],
            }
        ],
        "key_risks_overall": [
            {
                "category": "Payment",
                "clause_id": "C-1",
                "heading": "Payment",
                "page": "2",
                "risk_level": "Medium",
                "summary": "Payment is tied to certification. The supplied clause does not describe the certification process.",
                "suggested_attention": "Clarify the certification process before bid submission.",
            }
        ],
        "data_quality_notes": {
            "missing_categories": [],
            "ambiguous_clauses": [],
            "notes": "Assessment is limited to the supplied clause.",
        },
    }


def test_rejects_non_literal_excerpt() -> None:
    request = request_with_clause()
    payload = valid_payload()
    payload["per_category_analysis"][0]["findings"][0]["raw_excerpt"] = "Invented excerpt"

    with pytest.raises(GroundingError, match="literal excerpt"):
        validate_grounding(TenderAnalysis.model_validate(payload), request)


def test_normalizes_numeric_page_labels() -> None:
    request = request_with_clause()
    payload = valid_payload()
    payload["per_category_analysis"][0]["findings"][0]["page"] = 2
    payload["key_risks_overall"][0]["page"] = 2

    result = validate_grounding(TenderAnalysis.model_validate(payload), request)

    assert result.per_category_analysis[0].findings[0].page == "2"


def test_accepts_case_and_whitespace_variations_in_excerpt() -> None:
    request = request_with_clause()
    payload = valid_payload()
    payload["per_category_analysis"][0]["findings"][0]["raw_excerpt"] = (
        " payment   IS due within 21 DAYS after certification. "
    )

    validate_grounding(TenderAnalysis.model_validate(payload), request)


def test_reports_all_grounding_violations() -> None:
    request = request_with_clause()
    payload = valid_payload()
    finding = payload["per_category_analysis"][0]["findings"][0]
    finding["heading"] = "Wrong heading"
    finding["raw_excerpt"] = "Invented excerpt"
    finding["missing_points"] = ["Missing wording"]
    payload["key_risks_overall"][0]["page"] = 99

    with pytest.raises(GroundingError) as error:
        validate_grounding(TenderAnalysis.model_validate(payload), request)

    message = str(error.value)
    assert "heading does not match clause C-1" in message
    assert "raw_excerpt is not a literal excerpt from clause C-1" in message
    assert "page does not match clause C-1" in message


def test_service_accepts_grounded_structured_response() -> None:
    request = request_with_clause()
    fake_response = SimpleNamespace(output_text=json.dumps(valid_payload()))
    fake_client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **_: fake_response)
    )

    result = analyze_tender(request, client=fake_client)

    assert result.per_category_analysis[0].findings[0].clause_id == "C-1"


def test_service_retries_transient_provider_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    request = request_with_clause()
    fake_response = SimpleNamespace(output_text=json.dumps(valid_payload()))
    calls = 0

    def create(**_: object) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError("temporary provider failure")
        return fake_response

    monkeypatch.setattr("time.sleep", lambda _: None)
    fake_client = SimpleNamespace(responses=SimpleNamespace(create=create))

    result = analyze_tender(request, client=fake_client)

    assert calls == 3
    assert result.project_summary.overall_risk_level == "Medium"
