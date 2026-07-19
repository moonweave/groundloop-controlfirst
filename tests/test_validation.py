import pytest

from packages.core.models import DatasetAnalysis, EvidenceRef, Finding, Locator
from packages.core.validation import validate_findings


def test_observed_finding_cannot_claim_mechanism() -> None:
    data = EvidenceRef(
        id="data-001:rows-2-3",
        kind="data",
        artifact_id="data-001",
        locator=Locator(columns=["temperature_c", "two_wire_resistance_ohm"], row_start=2, row_end=3),
        excerpt="Two data rows",
        sha256="0" * 64,
    )
    dataset = DatasetAnalysis(
        columns=["temperature_c", "two_wire_resistance_ohm"],
        row_count=2,
        temperature_range_c=(20, 30),
        resistance_min_ohm=8,
        resistance_min_row=3,
        resistance_max_ohm=10,
        resistance_max_row=2,
        first_resistance_ohm=10,
        last_resistance_ohm=8,
        change_ohm=-2,
        percent_change=-20,
        monotonicity_segments=["rows 2-3: falling"],
        cited_row_range=(2, 3),
        rows=[{"temperature_c": 20, "two_wire_resistance_ohm": 10}, {"temperature_c": 30, "two_wire_resistance_ohm": 8}],
    )
    finding = Finding(
        id="finding-invalid-observation",
        statement="The decreasing trace proves the mechanism.",
        status="Observed",
        evidence_ref_ids=[data.id],
        reasoning="Invalid causal overreach.",
    )

    with pytest.raises(ValueError, match="causal language"):
        validate_findings([finding], [data], dataset)
