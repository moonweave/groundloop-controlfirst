import hashlib
from pathlib import Path

import pytest

from packages.core.generic_tabular import profile_csv
from packages.core.models import (
    AlignmentAdjudication,
    ClaimInput,
    ControlProposal,
    DatasetBinding,
    LiteratureCandidate,
    MeasurementModalityProposal,
    RequiredSignature,
    SourceAdjudication,
    SourceInput,
)
from packages.core.store import RunStore


SPECTRUM = b"wavelength_nm,intensity_counts\n580,12\n600,28\n620,91\n640,45\n660,18\n"
TEMPERATURE_CONTROL = b"temperature_c,peak_intensity_counts\n20,41\n40,58\n60,79\n80,104\n"


def _codex_spectrum_proposal() -> MeasurementModalityProposal:
    return MeasurementModalityProposal(
        candidate="generic_spectrum",
        confidence="high",
        reasons=["The method and bounded CSV describe steady-state wavelength-intensity spectroscopy."],
        alternatives=["generic_sweep"],
        authority="codex",
    )


def _literature_candidate(source_id: str, url: str = "https://doi.org/10.1000/spectrum", excerpt_suffix: str = "") -> LiteratureCandidate:
    excerpt = "A steady-state spectral feature does not uniquely identify a microscopic mechanism without an independent discriminator." + excerpt_suffix
    return LiteratureCandidate(
        id=source_id,
        title="Limits of steady-state spectral assignment",
        authors=["Test Lab"],
        year=2024,
        url_or_doi=url,
        retrieval_provider="crossref",
        publication_status="peer_reviewed",
        excerpt=excerpt,
        locator={"section": "Abstract"},
        retrieved_at="2026-07-21T00:00:00+00:00",
        search_query="steady state spectral assignment mechanism control",
        discovery_rationale="Codex found this source while checking whether the supplied measurement can distinguish the claimed mechanism.",
        content_sha256=hashlib.sha256(excerpt.encode()).hexdigest(),
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
    store.import_literature_candidates(run_id, [_literature_candidate("src-spectrum-candidate", "https://doi.org/10.1000/spectrum-candidate")])
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
        [
            SourceAdjudication(source_id=source.id, verdict="direct", role="method_limit", rationale="The excerpt limits mechanism assignment from a steady-state feature."),
            SourceAdjudication(source_id="src-spectrum-candidate", verdict="reject", rationale="The imported candidate is retained in provenance but not used for this decision."),
        ],
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
    assert "Literature provenance" in markdown
    assert "Excerpt SHA-256" in markdown
    assert "two-wire" not in markdown.lower()
    assert "resistance" not in markdown.lower()


def test_multi_artifact_generic_run_freezes_materializes_and_exports_cross_artifact_evidence(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    detail = store.create_generic_run(
        ClaimInput(claim="A spectral feature is caused by the proposed defect-state mechanism."),
        "Steady-state spectrum and a matched temperature-control intensity series were exported as separate CSV artifacts under fixed excitation geometry.",
        SPECTRUM,
        [_source()],
        filename="primary-spectrum.csv",
    )
    run_id = detail["run"]["run_id"]
    added = store.add_measurement_artifact(
        run_id,
        TEMPERATURE_CONTROL,
        artifact_id="artifact-control",
        filename="temperature-control.csv",
        label="control_measurement",
    )
    assert len(added["artifacts"]) == 2
    assert added["artifacts"][1]["sha256"] == hashlib.sha256(TEMPERATURE_CONTROL).hexdigest()
    assert added["profiles"][1]["columns"][0]["name"] == "temperature_c"
    store.record_measurement_modality(run_id, _codex_spectrum_proposal())
    store.set_artifact_binding(
        run_id,
        DatasetBinding(artifact_id="artifact-001", x_column_id="col-001", y_column_ids=["col-002"], confirmed_at="2026-07-21T00:00:00+00:00"),
        "generic_spectrum",
    )
    store.record_source_reviews(run_id, [SourceAdjudication(source_id="src-spectrum-limit", verdict="direct", role="method_limit", rationale="The supplied excerpt limits mechanism assignment from a steady-state feature.")])
    with pytest.raises(ValueError, match="every measurement artifact"):
        store.prepare_packet(run_id)
    store.set_artifact_binding(
        run_id,
        DatasetBinding(artifact_id="artifact-control", x_column_id="col-001", y_column_ids=["col-002"], confirmed_at="2026-07-21T00:00:00+00:00"),
        "generic_spectrum",
    )
    store.prepare_packet(run_id)
    packet = store.get_packet(run_id)
    assert [item["artifact_id"] for item in packet["artifacts"]] == ["artifact-001", "artifact-control"]
    assert {item["artifact_id"] for item in packet["artifact_bindings"]} == {"artifact-001", "artifact-control"}
    store.inspect_sources(run_id, [{"expected_observation": "assignment requires a discriminator", "condition": "source excerpt is frozen", "falsifier": "excerpt does not describe the limitation", "evidence_ref_ids": ["src-spectrum-limit:evidence"]}])
    store.analyze_dataset(run_id)
    spectral_evidence = store.materialize_data_evidence(run_id, "argmax", ["col-001", "col-002"], 2, 6, artifact_id="artifact-001")
    control_evidence = store.materialize_data_evidence(run_id, "endpoint_delta", ["col-001", "col-002"], 2, 5, artifact_id="artifact-control")
    assert spectral_evidence["artifact_id"] == "artifact-001"
    assert control_evidence["artifact_id"] == "artifact-control"
    store.record_signatures(
        run_id,
        [
            RequiredSignature(id="signature-feature", name="Feature", requirement="A spectral peak is present.", expected_observation="The primary spectrum contains a peak.", falsifying_outcome="No peak is present.", theory_evidence_ref_ids=["src-spectrum-limit:evidence"]),
            RequiredSignature(id="signature-temperature-response", name="Temperature response", requirement="The control series changes as predicted.", expected_observation="Peak intensity changes across temperature.", falsifying_outcome="The peak intensity is invariant."),
        ],
    )
    store.record_alignments(
        run_id,
        [
            AlignmentAdjudication(signature_id="signature-feature", status="Observed", rationale="The primary spectrum has a materialized maximum.", evidence_ref_ids=[spectral_evidence["evidence_id"]]),
            AlignmentAdjudication(signature_id="signature-temperature-response", status="Observed", rationale="The control artifact shows a temperature-linked intensity change.", evidence_ref_ids=[spectral_evidence["evidence_id"], control_evidence["evidence_id"]], artifact_relation_rationale="The signature cites the spectral feature artifact and the separate temperature-control artifact without merging rows."),
        ],
    )
    store.record_control_contract(
        run_id,
        ControlProposal(
            confound="Steady-state spectral non-uniqueness",
            experiment="Add a lifetime-resolved spectrum under the same excitation geometry.",
            preconditions=["Same sample", "Same excitation", "Same collection geometry"],
            outcomes=[
                {"if": "Lifetime follows the defect-state prediction", "then": "The assignment gains bounded support."},
                {"if": "Lifetime does not follow the prediction", "then": "The defect-state assignment is weakened."},
            ],
            signature_ref_ids=["signature-temperature-response"],
            closes_signature_ids=["signature-temperature-response"],
            leaves_open_signature_ids=["signature-feature"],
            required_artifact_labels=["lifetime_control"],
            priority="high",
            feasibility="One additional matched artifact.",
        ),
    )
    report = store.export_report(run_id)
    assert len(report["artifacts"]) == 2
    markdown = store.get_report_markdown(run_id)
    assert "## Measurement artifacts" in markdown
    assert "artifact-control" in markdown
    assert "## Cross-artifact evidence" in markdown
    assert "lifetime_control" in markdown


def test_multi_artifact_rejects_duplicate_identity_hash_and_frozen_mutation(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    detail = store.create_generic_run(
        ClaimInput(claim="A spectral feature is caused by a proposed mechanism."),
        "Steady-state spectrum was exported as a bounded CSV with enough method context for source review and controls.",
        SPECTRUM,
        [_source()],
    )
    run_id = detail["run"]["run_id"]
    with pytest.raises(ValueError, match="duplicate measurement artifact ID"):
        store.add_measurement_artifact(run_id, TEMPERATURE_CONTROL, artifact_id="artifact-001")
    with pytest.raises(ValueError, match="duplicate measurement artifact hash"):
        store.add_measurement_artifact(run_id, SPECTRUM, artifact_id="artifact-copy")
    store.record_measurement_modality(run_id, _codex_spectrum_proposal())
    store.set_artifact_binding(run_id, DatasetBinding(artifact_id="artifact-001", x_column_id="col-001", y_column_ids=["col-002"], confirmed_at="2026-07-21T00:00:00+00:00"), "generic_spectrum")
    store.record_source_reviews(run_id, [SourceAdjudication(source_id="src-spectrum-limit", verdict="direct", role="method_limit", rationale="The source limits the assignment.")])
    store.prepare_packet(run_id)
    with pytest.raises(ValueError, match="DRAFT"):
        store.add_measurement_artifact(run_id, TEMPERATURE_CONTROL, artifact_id="artifact-control")


def test_artifact_update_stales_existing_bindings_and_routing(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    detail = store.create_generic_run(
        ClaimInput(claim="A spectral feature is caused by a proposed mechanism."),
        "Steady-state spectrum and a control table were exported separately with bounded method context.",
        SPECTRUM,
        [_source()],
    )
    run_id = detail["run"]["run_id"]
    store.add_measurement_artifact(run_id, TEMPERATURE_CONTROL, artifact_id="artifact-control", label="control_measurement")
    store.record_measurement_modality(run_id, _codex_spectrum_proposal())
    store.set_artifact_binding(run_id, DatasetBinding(artifact_id="artifact-001", x_column_id="col-001", y_column_ids=["col-002"], confirmed_at="2026-07-21T00:00:00+00:00"), "generic_spectrum")
    store.set_artifact_binding(run_id, DatasetBinding(artifact_id="artifact-control", x_column_id="col-001", y_column_ids=["col-002"], confirmed_at="2026-07-21T00:00:00+00:00"), "generic_spectrum")
    store.record_source_reviews(run_id, [SourceAdjudication(source_id="src-spectrum-limit", verdict="direct", role="method_limit", rationale="The source limits mechanism assignment.")])
    store.update_dataset(run_id, b"wavelength_nm,intensity_counts\n500,2\n510,4\n")
    draft = store.get_detail(run_id)["draft"]
    assert draft["artifact_bindings"] == []
    assert draft["modality_proposal"]["authority"] == "groundloop_heuristic"
    with pytest.raises(ValueError, match="reconfirm"):
        store.prepare_packet(run_id)


def test_imported_literature_is_bounded_provenance_and_requires_review(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    detail = store.create_generic_run(
        ClaimInput(claim="A feature near 620 nm demonstrates defect-state emission."),
        "Steady-state photoluminescence was exported as a wavelength and intensity table under fixed excitation conditions.",
        SPECTRUM,
        [],
        filename="spectrum.csv",
    )
    run_id = detail["run"]["run_id"]
    store.import_literature_candidates(run_id, [_literature_candidate("src-imported-a"), _literature_candidate("src-imported-b", "https://doi.org/10.1000/spectrum-b", " A second source reports the same limitation.")])
    draft = store.get_detail(run_id)["draft"]
    assert len(draft["sources"]) == 2
    assert draft["sources"][0]["retrieval_provider"] == "crossref"
    assert draft["sources"][0]["publication_status"] == "peer_reviewed"
    assert draft["retrieval_review"]["status"] == "required"
    with pytest.raises(ValueError, match="source roles"):
        store.prepare_packet(run_id)
    store.record_source_reviews(
        run_id,
        [
            SourceAdjudication(source_id="src-imported-a", verdict="direct", role="method_limit", rationale="The bounded excerpt states the assignment limitation."),
            SourceAdjudication(source_id="src-imported-b", verdict="reject", rationale="The candidate is not needed for this bounded decision."),
        ],
    )
    store.set_dataset_binding(
        run_id,
        DatasetBinding(artifact_id="artifact-001", x_column_id="col-001", y_column_ids=["col-002"], confirmed_units={"col-001": "nm", "col-002": "counts"}, confirmed_at="2026-07-21T00:00:00+00:00"),
    )
    store.prepare_packet(run_id)
    packet = store.get_packet(run_id)
    assert packet["source_candidates"][0]["search_query"]
    assert packet["source_candidates"][0]["content_sha256"] == hashlib.sha256(packet["source_candidates"][0]["untrusted_content"].encode()).hexdigest()
    assert packet["candidate_review"]["adjudications"][1]["verdict"] == "reject"


def test_import_rejects_duplicate_identity_and_invalid_excerpt_hash(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    detail = store.create_generic_run(
        ClaimInput(claim="A bounded measurement contains a discriminating response."),
        "A local tabular measurement was exported with method context sufficient for source review and control design.",
        b"x,y\n1,2\n2,4\n",
        [],
    )
    run_id = detail["run"]["run_id"]
    store.import_literature_candidates(run_id, [_literature_candidate("src-imported-a")])
    with pytest.raises(ValueError, match="duplicate literature candidate identity"):
        store.import_literature_candidates(run_id, [_literature_candidate("src-imported-b", "doi:10.1000/spectrum")])
    with pytest.raises(ValueError, match="content_sha256"):
        LiteratureCandidate(**{**_literature_candidate("src-invalid").model_dump(), "content_sha256": "0" * 64})
    with pytest.raises(ValueError, match="publication_status"):
        LiteratureCandidate.model_validate({**_literature_candidate("src-status").model_dump(), "publication_status": "journal"})
    with pytest.raises(ValueError, match="page"):
        LiteratureCandidate.model_validate({**_literature_candidate("src-locator").model_dump(), "locator": {"page": 0}})


def test_source_change_invalidates_review_and_frozen_runs_reject_mutation(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    detail = store.create_generic_run(
        ClaimInput(claim="A bounded measurement contains a discriminating response."),
        "A local tabular measurement was exported with method context sufficient for source review and control design.",
        b"x,y\n1,2\n2,4\n",
        [],
    )
    run_id = detail["run"]["run_id"]
    first = _literature_candidate("src-first", "https://doi.org/10.1000/first")
    store.import_literature_candidates(run_id, [first])
    store.record_measurement_modality(run_id, MeasurementModalityProposal(candidate="generic_sweep", confidence="medium", reasons=["Codex read the bounded method and selected a generic sweep interpretation."], authority="codex"))
    store.set_dataset_binding(run_id, DatasetBinding(artifact_id="artifact-001", x_column_id="col-001", y_column_ids=["col-002"], confirmed_at="2026-07-21T00:00:00+00:00"))
    store.record_source_reviews(run_id, [SourceAdjudication(source_id="src-first", verdict="direct", role="theory_basis", rationale="The candidate is relevant to the claimed response.")])
    updated = SourceInput(
        id="src-second",
        title="A changed bounded source",
        authors=["Test Lab"],
        year=2026,
        url_or_doi="https://doi.org/10.1000/second",
        locator={"section": "Methods"},
        untrusted_content="This replacement excerpt changes the source boundary and must be reviewed.",
        retrieval_provider="manual",
        publication_status="unknown",
    )
    store.update_sources(run_id, [updated])
    assert store.get_detail(run_id)["draft"]["retrieval_review"]["status"] == "required"
    with pytest.raises(ValueError, match="source roles"):
        store.prepare_packet(run_id)
    store.record_source_reviews(run_id, [SourceAdjudication(source_id="src-second", verdict="direct", role="method_limit", rationale="The replacement excerpt is now the reviewed source boundary.")])
    store.prepare_packet(run_id)
    with pytest.raises(ValueError, match="DRAFT"):
        store.update_sources(run_id, [updated])


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
    binding_result = store.set_dataset_binding(
        run_id,
        DatasetBinding(artifact_id="artifact-001", x_column_id="col-001", y_column_ids=["col-002"], confirmed_at="2026-07-21T00:00:00+00:00"),
        "generic_spectrum",
    )
    assert binding_result["bindings"][0]["artifact_id"] == "artifact-001"
    store.record_measurement_modality(run_id, _codex_spectrum_proposal())
    store.set_dataset_binding(
        run_id,
        DatasetBinding(artifact_id="artifact-001", x_column_id="col-001", y_column_ids=["col-002"], confirmed_at="2026-07-21T00:00:00+00:00"),
        "generic_spectrum",
    )
    store.record_source_reviews(run_id, [SourceAdjudication(source_id="src-spectrum-limit", verdict="direct", role="method_limit", rationale="The supplied excerpt limits mechanism assignment.")])
    store.update_claim(run_id, ClaimInput(claim="A feature near 620 nm distinguishes the proposed emissive mechanism."))
    assert store.get_detail(run_id)["draft"]["modality_proposal"]["authority"] == "groundloop_heuristic"
    store.prepare_packet(run_id)
    with pytest.raises(ValueError, match="DRAFT"):
        store.update_dataset(run_id, b"time_s,displacement_mm\n0,0\n1,1.2\n")


def test_capability_pack_mismatch_does_not_constrain_codex_reasoning(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    detail = store.create_generic_run(
        ClaimInput(claim="A tabular response has an identifiable signature."),
        "A bounded local tabular measurement was exported with method context sufficient for later review.",
        SPECTRUM,
        [_source()],
    )
    run_id = detail["run"]["run_id"]
    store.record_measurement_modality(
        run_id,
        MeasurementModalityProposal(candidate="generic_sweep", confidence="low", reasons=["Codex kept the routing broad because the mechanism comparison is not recipe-bound."], authority="codex"),
    )
    store.set_dataset_binding(
        run_id,
        DatasetBinding(artifact_id="artifact-001", x_column_id="col-001", y_column_ids=["col-002"], confirmed_at="2026-07-21T00:00:00+00:00"),
        "generic_spectrum",
    )
    store.record_source_reviews(run_id, [SourceAdjudication(source_id="src-spectrum-limit", verdict="direct", role="method_limit", rationale="The supplied excerpt limits mechanism assignment.")])
    store.prepare_packet(run_id)
    packet = store.get_packet(run_id)
    assert packet["recipe"]["kind"] == "measurement_capability_pack"
    assert packet["recipe"]["id"] == "generic_spectrum"
    assert packet["recipe"]["routing_candidate"] == "generic_sweep"
    assert packet["recipe"]["routing_match_required"] is False
    store.inspect_sources(run_id, [{"expected_observation": "assignment is limited", "condition": "source excerpt is frozen", "falsifier": "excerpt does not describe a limitation", "evidence_ref_ids": ["src-spectrum-limit:evidence"]}])
    store.analyze_dataset(run_id)
    evidence = store.materialize_data_evidence(run_id, "argmax", ["col-001", "col-002"], 2, 6)
    store.record_signatures(
        run_id,
        [
            RequiredSignature(id="signature-feature", name="Feature", requirement="A feature is present.", expected_observation="A peak exists.", falsifying_outcome="No peak exists."),
            RequiredSignature(id="signature-specificity", name="Specificity", requirement="The mechanism is distinguishable.", expected_observation="A discriminator exists.", falsifying_outcome="No discriminator exists."),
        ],
    )
    store.record_alignments(
        run_id,
        [
            AlignmentAdjudication(signature_id="signature-feature", status="Observed", rationale="Codex can still cite the materialized data fact.", evidence_ref_ids=[evidence["evidence_id"]]),
            AlignmentAdjudication(signature_id="signature-specificity", status="Missing", rationale="The capability pack does not supply a scientific discriminator.", missing_reason="not_measured"),
        ],
    )


def test_generic_dataset_update_reprofiles_and_requires_rebinding_after_artifact_change(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    detail = store.create_generic_run(
        ClaimInput(claim="A tabular response has an identifiable signature."),
        "A bounded local tabular measurement was exported with method context sufficient for later review.",
        SPECTRUM,
        [_source()],
    )
    run_id = detail["run"]["run_id"]
    store.record_measurement_modality(run_id, _codex_spectrum_proposal())
    store.set_dataset_binding(
        run_id,
        DatasetBinding(artifact_id="artifact-001", x_column_id="col-001", y_column_ids=["col-002"], confirmed_at="2026-07-21T00:00:00+00:00"),
        "generic_spectrum",
    )
    store.record_source_reviews(run_id, [SourceAdjudication(source_id="src-spectrum-limit", verdict="direct", role="method_limit", rationale="The supplied excerpt limits mechanism assignment.")])
    updated = store.update_dataset(run_id, b"time_s,displacement_mm\n0,0\n1,1.2\n")
    assert updated["dataset_profile"]["columns"][0]["name"] == "time_s"
    assert store.get_detail(run_id)["draft"]["dataset_binding"] is None
    assert store.get_detail(run_id)["draft"]["modality_proposal"]["authority"] == "groundloop_heuristic"
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
