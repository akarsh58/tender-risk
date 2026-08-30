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

