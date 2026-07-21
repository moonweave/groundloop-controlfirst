from __future__ import annotations

import hashlib
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
    retrieval_provider: str = Field(default="openalex", min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    publication_status: Literal["peer_reviewed", "preprint", "indexed_abstract", "unknown"] = "indexed_abstract"
    retrieved_at: str | None = Field(default=None, max_length=80)
    search_query: str | None = Field(default=None, max_length=500)
    discovery_rationale: str | None = Field(default=None, max_length=500)
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$", validate_default=True)

    @field_validator("content_sha256", mode="before")
    @classmethod
    def derive_content_hash(cls, value: str | None, info: Any) -> str | None:
        if value:
            return value
        excerpt = info.data.get("untrusted_content")
        return hashlib.sha256(excerpt.encode("utf-8")).hexdigest() if excerpt else value

    @model_validator(mode="after")
    def validate_content_hash(self) -> "SourceInput":
        expected = hashlib.sha256(self.untrusted_content.encode("utf-8")).hexdigest()
        if self.content_sha256 != expected:
            raise ValueError("content_sha256 must match the bounded source excerpt")
        return self


class LiteratureCandidate(StrictModel):
    """Codex-imported, bounded literature candidate before semantic review."""

    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    title: str = Field(min_length=1, max_length=300)
    authors: list[str] = Field(min_length=1, max_length=20)
    year: int = Field(ge=1800, le=2100)
    url_or_doi: str = Field(min_length=1, max_length=500)
    retrieval_provider: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    publication_status: Literal["peer_reviewed", "preprint", "indexed_abstract", "unknown"]
    excerpt: str = Field(min_length=1, max_length=4000)
    locator: Locator
    retrieved_at: str = Field(min_length=1, max_length=80)
    search_query: str = Field(min_length=1, max_length=500)
    discovery_rationale: str = Field(min_length=1, max_length=500)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_excerpt_hash(self) -> "LiteratureCandidate":
        expected = hashlib.sha256(self.excerpt.encode("utf-8")).hexdigest()
        if self.content_sha256 != expected:
            raise ValueError("content_sha256 must match the bounded literature excerpt")
        return self


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
    kind: Literal["source", "method", "data"]
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
    artifact_relation_rationale: str | None = Field(default=None, max_length=500)
    alternative_explanation: str | None = Field(default=None, max_length=500)
    missing_reason: Literal[
        "not_measured", "not_specified_by_theory", "theory_prediction_unspecified", "outside_method_capability", "data_quality_insufficient", "required_condition_not_recorded"
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
    required_artifact_labels: list[str] = Field(default_factory=list, max_length=10)


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
    schema_version: int = Field(default=1, ge=1, le=2)
    workflow: Literal["transport_v1", "generic_v2"] = "transport_v1"


class UnitDescriptor(StrictModel):
    """A unit inferred from a header is only a candidate until a researcher confirms it."""

    value: str | None = Field(default=None, max_length=32)
    source: Literal["header", "user", "none"] = "none"
    status: Literal["unknown", "candidate", "confirmed"] = "unknown"


class NumericSummary(StrictModel):
    min: float
    max: float
    mean: float
    median: float
    std: float


class ColumnProfile(StrictModel):
    column_id: str = Field(pattern=r"^col-[0-9]{3}$")
    name: str = Field(min_length=1, max_length=200)
    index: int = Field(ge=0)
    inferred_type: Literal["integer", "numeric", "datetime", "boolean", "categorical", "text", "empty"]
    unit: UnitDescriptor
    missing_count: int = Field(ge=0)
    missing_fraction: float = Field(ge=0, le=1)
    unique_count: int = Field(ge=0)
    numeric_summary: NumericSummary | None = None


class DatasetArtifact(StrictModel):
    artifact_id: str = Field(pattern=r"^artifact-[a-zA-Z0-9_-]+$")
    filename: str = Field(min_length=1, max_length=255)
    label: str | None = Field(default=None, min_length=1, max_length=80)
    media_type: Literal["text/csv"] = "text/csv"
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_count: int = Field(ge=1, le=5 * 1024 * 1024)
    provenance: Literal["USER_MEASUREMENT", "LABELLED_DEMO", "FIXTURE_DEMO"] = "USER_MEASUREMENT"
    imported_at: str
    schema_version: Literal[2] = 2


class DatasetProfile(StrictModel):
    artifact_id: str
    row_count: int = Field(ge=1, le=10_000)
    column_count: int = Field(ge=1, le=128)
    row_order_preserved: Literal[True] = True
    columns: list[ColumnProfile] = Field(min_length=1, max_length=128)
    sample_rows: list[dict[str, str | None]] = Field(max_length=12)
    warnings: list[str] = Field(default_factory=list, max_length=40)
    profile_version: Literal["generic-tabular-1"] = "generic-tabular-1"


class DatasetBinding(StrictModel):
    artifact_id: str
    x_column_id: str | None = None
    y_column_ids: list[str] = Field(default_factory=list, max_length=3)
    group_column_id: str | None = None
    acquisition_order_column_id: str | None = None
    confirmed_units: dict[str, str] = Field(default_factory=dict)
    confirmation_authority: Literal["researcher"] = "researcher"
    confirmed_at: str

    @model_validator(mode="after")
    def validate_roles(self) -> "DatasetBinding":
        if not self.x_column_id or not self.y_column_ids:
            raise ValueError("binding requires one X column and at least one Y column")
        assigned = [self.x_column_id, *self.y_column_ids]
        if self.group_column_id:
            assigned.append(self.group_column_id)
        if self.acquisition_order_column_id:
            assigned.append(self.acquisition_order_column_id)
        if len(assigned) != len(set(assigned)):
            raise ValueError("binding roles cannot reuse a column")
        return self


class MeasurementModalityProposal(StrictModel):
    candidate: Literal[
        "electrical_transport_rt", "generic_spectrum", "generic_sweep", "generic_time_series",
        "generic_cyclic_trace", "grouped_comparison", "actuator_dynamics", "unknown",
    ]
    confidence: Literal["high", "medium", "low"]
    reasons: list[str] = Field(min_length=1, max_length=8)
    alternatives: list[str] = Field(default_factory=list, max_length=5)
    requires_confirmation: Literal[True] = True
    authority: Literal["codex", "groundloop_heuristic"] = "groundloop_heuristic"
    recorded_at: str | None = Field(default=None, max_length=80)


class DataEvidence(StrictModel):
    """A GroundLoop-calculated fact. Codex can cite it but cannot invent it."""

    evidence_id: str = Field(pattern=r"^data-evidence-[0-9a-f]{16}$")
    artifact_id: str
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selected_columns: list[str] = Field(min_length=1, max_length=8)
    row_start: int = Field(ge=2)
    row_end: int = Field(ge=2)
    operation: Literal[
        "raw_slice", "column_summary", "endpoint_delta", "argmax", "argmin", "range_extrema",
        "linear_fit", "correlation", "monotonicity", "group_summary", "grouped_extrema",
        "hysteresis_window", "power_law_fit", "local_peak", "group_comparison",
    ]
    parameters: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any]
    fact_text: str = Field(min_length=1, max_length=1000)
    engine: Literal["groundloop-generic-tabular"] = "groundloop-generic-tabular"
    engine_version: Literal["1.0.0"] = "1.0.0"
    binding_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    visualization_hint: Literal["line", "scatter", "table", "summary"] = "summary"
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
