from pathlib import Path

import pytest

from packages.core.models import ClaimInput, ControlProposal, Finding, Locator, SourceAdjudication, SourceInput
from packages.core.store import RunStore


FIXTURE = Path(__file__).parents[1] / "fixtures" / "four_wire_contact_control"


def _findings() -> list[Finding]:
    return [
        Finding(
            id="finding-four-wire-principle",
            statement="Four-terminal sensing separates current delivery from voltage sensing.",
            status="Established",
            evidence_ref_ids=["src-four-wire-principle:evidence"],
            reasoning="The supplied source states the measurement principle.",
        ),
        Finding(
            id="finding-resistance-change",
            statement="The supplied two-wire resistance decreases across the temperature sweep.",
            status="Observed",
            evidence_ref_ids=["data-001:rows-2-9"],
            reasoning="The deterministic CSV analysis reports a negative first-to-last change.",
        ),
        Finding(
            id="finding-bulk-inference",
            statement="The trend is consistent with, but does not establish, a bulk conductivity transition.",
            status="Inferred",
            evidence_ref_ids=["src-four-wire-principle:evidence", "data-001:rows-2-9"],
            reasoning="The observed trend is compatible with the stated interpretation.",
            uncertainty="The measurement is two-terminal and does not isolate contact contributions.",
            alternative_explanation="Temperature-dependent lead or contact resistance can also change the trace.",
        ),
        Finding(
            id="finding-contact-unresolved",
            statement="Contact and lead contributions remain unresolved without a matched four-terminal measurement.",
            status="Unresolved",
            evidence_ref_ids=["src-contact-contribution:evidence", "data-001:rows-2-9"],
            reasoning="No supplied evidence isolates the voltage drop across the sample.",
        ),
    ]


def _control() -> ControlProposal:
    return ControlProposal.model_validate(
        {
            "confound": "Temperature-dependent lead or contact resistance",
            "experiment": "Repeat the same temperature sweep in four-terminal mode while holding the sample, current, mounting, and temperature program fixed.",
            "preconditions": ["Same sample", "Same current", "Same mounting", "Same temperature program"],
            "outcomes": [
                {"if": "The trend persists in four-terminal mode", "then": "Support for a bulk contribution increases."},
                {"if": "The trend weakens substantially in four-terminal mode", "then": "A contact or lead contribution becomes more plausible."},
            ],
            "finding_ref_ids": ["finding-bulk-inference", "finding-contact-unresolved"],
            "priority": "high",
            "feasibility": "A matched four-terminal sweep is a bounded next measurement.",
        }
    )


