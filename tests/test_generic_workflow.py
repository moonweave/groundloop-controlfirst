from pathlib import Path

import pytest

from packages.core.generic_tabular import profile_csv
from packages.core.models import (
    AlignmentAdjudication,
    ClaimInput,
    ControlProposal,
    DatasetBinding,
    MeasurementModalityProposal,
    RequiredSignature,
    SourceAdjudication,
    SourceInput,
)
from packages.core.store import RunStore


SPECTRUM = b"wavelength_nm,intensity_counts\n580,12\n600,28\n620,91\n640,45\n660,18\n"


def _codex_spectrum_proposal() -> MeasurementModalityProposal:
    return MeasurementModalityProposal(
        candidate="generic_spectrum",
        confidence="high",
        reasons=["The method and bounded CSV describe steady-state wavelength-intensity spectroscopy."],
        alternatives=["generic_sweep"],
        authority="codex",
    )


def _source() -> SourceInput:
    return SourceInput(
        id="src-spectrum-limit",
        title="Spectral assignment limitations",
        authors=["Test Lab"],
        year=2025,
        url_or_doi="https://example.invalid/spectrum",
        locator={"section": "Methods"},
        untrusted_content="A steady-state spectral feature alone does not uniquely assign a mechanism; an independent temperature or lifetime control is required.",
    )


def _complete_to_analysis(store: RunStore) -> tuple[str, str]:
    source = _source()
    detail = store.create_generic_run(
        ClaimInput(claim="A feature near 620 nm demonstrates defect-state emission."),
        "Steady-state photoluminescence was exported as a wavelength and intensity table under fixed excitation conditions.",
        SPECTRUM,
        [source],
        filename="spectrum.csv",
    )
    run_id = detail["run"]["run_id"]
    profile = store.inspect_dataset_profile(run_id)
    assert profile["modality_proposal"]["candidate"] == "generic_spectrum"
    assert profile["modality_proposal"]["authority"] == "groundloop_heuristic"
    store.record_measurement_modality(run_id, _codex_spectrum_proposal())
    store.set_dataset_binding(
        run_id,
        DatasetBinding(
            artifact_id="artifact-001",
            x_column_id="col-001",
            y_column_ids=["col-002"],
            confirmed_units={"col-001": "nm", "col-002": "counts"},
            confirmed_at="2026-07-21T00:00:00+00:00",
        ),
        "generic_spectrum",
    )
    store.record_source_reviews(
        run_id,
        [SourceAdjudication(source_id=source.id, verdict="direct", role="method_limit", rationale="The excerpt limits mechanism assignment from a steady-state feature.")],
    )
    store.prepare_packet(run_id)
    store.inspect_sources(
        run_id,
        [{
            "expected_observation": "A steady-state feature alone is non-unique.",
            "condition": "Only the supplied excerpt is in the frozen source boundary.",
            "falsifier": "The supplied excerpt does not state an assignment limitation.",
            "evidence_ref_ids": ["src-spectrum-limit:evidence"],
        }],
    )
    store.analyze_dataset(run_id)
    evidence = store.materialize_data_evidence(run_id, "argmax", ["col-001", "col-002"], 2, 6)
    return run_id, evidence["evidence_id"]


