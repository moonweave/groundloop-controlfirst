from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class RunState(str, Enum):
    DRAFT = "DRAFT"; PACKET_READY = "PACKET_READY"; SOURCES_INSPECTED = "SOURCES_INSPECTED"
    DATA_ANALYZED = "DATA_ANALYZED"; FINDINGS_VALIDATED = "FINDINGS_VALIDATED"; CONTROL_VALIDATED = "CONTROL_VALIDATED"; EXPORTED = "EXPORTED"

class Locator(StrictModel):
    page: int | None = Field(default=None, ge=1)
    section: str | None = None
    columns: list[str] | None = None
    row_start: int | None = Field(default=None, ge=1)
    row_end: int | None = Field(default=None, ge=1)

class SourceInput(StrictModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    title: str = Field(min_length=1, max_length=300)
    authors: list[str] = Field(min_length=1, max_length=20)
    year: int = Field(ge=1800, le=2100)
    url_or_doi: str = Field(min_length=1, max_length=500)
    locator: Locator
    untrusted_content: str = Field(min_length=1, max_length=4000)
    retrieval_provider: Literal["openalex", "arxiv"] = "openalex"
    publication_status: Literal["indexed_abstract", "preprint"] = "indexed_abstract"


class SourceRelevance(StrictModel):
    """A deterministic lexical screen, never a claim about source quality."""

    source_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    verdict: Literal["direct", "contextual", "limited"]
    matched_terms: list[str] = Field(max_length=12)
    reason: str = Field(min_length=1, max_length=500)


class SourceAdjudication(StrictModel):
    """A Codex review of one retrieved candidate, recorded before freezing."""

    source_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    verdict: Literal["direct", "contextual", "reject"]
    rationale: str = Field(min_length=1, max_length=500)


class SourceReview(StrictModel):
    """The semantic source-selection record that defines a retrieved packet."""

    provider: str = Field(min_length=1, max_length=120)
    adjudications: list[SourceAdjudication] = Field(min_length=1, max_length=3)
    adjudicated_at: str = Field(min_length=1, max_length=80)


class AuditEvent(StrictModel):
    """A local, append-only explanation of a run state change."""

    at: str = Field(min_length=1, max_length=80)
    action: str = Field(pattern=r"^[a-z0-9_]+$")
    state: RunState
    summary: str = Field(min_length=1, max_length=300)

class EvidenceRef(StrictModel):
    id: str = Field(min_length=3, max_length=120)
    kind: Literal["source", "data"]
    artifact_id: str
    locator: Locator
    excerpt: str = Field(min_length=1, max_length=1000)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

class Expectation(StrictModel):
    expected_observation: str = Field(max_length=500)
    condition: str = Field(max_length=500)
    falsifier: str = Field(max_length=500)
    evidence_ref_ids: list[str] = Field(min_length=1)

class Observation(StrictModel):
    statement: str = Field(max_length=500)
    evidence_ref_ids: list[str] = Field(min_length=1)

class Finding(StrictModel):
    id: str = Field(pattern=r"^finding-[a-zA-Z0-9_-]+$")
    statement: str = Field(min_length=1, max_length=500)
    status: Literal["Established", "Observed", "Inferred", "Unresolved"]
    evidence_ref_ids: list[str] = Field(min_length=1)
    reasoning: str = Field(max_length=1500)
    uncertainty: str | None = Field(default=None, max_length=500)
    alternative_explanation: str | None = Field(default=None, max_length=500)

class Outcome(StrictModel):
    if_: str = Field(alias="if", min_length=1, max_length=400)
    then: str = Field(min_length=1, max_length=500)
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

class ControlProposal(StrictModel):
    confound: str = Field(min_length=1, max_length=500)
    experiment: str = Field(min_length=1, max_length=1000)
    preconditions: list[str] = Field(min_length=1, max_length=10)
    outcomes: Annotated[list[Outcome], Field(min_length=2, max_length=2)]
    finding_ref_ids: list[str] = Field(min_length=1)
    priority: Literal["high", "medium", "low"]
    feasibility: str = Field(min_length=1, max_length=300)


class MechanismVerdict(StrictModel):
    label: Literal["MECHANISM_NOT_ESTABLISHED"]
    reason: str = Field(min_length=1, max_length=500)
    blocking_finding_ids: list[str] = Field(min_length=2, max_length=20)

class ClaimInput(StrictModel):
    claim: str = Field(min_length=1, max_length=1000)

class DatasetAnalysis(StrictModel):
    artifact_id: str = "data-001"
    columns: list[str]
    row_count: int
    temperature_range_c: tuple[float, float]
    resistance_min_ohm: float
    resistance_min_row: int
    resistance_max_ohm: float
    resistance_max_row: int
    first_resistance_ohm: float
    last_resistance_ohm: float
    change_ohm: float
    percent_change: float
    monotonicity_segments: list[str]
    cited_row_range: tuple[int, int]
    rows: list[dict[str, float]]


class TransientAnalysis(StrictModel):
    """Deterministic diagnostic for a single SM7120 resistance transient.

    This is deliberately a measurement-format adapter, not a generic claim or
    mechanism analyzer. Its exponent is an OLS diagnostic and must not be
    presented as equivalent to a separately configured robust fit.
    """

    artifact_id: str = "data-001"
    columns: list[str]
    row_count: int
    source_row_range: tuple[int, int]
    time_range_s: tuple[float, float]
    voltage_range_v: tuple[float, float]
    first_current_a: float
    last_current_a: float
    fit_window_s: tuple[float, float]
    fit_point_count: int
    fit_method: Literal["ols_log_log"]
    decay_exponent: float
    log_log_r2: float
    warnings: list[str]

class RunSummary(StrictModel):
    run_id: str
    state: RunState
    fixture: str | None = None
    created_at: str

class Report(StrictModel):
    run_id: str
    claim: str
    state: RunState
    findings: list[Finding]
    control: ControlProposal
    sources: list[SourceInput]
    source_relevance: list[SourceRelevance] = Field(default_factory=list)
    source_review: SourceReview | None = None
    dataset: DatasetAnalysis
    dataset_provenance: Literal["USER_MEASUREMENT", "LABELLED_DEMO", "FIXTURE_DEMO"] = "USER_MEASUREMENT"
    verdict: MechanismVerdict
    exported_at: str

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
