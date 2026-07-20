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
    role: Literal["theory_basis", "method_limit", "discriminating_control"] | None = None


class SourceReview(StrictModel):
    """The semantic source-selection record that defines a retrieved packet."""

    provider: str = Field(min_length=1, max_length=120)
    adjudications: list[SourceAdjudication] = Field(min_length=1, max_length=20)
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


class RequiredSignature(StrictModel):
    """A falsifiable condition the mechanism claim must explain."""

    id: str = Field(pattern=r"^signature-[a-zA-Z0-9_-]+$")
    name: str = Field(min_length=1, max_length=80)
    requirement: str = Field(min_length=1, max_length=500)
    expected_observation: str = Field(min_length=1, max_length=500)
    falsifying_outcome: str = Field(min_length=1, max_length=500)
    theory_evidence_ref_ids: list[str] = Field(default_factory=list, max_length=10)


class AlignmentAdjudication(StrictModel):
    """The relationship between one required signature and the measurement."""

    signature_id: str = Field(pattern=r"^signature-[a-zA-Z0-9_-]+$")
    status: Literal["Observed", "Confounded", "Missing", "Contradicted"]
    rationale: str = Field(min_length=1, max_length=1200)
    evidence_ref_ids: list[str] = Field(default_factory=list, max_length=20)
    alternative_explanation: str | None = Field(default=None, max_length=500)
    missing_reason: Literal[
        "not_measured", "not_specified_by_theory", "outside_method_capability", "data_quality_insufficient"
    ] | None = None


class Outcome(StrictModel):
    if_: str = Field(alias="if", min_length=1, max_length=400)
    then: str = Field(min_length=1, max_length=500)
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

class ControlProposal(StrictModel):
    confound: str = Field(min_length=1, max_length=500)
    experiment: str = Field(min_length=1, max_length=1000)
    preconditions: list[str] = Field(min_length=1, max_length=10)
    outcomes: Annotated[list[Outcome], Field(min_length=2, max_length=2)]
    finding_ref_ids: list[str] = Field(default_factory=list, max_length=20)
    signature_ref_ids: list[str] = Field(default_factory=list, max_length=10)
    priority: Literal["high", "medium", "low"]
    feasibility: str = Field(min_length=1, max_length=300)
    closes_signature_ids: list[str] = Field(default_factory=list, max_length=10)
    leaves_open_signature_ids: list[str] = Field(default_factory=list, max_length=10)


class ConvergenceMap(StrictModel):
    """Persisted, reviewable claim-to-measurement alignment artifact."""

    claim: str = Field(min_length=1, max_length=1000)
    measurement_method: str = Field(min_length=1, max_length=20_000)
    signatures: list[RequiredSignature] = Field(min_length=2, max_length=5)
    alignments: list[AlignmentAdjudication] = Field(min_length=2, max_length=5)
    dominant_gap: str = Field(min_length=1, max_length=500)
    control: ControlProposal | None = None
    freeze_status: Literal["DRAFT", "FROZEN"] = "DRAFT"
    recorded_at: str


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
    findings: list[Finding] = Field(default_factory=list)
    control: ControlProposal | None = None
    sources: list[SourceInput]
    source_relevance: list[SourceRelevance] = Field(default_factory=list)
    source_review: SourceReview | None = None
    dataset: DatasetAnalysis
    dataset_provenance: Literal["USER_MEASUREMENT", "LABELLED_DEMO", "FIXTURE_DEMO"] = "USER_MEASUREMENT"
    verdict: MechanismVerdict
    exported_at: str
    convergence: ConvergenceMap | None = None

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
