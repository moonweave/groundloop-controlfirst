from pathlib import Path

from services.mcp_server import main as mcp_main
from packages.core.models import DatasetBinding, SourceAdjudication, SourceInput
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
    binding = mcp_main.set_dataset_binding(
        run_id,
        DatasetBinding(artifact_id="artifact-001", x_column_id="col-001", y_column_ids=["col-002"], confirmed_units={"col-001": "nm", "col-002": "counts"}, confirmed_at="2026-07-21T00:00:00+00:00"),
        "generic_spectrum",
    )
    assert binding["ok"] is True
    reviewed = mcp_main.record_source_reviews(run_id, [SourceAdjudication(source_id="src-limit", verdict="direct", role="method_limit", rationale="The excerpt limits mechanism assignment.")])
    assert reviewed["ok"] is True
    assert mcp_main.store.prepare_packet(run_id)["state"] == "PACKET_READY"
    assert mcp_main.inspect_sources(run_id)["ok"] is True
    assert mcp_main.analyze_dataset(run_id)["ok"] is True
    evidence = mcp_main.materialize_data_evidence(run_id, "argmax", ["col-001", "col-002"], 2, 4)
    assert evidence["ok"] is True
    assert evidence["result"]["result"]["x"] == 620