def test_generic_spectrum_run_materializes_evidence_and_exports(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    run_id, evidence_id = _complete_to_analysis(store)
    store.record_signatures(
        run_id,
        [
            RequiredSignature(id="signature-feature", name="Feature presence", requirement="A near-620 nm feature is present.", expected_observation="Maximum intensity occurs near 620 nm.", falsifying_outcome="No feature occurs near 620 nm.", theory_evidence_ref_ids=["src-spectrum-limit:evidence"]),
            RequiredSignature(id="signature-assignment", name="Mechanism assignment", requirement="The feature is distinguishable from alternatives.", expected_observation="An independent discriminator separates alternatives.", falsifying_outcome="Alternatives remain compatible.", theory_evidence_ref_ids=["src-spectrum-limit:evidence"]),
            RequiredSignature(id="signature-specificity", name="Mechanism specificity", requirement="A mechanism-specific response is measured.", expected_observation="A discriminating response is present.", falsifying_outcome="No discriminator is measured."),
        ],
    )
    store.record_alignments(
        run_id,
        [
            AlignmentAdjudication(signature_id="signature-feature", status="Observed", rationale="The materialized maximum is at 620 nm.", evidence_ref_ids=[evidence_id]),
            AlignmentAdjudication(signature_id="signature-assignment", status="Confounded", rationale="The feature remains non-unique.", evidence_ref_ids=[evidence_id, "method-evidence-frozen", "src-spectrum-limit:evidence"], alternative_explanation="A different emissive state can produce a steady-state feature in the same range."),
            AlignmentAdjudication(signature_id="signature-specificity", status="Missing", rationale="No discriminator was recorded.", missing_reason="not_measured"),
        ],
    )
    store.record_control_contract(
        run_id,
        ControlProposal(
            confound="Non-unique steady-state spectral assignment",
            experiment="Repeat the matched spectrum across a controlled temperature series.",
            preconditions=["Same sample", "Same excitation", "Same collection geometry"],
            outcomes=[
                {"if": "The feature follows the predicted response", "then": "The assignment gains support."},
                {"if": "The feature lacks the predicted response", "then": "Alternatives remain favored."},
            ],
            signature_ref_ids=["signature-assignment"],
            closes_signature_ids=["signature-assignment"],
            leaves_open_signature_ids=["signature-specificity"],
            priority="high",
            feasibility="One matched temperature series.",
        ),
    )
    report = store.export_report(run_id)
    assert isinstance(report, dict)
    assert report["verdict"]["label"] == "NOT_ESTABLISHED"
    assert report["data_evidence"][0]["result"]["x"] == 620
    markdown = store.get_report_markdown(run_id)
    assert "Materialized data evidence" in markdown
    assert "two-wire" not in markdown.lower()
    assert "resistance" not in markdown.lower()


def test_generic_alignments_reject_unmaterialized_observation(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    run_id, _ = _complete_to_analysis(store)
    store.record_signatures(
        run_id,
        [
            RequiredSignature(id="signature-feature", name="Feature", requirement="A feature is present.", expected_observation="A peak exists.", falsifying_outcome="No peak exists."),
            RequiredSignature(id="signature-other", name="Other", requirement="A second condition is met.", expected_observation="A second response exists.", falsifying_outcome="It does not."),
        ],
    )
    with pytest.raises(ValueError, match="materialized"):
        store.record_alignments(
            run_id,
            [
                AlignmentAdjudication(signature_id="signature-feature", status="Observed", rationale="A raw artifact was supplied.", evidence_ref_ids=["method-evidence-frozen"]),
                AlignmentAdjudication(signature_id="signature-other", status="Missing", rationale="Not measured.", missing_reason="not_measured"),
            ],
        )


def test_generic_dataset_update_reprofiles_and_requires_rebinding(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    detail = store.create_generic_run(
        ClaimInput(claim="A tabular response has an identifiable signature."),
        "A bounded local tabular measurement was exported with method context sufficient for later review.",
        SPECTRUM,
        [_source()],
    )
    run_id = detail["run"]["run_id"]
    with pytest.raises(ValueError, match="Codex-authored"):
        store.set_dataset_binding(
            run_id,
            DatasetBinding(artifact_id="artifact-001", x_column_id="col-001", y_column_ids=["col-002"], confirmed_at="2026-07-21T00:00:00+00:00"),
            "generic_spectrum",
        )
    store.record_measurement_modality(run_id, _codex_spectrum_proposal())
    store.set_dataset_binding(
        run_id,
        DatasetBinding(artifact_id="artifact-001", x_column_id="col-001", y_column_ids=["col-002"], confirmed_at="2026-07-21T00:00:00+00:00"),
        "generic_spectrum",
    )
    store.record_source_reviews(run_id, [SourceAdjudication(source_id="src-spectrum-limit", verdict="direct", role="method_limit", rationale="The supplied excerpt limits mechanism assignment.")])
    store.update_claim(run_id, ClaimInput(claim="A feature near 620 nm distinguishes the proposed emissive mechanism."))
    assert store.get_detail(run_id)["draft"]["modality_proposal"]["authority"] == "groundloop_heuristic"
    with pytest.raises(ValueError, match="stale or missing Codex"):
        store.prepare_packet(run_id)
    updated = store.update_dataset(run_id, b"time_s,displacement_mm\n0,0\n1,1.2\n")
    assert updated["dataset_profile"]["columns"][0]["name"] == "time_s"
    assert store.get_detail(run_id)["draft"]["dataset_binding"] is None
    assert store.get_detail(run_id)["draft"]["modality_proposal"]["authority"] == "groundloop_heuristic"
    with pytest.raises(ValueError, match="Codex-authored"):
        store.set_dataset_binding(
            run_id,
            DatasetBinding(artifact_id="artifact-001", x_column_id="col-001", y_column_ids=["col-002"], confirmed_at="2026-07-21T00:00:00+00:00"),
            "generic_spectrum",
        )
    with pytest.raises(ValueError, match="reconfirm"):
        store.prepare_packet(run_id)


def test_generic_profiler_accepts_bom_quoted_headers_and_preserves_rows() -> None:
    _, profile = profile_csv("\ufeffwavelength_nm,intensity_counts,label\n580,12,\"reference, dark\"\n620,,sample\n".encode())
    assert profile.row_order_preserved is True
    assert profile.columns[0].unit.status == "candidate"
    assert profile.columns[1].missing_count == 1
    assert profile.sample_rows[0]["label"] == "reference, dark"


@pytest.mark.parametrize("raw", [b",intensity\n1,2\n", b"x,x\n1,2\n", b"x,y\n1\n"])
def test_generic_profiler_rejects_unsafe_headers_or_width(raw: bytes) -> None:
    with pytest.raises(ValueError):
        profile_csv(raw)
