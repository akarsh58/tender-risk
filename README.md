# TenderRisk

TenderRisk is a contractor-side tender risk analysis service. It accepts retrieved tender clauses only and produces a structured, clause-cited risk assessment. It is designed to support bid review, not legal advice.

## What this project does

- Exposes a FastAPI API for tender risk analysis.
- Provides a Swagger upload endpoint for PDF, DOCX, DOC, and JSON documents.
- Accepts a request shaped like `TenderRequest`.
- Validates supplied clauses before running any model call.
- Calls the OpenAI-compatible Responses API with strict JSON schema output.
- Re-checks every resulting citation and excerpt locally against the supplied clauses.
- Returns a deterministic `Not_assessed` response when no clauses are provided.
- Supports a lightweight document loader for local PDFs and JSON clause files.

## High-level flow

1. The caller sends a payload to `POST /v1/tender-risk/analyze`.
2. A document can first be uploaded to `POST /v1/tender-risk/extract`.
3. FastAPI validates the request using Pydantic models in `schemas.py`.
4. `service.py` builds a client and sends a structured prompt to the model.
5. The model is forced to return JSON that matches the schema in `output_schema.py`.
6. `grounding.py` validates that every cited clause, heading, page, and raw excerpt matches the user-provided clauses.
7. A final `TenderAnalysis` object is returned to the caller.

## How the complete workflow works

### 1. Upload and extract

Use `POST /v1/tender-risk/extract` when you want to inspect or edit the extracted clauses.
The API accepts PDF, DOCX, legacy DOC, and JSON files. Uploaded files are limited to 100 MB,
stored temporarily, processed locally, and deleted in a `finally` block.

The document loader uses:

- **PyMuPDF** first for PDF text extraction.
- **pdfplumber** and **PyPDF2** as PDF fallbacks.
- **python-docx** for DOCX files.
- **antiword**, **LibreOffice**, or **pypandoc/Pandoc** for legacy DOC files.
- A lightweight heading and page heuristic to create clause objects.

Scanned or nearly empty documents report an OCR-related extraction error. Extracted clauses
should be reviewed because document splitting is intentionally heuristic.

### 2. Analyze

Use `POST /v1/tender-risk/analyze` when you already have a `TenderRequest`. The synchronous
provider call runs in a worker thread so it does not block FastAPI's event loop.

The service layer:

1. Selects OpenRouter when `OPENROUTER_API_KEY` is configured, otherwise OpenAI when
   `OPENAI_API_KEY` is configured.
2. Loads and caches the system prompt and strict output schema.
3. Requests structured JSON through the OpenAI-compatible Responses API.
4. Retries transient provider failures with bounded exponential backoff.
5. Parses normal JSON, fenced JSON, Responses API output, and Chat Completions output.
6. Normalizes common model field aliases before Pydantic validation.

If no context clauses are supplied, the API returns a deterministic `Not_assessed` response
without calling a provider.

### 3. Download a PDF report

Use `POST /v1/tender-risk/report.pdf` with the same JSON request as `/analyze` to receive a
downloadable `tenderrisk-report.pdf`.

For the complete one-step workflow, use `POST /v1/tender-risk/report-from-document.pdf`.
This multipart endpoint accepts the document plus `project_context`, `question_or_mode`, and
comma-separated `risk_categories`; it extracts clauses, validates the request, analyzes it,
and returns the PDF directly.

The PDF renderer uses PyMuPDF and provides wrapped text, consistent margins, automatic page
breaks, section hierarchy, evidence labels, and page footers.

## Validation and error behavior

- **400**: unsupported file type or document extraction failure.
- **413**: upload exceeds 100 MB.
- **422**: malformed request fields, duplicate categories, too many clauses, or oversized clause text.
- **502**: the configured model provider fails or returns unusable output.

Grounding remains strict: cited clause IDs, headings, and normalized page values must refer to
the submitted clauses. Evidence matching tolerates case and repeated whitespace, but still
requires the excerpt to be present in the original source text.

## Project structure

- `src/tenderrisk/main.py` – FastAPI entrypoints.
- `src/tenderrisk/schemas.py` – request/response models.
- `src/tenderrisk/service.py` – model orchestration, normalization, and result validation.
- `src/tenderrisk/grounding.py` – local grounding checks for citations and excerpts.
- `src/tenderrisk/output_schema.py` – JSON schema used by structured outputs.
- `src/tenderrisk/prompts/system.md` – system prompt used for the model.
- `examples/sample-request.json` – example API request payload.
- `src/tenderrisk/document_loader.py` – document extraction for PDF, DOCX, DOC, and JSON files.
- `analyze_real_documents.py` – example script using real clauses from local files.
- `tests/` – automated tests for API and grounding validation.
- `docs/` – documentation and contract examples.

