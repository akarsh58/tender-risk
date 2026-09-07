"""OpenRouter integration for TenderRisk (OpenAI SDK, compatible endpoint)."""

import json
import os
from importlib.resources import files
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import ValidationError

from .grounding import GroundingError, empty_context_analysis, validate_grounding
from .output_schema import tender_analysis_schema
from .schemas import TenderAnalysis, TenderRequest

load_dotenv()


class AnalysisServiceError(RuntimeError):
    """A safe-to-display failure while generating a tender analysis."""


def system_prompt() -> str:
    return (
        files("tenderrisk")
        .joinpath("prompts", "system.md")
        .read_text(encoding="utf-8")
    )


def _build_client(client: Any | None = None) -> Any:
    if client is not None:
        return client

    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if not (openrouter_key or openai_key):
        raise AnalysisServiceError("OPENROUTER_API_KEY or OPENAI_API_KEY is not set.")

    # Prefer OpenRouter if explicitly configured; otherwise use the OpenAI key
    if openrouter_key:
        return OpenAI(api_key=openrouter_key, base_url="https://openrouter.ai/api/v1")

    # If only OPENAI_API_KEY is set, rely on the OpenAI SDK defaults (do not override base_url)
    return OpenAI(api_key=openai_key)


def _parse_response_content(response: Any) -> dict:
    content: str | list | None = getattr(response, "output_text", None)

    if content is None:
        output = getattr(response, "output", None)
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                for part in item.get("content", []):
                    if isinstance(part, dict) and part.get("type") == "output_text":
                        content = part.get("text")
                        break
                if content is not None:
                    break

    if content is None:
        choices = getattr(response, "choices", None)
        if not choices:
            raise AnalysisServiceError("The provider returned no choices.")

        choice = choices[0]
        message = getattr(choice, "message", None)
        if message is None:
            raise AnalysisServiceError("The provider returned no message object.")

        choice_error = getattr(choice, "error", None)
        if choice_error:
            raise AnalysisServiceError(f"Provider choice error: {choice_error}")

        content = getattr(message, "content", None)
        if not content:
            refusal = getattr(message, "refusal", None)
            tool_calls = getattr(message, "tool_calls", None)
            finish_reason = getattr(choice, "finish_reason", None)
            raise AnalysisServiceError(
                "The provider returned no text content. "
                f"finish_reason={finish_reason}, refusal={refusal}, tool_calls={tool_calls}"
            )

    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
            elif hasattr(part, "type") and getattr(part, "type", None) == "text":
                text_parts.append(getattr(part, "text", ""))
        content = "".join(text_parts).strip()

    if not isinstance(content, str) or not content.strip():
        raise AnalysisServiceError("The provider returned empty text content.")

    if content.startswith("```"):
        content = content.strip("`").strip()
        if content.lower().startswith("json"):
            content = content[4:].strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise AnalysisServiceError(f"The provider returned invalid JSON: {exc}") from exc


def _normalize_project_summary(project_summary: Any, request: TenderRequest) -> dict:
    if not isinstance(project_summary, dict):
        project_summary = {}

    return {
        "project_context": request.project_context,
        "overall_risk_level": (
            project_summary.get("overall_risk_level")
            or project_summary.get("risk_level")
            or "Not_assessed"
        ),
        "overall_comment": (
            project_summary.get("overall_comment")
            or project_summary.get("overall_assessment")
            or project_summary.get("summary")
            or "Not found in provided clauses"
        ),
    }


