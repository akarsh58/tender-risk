# TenderRisk architecture and file map

## Overview

TenderRisk is a contract-risk analysis service for contractor-side tender review. It accepts a set of retrieved clauses, asks an LLM for a structured risk assessment, then validates every citation against the source clauses before returning a result.

## Request lifecycle

1. The caller sends JSON to `POST /v1/tender-risk/analyze`.
2. `main.py` receives the request and validates it via `TenderRequest`.
3. `service.py` checks whether `CONTEXT_CLAUSES` is empty.
4. If it is empty, the service returns a deterministic `Not_assessed` result without calling the model.
5. Otherwise, it builds a structured prompt and sends a request to the model using the OpenAI-compatible Responses API.
6. The response is parsed as raw JSON.
7. `normalize_payload` repairs common structure issues and fills defaults.
8. `TenderAnalysis.model_validate` ensures the result matches the schema.
9. `validate_grounding` checks the clauses, page numbers, headings, and excerpt literals against the original clause set.
10. The final analysis is returned.

## Important files

### `src/tenderrisk/main.py`

FastAPI application. It defines:

- `GET /health`
- `GET /v1/tender-risk/output-schema`
- `POST /v1/tender-risk/analyze`

### `src/tenderrisk/schemas.py`

Contains all Pydantic models:

- `Clause`
- `TenderRequest`
- `ProjectSummary`
- `Finding`
- `CategoryAnalysis`
- `KeyRisk`
- `AmbiguousClause`
- `DataQualityNotes`
- `TenderAnalysis`

These model the strict JSON contract used by the API.

### `src/tenderrisk/service.py`

Contains the business logic that:

- builds the OpenAI client
- reads the system prompt from `prompts/system.md`
- requests a model response
- parses the model output
- normalizes inconsistent data
- validates the final payload

### `src/tenderrisk/grounding.py`

Performs local validation:

- clause ID exists in the request
- heading and page are valid
- raw excerpt is present in the clause text
- ambiguous clauses are tracked

### `src/tenderrisk/output_schema.py`

Generates the strict JSON schema used by the model call. This is the guardrail behind `text.format.type: json_schema`.

### `src/tenderrisk/prompts/system.md`

This is the system prompt given to the model. It defines the contract-risk perspective, grounding requirements, and output rules.

## Data contract

The user supplies text-only clause objects, not a whole tender document.

Example:

```json
{
  "clause_id": "PAY-001",
  "heading": "Payment Terms",
  "page": 12,
  "text": "Payment shall be released within 60 days..."
}
```

The project validates that every model-produced finding maps to one real clause from this set.

## Why grounding matters

The service does not accept a generic AI summary. It requires the model to show evidence from the exact source clause text. This reduces hallucination and preserves traceability.

## Local file workflow

The project supports a light local document pipeline:

- `load_documents.py` reads JSON files and PDF files from the `pdfs/` folder.
- `analyze_real_documents.py` loads all available documents and calls the analysis service.

This is meant for testing and local experimentation, not production document ingestion.

## Testing

The repository includes tests for:

- health endpoint
- empty-context deterministic response
- grounding validation
- service acceptance of grounded response objects

See `tests/test_api.py` and `tests/test_grounding.py`.
