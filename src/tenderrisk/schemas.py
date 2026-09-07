"""Input and output contracts for the TenderRisk API."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _normalize_page_value(value: object) -> str:
    if value is None:
        raise ValueError("page is required")
    return str(value).strip()


class OverallRiskLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"
    NOT_ASSESSED = "Not_assessed"


class FindingRiskLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class KeyRiskLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class Clause(BaseModel):
    """One source clause supplied for evidence-grounded review."""

    model_config = ConfigDict(extra="forbid")

    clause_id: str = Field(
        min_length=1,
        max_length=100,
        description="Your stable identifier for the clause, such as PY-10.3.",
        examples=["PY-10.3"],
    )
    heading: str = Field(
        default="",
        max_length=500,
        description="The clause heading exactly as it appears in the tender.",
        examples=["10.3 Interim Payments"],
    )
    page: str = Field(
        description="Page number or source page label.",
        examples=["10"],
    )
    text: str = Field(
        min_length=1,
        max_length=10000,
        description="The complete source text used to ground findings.",
        examples=["The Employer shall pay the certified amount within 14 days."],
    )

    @field_validator("page", mode="before")
    @classmethod
    def normalize_page(cls, value: object) -> str:
        return _normalize_page_value(value)


class TenderRequest(BaseModel):
    """Input for one contractor-side tender risk review."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "PROJECT_CONTEXT": "Public works contract for a G+5 residential building.",
                "QUESTION_OR_MODE": "FULL_RISK_SCAN",
                "RISK_CATEGORIES": ["Payment Terms", "Delay", "Termination"],
                "CONTEXT_CLAUSES": [
                    {
                        "clause_id": "PY-10.3",
                        "heading": "10.3 Interim Payments",
                        "page": 10,
                        "text": "The Employer shall pay the certified amount within 14 days.",
                    }
                ],
            }
        },
    )

    project_context: str = Field(
        alias="PROJECT_CONTEXT",
        description="Short project and contract context from the contractor's perspective.",
        examples=["Public works contract for a G+5 residential building."],
    )
    question_or_mode: str = Field(
        alias="QUESTION_OR_MODE",
        min_length=1,
        description="Use FULL_RISK_SCAN for a complete review, or describe a focused question.",
        examples=["FULL_RISK_SCAN"],
    )
    risk_categories: list[str] = Field(
        alias="RISK_CATEGORIES",
        min_length=1,
        description="The commercial risk areas to assess. Each category must be unique.",
        examples=[["Payment Terms", "Delay", "Termination"]],
    )
    context_clauses: list[Clause] = Field(
        alias="CONTEXT_CLAUSES",
        max_length=200,
        description="Retrieved tender clauses. Findings can cite only these clauses.",
    )

    @field_validator("risk_categories")
    @classmethod
    def categories_are_unique(cls, categories: list[str]) -> list[str]:
        if any(not category.strip() for category in categories):
            raise ValueError("risk categories cannot be blank")
        if len(set(categories)) != len(categories):
            raise ValueError("risk categories must be unique")
        return categories

    @field_validator("context_clauses")
    @classmethod
    def clause_ids_are_unique(cls, clauses: list[Clause]) -> list[Clause]:
        clause_ids = [clause.clause_id for clause in clauses]
        if len(set(clause_ids)) != len(clause_ids):
            raise ValueError("context clause IDs must be unique")
        return clauses


class DocumentExtraction(BaseModel):
    """Clauses extracted from one uploaded tender document."""

    filename: str = Field(description="Name of the uploaded document.")
    document_type: str = Field(description="Detected file type, such as PDF or DOCX.")
    clause_count: int = Field(description="Number of extracted clause objects.")
    clauses: list[Clause] = Field(
        description="Extracted clauses ready to send to the analysis endpoint."
    )


class ProjectSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_context: str
    overall_risk_level: OverallRiskLevel
    overall_comment: str


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clause_id: str
    heading: str
    page: str
    raw_excerpt: str
    summary: str
    risk_flag: FindingRiskLevel
    risk_reason: str
    missing_points: list[str]

    @field_validator("page", mode="before")
    @classmethod
    def normalize_page(cls, value: object) -> str:
        return _normalize_page_value(value)


class CategoryAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    category_risk_level: OverallRiskLevel
    findings: list[Finding]


class KeyRisk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    clause_id: str
    heading: str
    page: str
    risk_level: KeyRiskLevel
    summary: str
    suggested_attention: str

    @field_validator("page", mode="before")
    @classmethod
    def normalize_page(cls, value: object) -> str:
        return _normalize_page_value(value)


class AmbiguousClause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clause_id: str
    heading: str
    reason: str


class DataQualityNotes(BaseModel):
    model_config = ConfigDict(extra="forbid")

    missing_categories: list[str]
    ambiguous_clauses: list[AmbiguousClause]
    notes: str


class TenderAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_summary: ProjectSummary
    per_category_analysis: list[CategoryAnalysis]
    key_risks_overall: list[KeyRisk]
    data_quality_notes: DataQualityNotes