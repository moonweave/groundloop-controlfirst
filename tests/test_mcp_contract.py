import hashlib
from pathlib import Path

from services.mcp_server import main as mcp_main
from packages.core.models import DatasetBinding, LiteratureCandidate, MeasurementModalityProposal, SourceAdjudication, SourceInput
from packages.core.store import RunStore


def test_update_run_is_atomic_when_a_later_field_is_invalid(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(mcp_main, "store", RunStore(tmp_path / "runs"))
    original_claim = "Does this resistance sweep establish a bulk transition?"
    created = mcp_main.create_run(
        claim=original_claim,
        methods="Two-terminal resistance was recorded during a temperature sweep.",
        dataset_csv="temperature_c,two_wire_resistance_ohm\n20,120\n30,100\n",
    )
    run_id = created["result"]["run"]["run_id"]

    failed = mcp_main.update_run(
        run_id,
        claim="A replacement claim that must not be partially saved.",
        methods="too short",
    )

    assert failed["ok"] is False
    detail = mcp_main.get_run(run_id)
    assert detail["result"]["draft"]["claim"]["claim"] == original_claim


def test_generic_mcp_profile_binding_and_materialized_fact(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(mcp_main, "store", RunStore(tmp_path / "runs"))
    source = SourceInput(id="src-limit", title="Spectral limit", authors=["Lab"], year=2025, url_or_doi="https://example.invalid/limit", locator={"section": "Abstract"}, untrusted_content="A steady-state feature alone does not uniquely assign a mechanism.")
    created = mcp_main.create_generic_run(
        claim="A feature near 620 nm demonstrates defect-state emission.",
        methods="Steady-state spectra were exported as wavelength and intensity tables under fixed excitation conditions.",
        dataset_csv="wavelength_nm,intensity_counts\n580,12\n620,91\n660,18\n",
        sources=[source],
    )
    assert created["ok"] is True
    run_id = created["result"]["run"]["run_id"]
    profile = mcp_main.inspect_dataset_profile(run_id)
    assert profile["result"]["profile"]["columns"][0]["name"] == "wavelength_nm"
    excerpt = "An independent control is required before a steady-state feature can identify a mechanism."
    imported = mcp_main.import_literature_candidates(
        run_id,
        [LiteratureCandidate(
            id="src-imported",
            title="Spectral assignment limits",
            authors=["Lab"],
            year=2024,
            url_or_doi="https://doi.org/10.1000/imported",
            retrieval_provider="crossref",
            publication_status="peer_reviewed",
            excerpt=excerpt,
            locator={"section": "Abstract"},
            retrieved_at="2026-07-21T00:00:00+00:00",
            search_query="spectral assignment limitation",
            discovery_rationale="Codex checked whether the feature identifies the claimed mechanism.",
            content_sha256=hashlib.sha256(excerpt.encode()).hexdigest(),
        )],
    )
    assert imported["ok"] is True
    assert any(item["retrieval_provider"] == "crossref" for item in imported["result"]["draft"]["sources"])
    rejected = mcp_main.set_dataset_binding(
        run_id,
        DatasetBinding(artifact_id="artifact-001", x_column_id="col-001", y_column_ids=["col-002"], confirmed_units={"col-001": "nm", "col-002": "counts"}, confirmed_at="2026-07-21T00:00:00+00:00"),
        "generic_spectrum",
    )
    assert rejected["ok"] is False
    routed = mcp_main.record_measurement_modality(
        run_id,
        MeasurementModalityProposal(
            candidate="generic_spectrum",
            confidence="high",
            reasons=["The method and CSV are steady-state wavelength-intensity spectroscopy."],
            authority="codex",
        ),
    )
    assert routed["ok"] is True
    assert routed["result"]["modality_proposal"]["authority"] == "codex"
    binding = mcp_main.set_dataset_binding(
        run_id,
        DatasetBinding(artifact_id="artifact-001", x_column_id="col-001", y_column_ids=["col-002"], confirmed_units={"col-001": "nm", "col-002": "counts"}, confirmed_at="2026-07-21T00:00:00+00:00"),
        "generic_spectrum",
    )
    assert binding["ok"] is True
    reviewed = mcp_main.record_source_reviews(run_id, [
        SourceAdjudication(source_id="src-limit", verdict="direct", role="method_limit", rationale="The excerpt limits mechanism assignment."),
        SourceAdjudication(source_id="src-imported", verdict="reject", rationale="The candidate is retained in provenance but is not needed for this decision."),
    ])
    assert reviewed["ok"] is True
    assert mcp_main.store.prepare_packet(run_id)["state"] == "PACKET_READY"
    assert mcp_main.inspect_sources(run_id)["ok"] is True
    assert mcp_main.analyze_dataset(run_id)["ok"] is True
    evidence = mcp_main.materialize_data_evidence(run_id, "argmax", ["col-001", "col-002"], 2, 4)
    assert evidence["ok"] is True
    assert evidence["result"]["result"]["x"] == 620


def test_generic_mcp_multi_artifact_contract(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(mcp_main, "store", RunStore(tmp_path / "runs"))
    source = SourceInput(id="src-limit", title="Spectral limit", authors=["Lab"], year=2025, url_or_doi="https://example.invalid/limit", locator={"section": "Abstract"}, untrusted_content="A steady-state spectral feature alone does not uniquely identify a mechanism.")
    created = mcp_main.create_generic_run(
        claim="A spectral feature is caused by a defect-state mechanism.",
        methods="A primary spectrum and a separate temperature-control peak intensity table were exported as bounded CSV artifacts.",
        dataset_csv="wavelength_nm,intensity_counts\n580,12\n620,91\n660,18\n",
        sources=[source],
        filename="primary-spectrum.csv",
    )
    assert created["ok"] is True
    run_id = created["result"]["run"]["run_id"]
    added = mcp_main.add_measurement_artifact(
        run_id,
        "artifact-control",
        "temperature_c,peak_intensity_counts\n20,41\n40,58\n60,79\n",
        filename="temperature-control.csv",
        label="control_measurement",
    )
    assert added["ok"] is True
    inspected = mcp_main.inspect_measurement_artifacts(run_id)
    assert inspected["ok"] is True
    assert len(inspected["result"]["artifacts"]) == 2
    assert inspected["result"]["binding_status"][1]["status"] == "required"
    assert mcp_main.record_measurement_modality(
        run_id,
        MeasurementModalityProposal(candidate="generic_spectrum", confidence="high", reasons=["Codex read both artifact profiles as spectrum plus temperature-control evidence."], authority="codex"),
    )["ok"] is True
    assert mcp_main.set_artifact_binding(
        run_id,
        DatasetBinding(artifact_id="artifact-001", x_column_id="col-001", y_column_ids=["col-002"], confirmed_at="2026-07-21T00:00:00+00:00"),
        "generic_spectrum",
    )["ok"] is True
    assert mcp_main.set_artifact_binding(
        run_id,
        DatasetBinding(artifact_id="artifact-control", x_column_id="col-001", y_column_ids=["col-002"], confirmed_at="2026-07-21T00:00:00+00:00"),
        "generic_spectrum",
    )["ok"] is True
    assert mcp_main.record_source_reviews(run_id, [SourceAdjudication(source_id="src-limit", verdict="direct", role="method_limit", rationale="The source limits steady-state mechanism assignment.")])["ok"] is True
    assert mcp_main.store.prepare_packet(run_id)["state"] == "PACKET_READY"
    assert mcp_main.inspect_sources(run_id)["ok"] is True
    assert mcp_main.analyze_dataset(run_id)["ok"] is True
    evidence = mcp_main.materialize_data_evidence(run_id, "endpoint_delta", ["col-001", "col-002"], 2, 4, artifact_id="artifact-control")
    assert evidence["ok"] is True
    assert evidence["result"]["artifact_id"] == "artifact-control"
