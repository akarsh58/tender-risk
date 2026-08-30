"""Input and output contracts for the TenderRisk API."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    model_config = ConfigDict(extra="forbid")

    clause_id: str = Field(min_length=1)
    heading: str = ""
    page: str | int
    text: str = Field(min_length=1)


class TenderRequest(BaseModel):
    """Request payload using the field names in the TenderRisk input template."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    project_context: str = Field(alias="PROJECT_CONTEXT")
    question_or_mode: str = Field(alias="QUESTION_OR_MODE", min_length=1)
    risk_categories: list[str] = Field(alias="RISK_CATEGORIES", min_length=1)
    context_clauses: list[Clause] = Field(alias="CONTEXT_CLAUSES")

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


class ProjectSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_context: str
    overall_risk_level: OverallRiskLevel
    overall_comment: str


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clause_id: str
    heading: str
    page: str | int
    raw_excerpt: str
    summary: str
    risk_flag: FindingRiskLevel
    risk_reason: str
    missing_points: list[str]


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
    page: str | int
    risk_level: KeyRiskLevel
    summary: str
    suggested_attention: str


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