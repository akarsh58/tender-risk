"""OpenAI Structured Outputs schema used by the analysis call."""

from typing import Any

from .schemas import TenderAnalysis


def tender_analysis_schema() -> dict[str, Any]:
    """Return the JSON Schema passed to the Responses API with strict mode."""
    return TenderAnalysis.model_json_schema()


def response_text_format() -> dict[str, Any]:
    """Return the Responses API text-format configuration."""
    return {
        "format": {
            "type": "json_schema",
            "name": "tender_risk_analysis",
            "description": "Grounded contractor-side tender risk analysis.",
            "strict": True,
            "schema": tender_analysis_schema(),
        }
    }