def _normalize_missing_points(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    prefix = "Not found in provided clauses:"
    normalized: list[str] = []

    for item in value:
        if not isinstance(item, str):
            continue

        text = item.strip()
        if not text:
            continue

        if text.startswith(prefix):
            remainder = text[len(prefix):].strip()
            normalized.append(f"{prefix} {remainder}" if remainder else f"{prefix} unspecified protection")
        else:
            normalized.append(f"{prefix} {text}")

    return normalized


def _normalize_ambiguous_clauses(
    ambiguous_clauses: Any,
    clause_lookup: dict[str, Any],
) -> list[dict]:
    if not isinstance(ambiguous_clauses, list):
        return []

    normalized = []

    for item in ambiguous_clauses:
        if isinstance(item, dict):
            clause_id = str(item.get("clause_id", "")).strip()
            clause = clause_lookup.get(clause_id)
            if not clause_id or clause is None:
                continue
            normalized.append(
                {
                    "clause_id": clause_id,
                    "heading": clause.heading,
                    "reason": str(item.get("reason", "")).strip(),
                }
            )
        elif isinstance(item, str):
            text = item.strip()
            if not text:
                continue
            possible_id = text.split(":", 1)[0].strip()
            clause = clause_lookup.get(possible_id)
            if clause is None:
                continue
            reason = text.split(":", 1)[1].strip() if ":" in text else text
            normalized.append(
                {
                    "clause_id": possible_id,
                    "heading": clause.heading,
                    "reason": reason,
                }
            )

    return normalized


def _normalize_key_risks(key_risks_overall: Any, clause_lookup: dict[str, Any]) -> list[dict]:
    if not isinstance(key_risks_overall, list):
        return []

    normalized = []

    for item in key_risks_overall:
        if not isinstance(item, dict):
            continue

        clause_id = str(item.get("clause_id", "")).strip()
        clause = clause_lookup.get(clause_id)
        if clause is None:
            continue

        normalized.append(
            {
                "category": str(item.get("category", "")).strip(),
                "clause_id": clause_id,
                "heading": clause.heading,
                "page": clause.page,
                "risk_level": item.get("risk_level", "Medium"),
                "summary": str(item.get("summary", "")).strip(),
                "suggested_attention": str(
                    item.get("suggested_attention")
                    or item.get("recommendation")
                    or item.get("suggested_action")
                    or ""
                ).strip(),
            }
        )

    return normalized


def _pick_literal_excerpt(source_text: str, candidate: str) -> str:
    candidate = (candidate or "").strip()
    if candidate and candidate in source_text and len(candidate.split()) <= 60:
        return candidate

    words = source_text.split()
    excerpt = " ".join(words[:60]).strip()
    return excerpt


def _normalize_findings(
    findings_in: Any,
    category_item: dict,
    clause_lookup: dict[str, Any],
) -> list[dict]:
    if isinstance(findings_in, list):
        raw_findings = findings_in
    elif isinstance(category_item, dict) and category_item.get("clause_id"):
        raw_findings = [category_item]
    else:
        raw_findings = []

    normalized = []

    for item in raw_findings:
        if not isinstance(item, dict):
            continue

        evidence = item.get("evidence", {})
        if not isinstance(evidence, dict):
            evidence = {}

        clause_id = str(
            item.get("clause_id")
            or evidence.get("clause_id")
            or category_item.get("clause_id")
            or ""
        ).strip()
        clause = clause_lookup.get(clause_id)
        if clause is None:
            continue

        raw_excerpt = (
            item.get("raw_excerpt")
            or evidence.get("raw_excerpt")
            or evidence.get("excerpt")
            or item.get("text")
            or ""
        )
        raw_excerpt = _pick_literal_excerpt(clause.text, str(raw_excerpt))

        summary = str(
            item.get("summary")
            or item.get("observation")
            or item.get("title")
            or category_item.get("summary")
            or raw_excerpt
        ).strip()

        risk_flag = (
            item.get("risk_flag")
            or item.get("risk_level")
            or category_item.get("risk_level")
            or category_item.get("category_risk_level")
            or "Medium"
        )

        risk_reason = str(
            item.get("risk_reason")
            or item.get("reason")
            or item.get("rationale")
            or summary
        ).strip()

        missing_points = item.get("missing_points")
        if not isinstance(missing_points, list):
            missing_points = item.get("missing_protections", [])
        missing_points = _normalize_missing_points(missing_points)

        normalized.append(
            {
                "clause_id": clause_id,
                "heading": clause.heading,
                "page": clause.page,
                "raw_excerpt": raw_excerpt,
                "summary": summary,
                "risk_flag": risk_flag,
                "risk_reason": risk_reason,
                "missing_points": missing_points,
            }
        )

    return normalized


def _normalize_category_analysis(
    per_category_analysis: Any,
    clause_lookup: dict[str, Any],
    requested_categories: list[str],
) -> list[dict]:
    if not isinstance(per_category_analysis, list):
        per_category_analysis = []

    by_category: dict[str, dict] = {}
    for item in per_category_analysis:
        if isinstance(item, dict) and item.get("category"):
            by_category[str(item["category"])] = item

    normalized = []
    for category_name in requested_categories:
        item = by_category.get(category_name, {})
        findings = _normalize_findings(item.get("findings"), item, clause_lookup)
        normalized.append(
            {
                "category": category_name,
                "category_risk_level": item.get(
                    "category_risk_level",
                    item.get("risk_level", "Not_assessed"),
                ),
                "findings": findings,
            }
        )

    return normalized


def normalize_payload(payload: dict, request: TenderRequest) -> dict:
    if not isinstance(payload, dict):
        payload = {}

    clause_lookup = {c.clause_id: c for c in request.context_clauses}

    project_summary = _normalize_project_summary(payload.get("project_summary"), request)
    per_category_analysis = _normalize_category_analysis(
        payload.get("per_category_analysis"),
        clause_lookup,
        request.risk_categories,
    )
    key_risks_overall = _normalize_key_risks(
        payload.get("key_risks_overall"),
        clause_lookup,
    )

    dqn = payload.get("data_quality_notes")
    if not isinstance(dqn, dict):
        dqn = {}

    missing_categories = dqn.get("missing_categories", [])
    if not isinstance(missing_categories, list):
        missing_categories = []

    return {
        "project_summary": project_summary,
        "per_category_analysis": per_category_analysis,
        "key_risks_overall": key_risks_overall,
        "data_quality_notes": {
            "missing_categories": [str(x).strip() for x in missing_categories if str(x).strip()],
            "ambiguous_clauses": _normalize_ambiguous_clauses(
                dqn.get("ambiguous_clauses", []),
                clause_lookup,
            ),
            "notes": str(dqn.get("notes", "No additional data quality issues noted.")).strip(),
        },
    }


def analyze_tender(
    request: TenderRequest,
    client: Any | None = None,
) -> TenderAnalysis:
    """Analyze submitted clauses and validate all returned evidence locally."""
    if not request.context_clauses:
        return empty_context_analysis(request)

    api_client = _build_client(client)
    model = os.getenv("OPENROUTER_MODEL", "openrouter/free")

    request_json = json.dumps(
        request.model_dump(mode="json", by_alias=True),
        ensure_ascii=False,
    )

    shape_hint = """
Return only a valid JSON object.

Required top-level keys:
- project_summary
- per_category_analysis
- key_risks_overall
- data_quality_notes

project_summary must contain exactly:
- project_context
- overall_risk_level
- overall_comment

Each per_category_analysis item must contain exactly:
- category
- category_risk_level
- findings

Each finding must contain exactly:
- clause_id
- heading
- page
- raw_excerpt
- summary
- risk_flag
- risk_reason
- missing_points

Each key_risks_overall item must contain exactly:
- category
- clause_id
- heading
- page
- risk_level
- summary
- suggested_attention

Each ambiguous_clauses item must contain exactly:
- clause_id
- heading
- reason

Rules:
- overall_risk_level must be one of: Low, Medium, High, Critical, Not_assessed
- category_risk_level must be one of: Low, Medium, High, Critical, Not_assessed
- risk_flag must be one of: Low, Medium, High
- risk_level must be one of: Low, Medium, High, Critical
- missing_points must be an array of strings
- Every missing_points item must start with: Not found in provided clauses:
- Do not include recommended_action
- Do not include overall_assessment
- Do not include scope_notes
- Do not include finding_id, title, evidence, or missing_protections
- key_risks_overall must be an array of objects, never strings
- ambiguous_clauses must be an array of objects, never strings
- data_quality_notes must always include:
  - missing_categories: array
  - ambiguous_clauses: array
  - notes: string
- Do not include markdown fences
- Do not include explanatory text before or after JSON
"""

    messages = [
        {"role": "system", "content": system_prompt()},
        {"role": "system", "content": shape_hint},
        {"role": "user", "content": request_json},
    ]

    extra_headers = {
        "HTTP-Referer": "https://your-project-url.com",
        "X-OpenRouter-Title": "TenderRisk",
    }

    def _run_once(extra_user_message: str | None = None) -> TenderAnalysis:
        response_client = getattr(api_client, "responses", None)
        if response_client is not None:
            run_input = [
                {"role": "system", "content": system_prompt()},
                {"role": "system", "content": shape_hint},
                {"role": "user", "content": request_json},
            ]
            if extra_user_message:
                run_input.append({"role": "user", "content": extra_user_message})

            response = response_client.create(
                model=model,
                input=run_input,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "tender_risk_analysis",
                        "schema": tender_analysis_schema(),
                        "strict": True,
                    }
                },
                extra_headers=extra_headers,
            )
        else:
            run_messages = list(messages)
            if extra_user_message:
                run_messages.append({"role": "user", "content": extra_user_message})

            response = api_client.chat.completions.create(
                model=model,
                messages=run_messages,
                extra_headers=extra_headers,
            )

        payload = _parse_response_content(response)
        normalized = normalize_payload(payload, request)
        analysis = TenderAnalysis.model_validate(normalized)
        return validate_grounding(analysis, request)

    # Bounded retries with exponential backoff for transient provider failures.
    max_attempts = 3
    base_backoff = 0.8
    last_exc: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return _run_once()
        except (GroundingError, ValidationError):
            # These are deterministic validation errors — do not retry.
            raise
        except AnalysisServiceError as exc:
            last_exc = exc
            if attempt < max_attempts:
                import time, random

                wait = base_backoff * (2 ** (attempt - 1))
                time.sleep(wait + random.random() * 0.3)
                continue
            break
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts:
                import time, random

                wait = base_backoff * (2 ** (attempt - 1))
                time.sleep(wait + random.random() * 0.3)
                continue
            break

    # If all retries exhausted, attempt the stricter guidance fallback once.
    try:
        return _run_once(
            "Return only valid JSON matching the required schema exactly. "
            "Use only the exact field names required by the schema. "
            "Every missing_points item must start with 'Not found in provided clauses:'. "
            "Do not include recommended_action, overall_assessment, scope_notes, "
            "finding_id, title, evidence, or missing_protections. "
            "Use the exact clause heading and exact clause page from the provided context. "
            "raw_excerpt must be a literal substring from the cited clause and no more than 60 words. "
            "Do not include markdown fences or extra text."
        )
    except (json.JSONDecodeError, ValidationError, GroundingError, AnalysisServiceError) as exc:
        raise AnalysisServiceError(
            f"The generated analysis failed validation: {exc}"
        ) from exc
    except Exception as exc:
        if last_exc is not None:
            raise AnalysisServiceError(
                f"Provider failures after retries: {type(last_exc).__name__}: {last_exc}; fallback: {type(exc).__name__}: {exc}"
            ) from exc
        raise AnalysisServiceError(
            f"The analysis provider could not complete the request: {type(exc).__name__}: {exc}"
        ) from exc
