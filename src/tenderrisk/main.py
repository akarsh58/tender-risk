"""HTTP entry point for TenderRisk."""

import asyncio
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .document_loader import (
    DocumentLoadError,
    extract_clauses_from_document,
    load_clauses_from_json,
)
from .output_schema import tender_analysis_schema
from .schemas import DocumentExtraction, TenderAnalysis, TenderRequest
from .service import AnalysisServiceError, analyze_tender

app = FastAPI(
    title="TenderRisk API",
    version="1.0.0",
    summary="Evidence-backed tender risk review for contractors",
    docs_url=None,
    redoc_url=None,
    description="""
## What this API does

TenderRisk reviews tender clauses from a contractor or bidder perspective and returns a
structured risk register covering payment, delay, termination, claims, and other
commercial categories.

This API is designed for external integrators who may not know our domain model.
Use the task-based workflow below rather than learning internal resource names first.

## Quick start

1. Check `GET /health`.
2. Upload a PDF, DOCX, DOC, or JSON file with `POST /v1/tender-risk/extract`.
3. Copy the returned `clauses` into `POST /v1/tender-risk/analyze`.
4. Set project context and risk categories, then click **Execute**.
5. Review cited evidence and data-quality notes in the response.

## Important

- Uploads are extracted locally into clause objects; the analysis endpoint receives only those clauses.
- Every finding is checked against the supplied clause ID, heading, page, and excerpt.
- An empty clause list returns `Not_assessed` instead of inventing an answer.
- This is an analytical aid, not legal advice.

Use `/` for the product overview and this page for interactive API integration.
""",
    contact={
        "name": "TenderRisk API support",
        "url": "http://127.0.0.1:8000/",
        "email": "hello@tenderrisk.com",
    },
    license_info={"name": "Proprietary"},
    openapi_tags=[
        {
            "name": "System",
            "description": "Service availability and status checks.",
        },
        {
            "name": "Tender risk analysis",
            "description": "Submit source clauses and receive a grounded contractor-side risk review.",
        },
        {
            "name": "Document ingestion",
            "description": "Upload a PDF, DOCX, DOC, or JSON file and extract reviewable clauses.",
        },
        {
            "name": "Developer tools",
            "description": "Schema information for integrating the structured response.",
        },
    ],
)


@app.get("/docs", include_in_schema=False)
def swagger_docs() -> HTMLResponse:
    """Serve a task-oriented Swagger UI shell for external integrators."""
    response = get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title="TenderRisk API docs",
        swagger_ui_parameters={
            "deepLinking": True,
            "displayRequestDuration": True,
            "docExpansion": "list",
            "filter": True,
            "persistAuthorization": True,
            "showExtensions": False,
            "showCommonExtensions": False,
            "tryItOutEnabled": True,
            "defaultModelsExpandDepth": -1,
            "syntaxHighlight": {"theme": "arta"},
        },
    )
    html = response.body.decode("utf-8")
    html = html.replace(
        "</head>",
        '<link rel="stylesheet" href="/docs-assets/swagger.css"></head>',
    )
    html = html.replace(
        "</body>",
        '<script src="/docs-assets/swagger.js"></script></body>',
    )
    return HTMLResponse(content=html)


@app.get(
    "/health",
    tags=["System"],
    summary="Check that the API is running",
    description="Returns a simple status response. Use this for a deployment or local-server health check.",
    response_description="The current service status.",
)
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/v1/tender-risk/extract",
    response_model=DocumentExtraction,
    tags=["Document ingestion"],
    summary="Upload a tender document and extract clauses",
    description=(
        "Upload one PDF, DOCX, DOC, or JSON file. The response shows the extracted clauses "
        "and their page references. Review or edit these clauses before sending them to the "
        "analysis endpoint. Maximum upload size is 20 MB."
    ),
    response_description="Extracted clause objects ready for analysis.",
    responses={
        400: {"description": "Unsupported file type or document extraction failed."},
        413: {"description": "The uploaded file is larger than 20 MB."},
        422: {"description": "No file was supplied."},
    },
)
async def extract_document(
    file: UploadFile = File(
        description="Tender document in PDF, DOCX, DOC, or JSON format.",
    ),
) -> DocumentExtraction:
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    allowed_suffixes = {".pdf", ".docx", ".doc", ".json"}
    if not filename or suffix not in allowed_suffixes:
        raise HTTPException(
            status_code=400,
            detail="Supported file types are .pdf, .docx, .doc, and .json.",
        )

    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="The uploaded file must be 20 MB or smaller.")

    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(suffix=suffix, delete=False) as temporary_file:
            temporary_file.write(content)
            temporary_path = Path(temporary_file.name)
        if suffix == ".json":
            clauses = load_clauses_from_json(str(temporary_path))
        else:
            clauses = extract_clauses_from_document(str(temporary_path))
    except (DocumentLoadError, OSError, ValueError, ImportError) as exc:
        raise HTTPException(status_code=400, detail=f"Could not extract clauses: {exc}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return DocumentExtraction(
        filename=filename,
        document_type=suffix.removeprefix(".").upper(),
        clause_count=len(clauses),
        clauses=clauses,
    )


@app.get(
    "/v1/tender-risk/output-schema",
    tags=["Developer tools"],
    summary="Get the strict analysis output schema",
    description="Returns the JSON Schema used to validate the structured tender analysis response.",
    response_description="The JSON Schema for a TenderAnalysis response.",
)
def output_schema() -> dict:
    """Expose the exact strict schema configured for model output."""
    return tender_analysis_schema()


@app.post(
    "/v1/tender-risk/analyze",
    response_model=TenderAnalysis,
    tags=["Tender risk analysis"],
    summary="Analyze supplied tender clauses",
    description=(
        "Reviews the supplied clauses from a contractor-side perspective. "
        "Use the generated example as a starting point, then provide real clause text. "
        "The model cannot cite clauses that are not in your request."
    ),
    response_description="A structured risk register with cited findings and data-quality notes.",
    responses={
        200: {"description": "Analysis completed and passed grounding validation."},
        422: {"description": "The request shape is invalid. Check the `detail` field for the exact field and reason."},
        502: {"description": "The configured model provider could not return a valid analysis."},
    },
)
async def analyze(request: TenderRequest) -> TenderAnalysis:
    try:
        return await asyncio.to_thread(analyze_tender, request)
    except AnalysisServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


website_dir = Path(__file__).resolve().parents[2] / "website"
if website_dir.is_dir():
    app.mount("/", StaticFiles(directory=website_dir, html=True), name="website")
