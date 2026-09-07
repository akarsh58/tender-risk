from fastapi.testclient import TestClient

from tenderrisk.main import app


def test_health_endpoint() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_empty_context_returns_required_deterministic_assessment() -> None:
    response = TestClient(app).post(
        "/v1/tender-risk/analyze",
        json={
            "PROJECT_CONTEXT": "A contractor-side tender review.",
            "QUESTION_OR_MODE": "FULL_RISK_SCAN",
            "RISK_CATEGORIES": ["Payment", "Termination"],
            "CONTEXT_CLAUSES": [],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["project_summary"]["overall_risk_level"] == "Not_assessed"
    assert [item["category"] for item in body["per_category_analysis"]] == [
        "Payment",
        "Termination",
    ]


def test_document_upload_extracts_json_clauses() -> None:
    response = TestClient(app).post(
        "/v1/tender-risk/extract",
        files={
            "file": (
                "tender.json",
                b'[{"clause_id":"PAY-001","heading":"Payment","page":3,"text":"Payment is due within 30 days."}]',
                "application/json",
            )
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["document_type"] == "JSON"
    assert body["clause_count"] == 1
    assert body["clauses"][0]["clause_id"] == "PAY-001"


def test_document_upload_rejects_malformed_json() -> None:
    response = TestClient(app).post(
        "/v1/tender-risk/extract",
        files={"file": ("broken.json", b'{"not": "a clause array"', "application/json")},
    )

    assert response.status_code == 400
    assert "Could not read valid JSON" in response.json()["detail"]


def test_empty_analysis_can_be_downloaded_as_pdf() -> None:
    response = TestClient(app).post(
        "/v1/tender-risk/report.pdf",
        json={
            "PROJECT_CONTEXT": "A contractor-side tender review.",
            "QUESTION_OR_MODE": "FULL_RISK_SCAN",
            "RISK_CATEGORIES": ["Payment"],
            "CONTEXT_CLAUSES": [],
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")
