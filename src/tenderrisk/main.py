"""HTTP entry point for TenderRisk."""

from fastapi import FastAPI, HTTPException

from .output_schema import tender_analysis_schema
from .schemas import TenderAnalysis, TenderRequest
from .service import AnalysisServiceError, analyze_tender

app = FastAPI(
    title="TenderRisk API",
    version="1.0.0",
    description="Grounded contractor-side tender risk analysis. Not legal advice.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/tender-risk/output-schema")
def output_schema() -> dict:
    """Expose the exact strict schema configured for model output."""
    return tender_analysis_schema()


@app.post("/v1/tender-risk/analyze", response_model=TenderAnalysis)
def analyze(request: TenderRequest) -> TenderAnalysis:
    try:
        return analyze_tender(request)
    except AnalysisServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