def test_store_requires_ordered_evidence_workflow(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    run = store.create_fixture_run(FIXTURE)

    with pytest.raises(ValueError, match="PACKET_READY"):
        store.inspect_sources(run.run_id, [])

    store.prepare_packet(run.run_id)
    store.inspect_sources(
        run.run_id,
        [
            {
                "expected_observation": "Four-terminal sensing reduces lead contribution.",
                "condition": "The source applies to the measurement configuration.",
                "falsifier": "The supplied source does not state this principle.",
                "evidence_ref_ids": ["src-four-wire-principle:evidence"],
            }
        ],
    )
    store.analyze_dataset(run.run_id)
    store.reconcile_findings(run.run_id, _findings())
    store.propose_control(run.run_id, _control())
    report = store.export_report(run.run_id)

    assert report.state.value == "EXPORTED"
    assert report.control.priority == "high"
    assert report.verdict.label == "MECHANISM_NOT_ESTABLISHED"
    assert report.dataset_provenance == "FIXTURE_DEMO"
    assert report.source_relevance == []
    assert store.get_summary(run.run_id).state.value == "EXPORTED"
    stored_report = store._read(tmp_path / "runs" / run.run_id / "report" / "report.json")
    assert stored_report["control"]["outcomes"][0]["if"] == "The trend persists in four-terminal mode"
    assert "if_" not in stored_report["control"]["outcomes"][0]
    markdown = store.get_report_markdown(run.run_id)
    assert "MECHANISM NOT ESTABLISHED" in markdown
    assert "### Established" in markdown
    assert "## ControlFirst" in markdown
    assert "src-four-wire-principle" in markdown


def test_store_rejects_path_like_run_id(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    with pytest.raises(ValueError, match="invalid run id"):
        store.get_summary("../../etc")


def test_list_runs_ignores_mismatched_or_malformed_manifests(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    valid = store.create_run()
    valid_manifest = store._read(tmp_path / "runs" / valid.run_id / "manifest.json")

    legacy_copy = tmp_path / "runs" / "legacy-copy" / "manifest.json"
    legacy_copy.parent.mkdir()
    store._write(legacy_copy, valid_manifest)
    malformed_manifest = {**valid_manifest, "run_id": "not-a-uuid"}
    legacy_invalid = tmp_path / "runs" / "legacy-invalid" / "manifest.json"
    legacy_invalid.parent.mkdir()
    store._write(legacy_invalid, malformed_manifest)

    assert [run.run_id for run in store.list_runs()] == [valid.run_id]


def test_store_freezes_an_evidence_packet_when_retrieval_signals_are_limited(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    run = store.create_run()
    store.save_inputs(
        run.run_id,
        ClaimInput(claim="Does a two-wire resistance sweep establish a bulk transition?"),
        [
            SourceInput(
                id="openalex-adjacent",
                title="Optical calibration methods",
                authors=["Researcher"],
                year=2025,
                url_or_doi="https://doi.org/10.1/adjacent",
                locator=Locator(section="Abstract"),
                untrusted_content="Microscope focus was calibrated with a reference target.",
            )
        ],
        "Two-terminal resistance was recorded during a temperature sweep.",
        b"temperature_c,two_wire_resistance_ohm\n20,120\n30,100\n",
    )

    prepared = store.prepare_packet(run.run_id)

    assert prepared["state"] == "PACKET_READY"
    assert store.get_packet(run.run_id)["source_relevance"][0]["verdict"] == "limited"


def test_labelled_demo_data_keeps_its_provenance_in_a_draft(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    run = store.create_run()

    store.load_demo_data(run.run_id, FIXTURE)

    assert store.get_detail(run.run_id)["draft"]["dataset_provenance"] == "LABELLED_DEMO"


def test_labelled_demo_data_preserves_existing_measurement_context(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    run = store.create_run()
    methods = "Two-terminal resistance was recorded with fixed current and contact geometry."
    store.update_methods(run.run_id, methods)

    store.load_demo_data(run.run_id, FIXTURE)

    assert store.get_detail(run.run_id)["draft"]["methods"] == methods


def test_retrieved_candidates_require_a_complete_codex_adjudication_before_freezing(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    run = store.create_run()
    direct = SourceInput(
        id="openalex-direct",
        title="Four-point resistance measurement",
        authors=["Researcher"],
        year=2025,
        url_or_doi="https://doi.org/10.1/direct",
        locator=Locator(section="Abstract"),
        untrusted_content="Four-terminal voltage sensing reduces contact and lead contributions.",
    )
    contextual = SourceInput(
        id="openalex-context",
        title="Unrelated material overview",
        authors=["Researcher"],
        year=2025,
        url_or_doi="https://doi.org/10.1/context",
        locator=Locator(section="Abstract"),
        untrusted_content="A general overview of material processing.",
        retrieval_provider="arxiv",
        publication_status="preprint",
    )
    store.save_research_setup(
        run.run_id,
        ClaimInput(claim="Does a two-wire resistance sweep establish a bulk transition?"),
        [direct, contextual],
    )
    store.update_methods(run.run_id, "Two-terminal resistance was recorded during a temperature sweep.")
    store.update_dataset(run.run_id, b"temperature_c,two_wire_resistance_ohm\n20,120\n30,100\n")

    with pytest.raises(ValueError, match="Codex must adjudicate"):
        store.prepare_packet(run.run_id)

    with pytest.raises(ValueError, match="exactly once"):
        store.adjudicate_retrieved_sources(
            run.run_id,
            [SourceAdjudication(source_id=direct.id, verdict="direct", rationale="It describes the measurement control.")],
        )

    draft = store.adjudicate_retrieved_sources(
        run.run_id,
        [
            SourceAdjudication(source_id=direct.id, verdict="direct", rationale="It describes the measurement control."),
            SourceAdjudication(source_id=contextual.id, verdict="reject", rationale="It does not address the measurement or confound."),
        ],
    )
    assert draft["retrieval_review"]["status"] == "completed"
    assert draft["retrieval_review"]["provider"] == "OpenAlex + arXiv candidate retrieval"
    assert draft["retrieval_review"]["direct_source_ids"] == [direct.id]

    store.prepare_packet(run.run_id)
    packet = store.get_packet(run.run_id)
    assert [source["id"] for source in packet["sources"]] == [direct.id]
    assert packet["source_review"]["adjudications"] == [
        {"source_id": direct.id, "verdict": "direct", "rationale": "It describes the measurement control."}
    ]
    timeline = store.get_detail(run.run_id)["timeline"]
    assert [event["action"] for event in timeline][-2:] == [
        "sources_adjudicated",
        "evidence_packet_frozen",
    ]


def test_store_explores_a_draft_without_freezing_its_decision_boundary(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    run = store.create_fixture_run(FIXTURE)

    exploration = store.explore_draft(run.run_id)

    assert exploration["frozen"] is False
    assert exploration["dataset"]["row_count"] == 8
    assert exploration["source_relevance"][0]["verdict"] == "contextual"
    assert store.get_summary(run.run_id).state.value == "DRAFT"


def test_report_cannot_be_read_before_export(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    run = store.create_fixture_run(FIXTURE)

    with pytest.raises(ValueError, match="EXPORTED"):
        store.get_report(run.run_id)


def test_existing_report_is_read_with_the_conservative_verdict(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    run = store.create_fixture_run(FIXTURE)
    store.prepare_packet(run.run_id)
    store.inspect_sources(run.run_id, [{"expected_observation": "Four-terminal sensing reduces lead contribution.", "condition": "The source applies to the measurement configuration.", "falsifier": "The supplied source does not state this principle.", "evidence_ref_ids": ["src-four-wire-principle:evidence"]}])
    store.analyze_dataset(run.run_id)
    store.reconcile_findings(run.run_id, _findings())
    store.propose_control(run.run_id, _control())
    store.export_report(run.run_id)
    report_path = tmp_path / "runs" / run.run_id / "report" / "report.json"
    payload = store._read(report_path)
    payload.pop("verdict")
    payload.pop("source_relevance")
    store._write(report_path, payload)

    report = store.get_report(run.run_id)

    assert report.verdict.label == "MECHANISM_NOT_ESTABLISHED"
    assert report.source_relevance == []
