from pathlib import Path

import pytest

from packages.core.models import ControlProposal, Finding
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
    assert {item.verdict for item in report.source_relevance} == {"contextual"}
    assert store.get_summary(run.run_id).state.value == "EXPORTED"
    markdown = store.get_report_markdown(run.run_id)
    assert "MECHANISM NOT ESTABLISHED" in markdown
    assert "### Established" in markdown
    assert "## ControlFirst" in markdown
    assert "src-four-wire-principle" in markdown


def test_store_rejects_path_like_run_id(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    with pytest.raises(ValueError, match="invalid run id"):
        store.get_summary("../../etc")


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