## Request shape

A request is built from these fields:

```json
{
  "PROJECT_CONTEXT": "Construction of a G+5 residential building under a lump-sum contract.",
  "QUESTION_OR_MODE": "FULL_RISK_SCAN",
  "RISK_CATEGORIES": ["Payment", "Termination", "Defects & Warranty"],
  "CONTEXT_CLAUSES": [
    {
      "clause_id": "C-0012",
      "heading": "Interim Payments",
      "page": 23,
      "text": "The Employer shall certify each valid interim payment application within 21 days of receipt."
    }
  ]
}
```

The request model uses aliases so the API accepts the uppercase names shown above.

## Output shape

The API returns a structured tender analysis object with:

- `project_summary`
- `per_category_analysis`
- `key_risks_overall`
- `data_quality_notes`

Each finding includes:

- `clause_id`
- `heading`
- `page`
- `raw_excerpt`
- `summary`
- `risk_flag`
- `risk_reason`
- `missing_points`

## Grounding rules

This project intentionally validates every result before returning it. The model cannot invent a clause.

Grounding requirements include:

- Only clauses supplied in `CONTEXT_CLAUSES` may be cited.
- `clause_id`, `heading`, and `page` must match the supplied source clause.
- `raw_excerpt` must be an actual literal excerpt from the clause text.
- Missing information must be reported as `Not found in provided clauses` or with a clear suffix.
- If a clause is unclear or incomplete, it is recorded in `ambiguous_clauses`.

This safety check is enforced in `src/tenderrisk/grounding.py`.

## Local document loading

The project includes a simple loader for clause extraction from PDF, DOCX, DOC, and JSON files.

Use files in `pdfs/` with either:

- JSON array of clause objects, or
- PDF files processed via PyMuPDF / pdfplumber / PyPDF2
- DOCX files processed via `python-docx`
- legacy DOC files processed via `antiword`, LibreOffice, or `pypandoc` when available

Example JSON format:

```json
[
  {
    "clause_id": "PAY-001",
    "heading": "Payment Terms",
    "page": 12,
    "text": "Payment shall be released within 60 days from certification of the bill by the Engineer."
  }
]
```

The sample workflow is in `analyze_real_documents.py`.

### Upload through Swagger

Start the API and open `http://127.0.0.1:8000/docs`.

1. Expand `POST /v1/tender-risk/extract`.
2. Click **Try it out**.
3. Choose a `.pdf`, `.docx`, `.doc`, or `.json` file in the `file` field.
4. Click **Execute**.
5. Copy the returned `clauses` array into `POST /v1/tender-risk/analyze`.

The upload endpoint extracts text locally and returns clause IDs, headings, page references,
and source text. It accepts files up to 100 MB. Review extracted clauses before analysis because
scanned PDFs may require OCR and document splitting is intentionally lightweight.

To download a report, send the same request body to `POST /v1/tender-risk/report.pdf`.
The endpoint returns a downloadable PDF containing the grounded analysis.

For the shortest workflow, use `POST /v1/tender-risk/report-from-document.pdf` in Swagger.
Upload the document, enter project context, and the API extracts, analyzes, and downloads the
PDF report automatically.

## Running locally

1. Create a Python 3.11+ virtual environment.
2. Install the project:

   ```bash
   pip install -e .[dev]
   ```

3. Set the required environment variable:

   ```bash
   set OPENROUTER_API_KEY=your_api_key
   ```

   On PowerShell, use:

   ```powershell
   $env:OPENROUTER_API_KEY="your_api_key"
   $env:OPENROUTER_MODEL="openrouter/free"
   ```

4. Start the API:

   ```bash
   uvicorn tenderrisk.main:app --reload
   ```

5. Open the docs at:

   ```text
   http://127.0.0.1:8000/docs
   ```

## Test

```bash
python -m pytest -q
```

The test suite covers API health and upload behavior, malformed JSON, deterministic empty
analysis, PDF responses, automated document-to-PDF workflow, request size limits, page
normalization, grounding tolerance, aggregated grounding errors, extraction heuristics,
transient provider retries, and schema validation.

## Example checks

```bash
python test_analysis.py
python analyze_real_documents.py
```

## Key implementation detail

Structured Outputs are configured through the Responses API with a schema and strict mode. The schema is generated from `TenderAnalysis.model_json_schema()` and exposed through `GET /v1/tender-risk/output-schema`.

This project deliberately does not search the web or upload a full tender. The caller is responsible for collecting the relevant clause text and supplying it in `CONTEXT_CLAUSES`.

## Notes

- A call with no context clauses returns a deterministic `Not_assessed` result without invoking the model.
- This is an analytical aid and not legal advice.
