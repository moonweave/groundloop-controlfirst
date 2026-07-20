from pathlib import Path

from packages.core.models import (
    AlignmentAdjudication,
    ClaimInput,
    ControlProposal,
    RequiredSignature,
    SourceAdjudication,
    SourceInput,
)
from packages.core.store import RunStore


FIXTURE = Path(__file__).parents[1] / "fixtures" / "four_wire_contact_control"


def _source(source_id: str, title: str, excerpt: str) -> SourceInput:
    return SourceInput(
        id=source_id,
        title=title,
        authors=["Test Lab"],
        year=2026,
        url_or_doi=f"https://example.invalid/{source_id}",
        locator={"section": "Abstract"},
        untrusted_content=excerpt,
    )


def test_convergence_contract_round_trips_from_codex_to_export(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    source = _source(
        "src-method-limit",
        "Two-wire and four-wire resistance",
        "Four-wire sensing separates voltage measurement from current delivery and reduces lead and contact contributions.",
    )
    detail = store.create_codex_run(
        ClaimInput(claim="A two-wire resistance decrease demonstrates a bulk transition."),
        "Two-wire resistance was recorded during a temperature sweep with fixed current and mounting.",
        (FIXTURE / "dataset.csv").read_bytes(),
        [source],
    )
    run_id = detail["run"]["run_id"]

    store.record_source_reviews(
        run_id,
        [SourceAdjudication(source_id=source.id, verdict="direct", role="method_limit", rationale="The excerpt states the measurement limitation.")],
    )
    store.prepare_packet(run_id)
    store.inspect_sources(
        run_id,
        [{
            "expected_observation": "The method cannot isolate contact and lead contributions.",
            "condition": "The supplied excerpt is the only source boundary.",
            "falsifier": "The excerpt does not describe two-wire limitations.",
            "evidence_ref_ids": [f"{source.id}:evidence"],
        }],
    )
    store.analyze_dataset(run_id)
    signatures = [
        RequiredSignature(
            id="signature-response",
            name="Response",
            requirement="The trace contains the claimed decrease.",
            expected_observation="Resistance decreases across temperature.",
            falsifying_outcome="The trace is flat or rises.",
            theory_evidence_ref_ids=[f"{source.id}:evidence"],
        ),
        RequiredSignature(
            id="signature-localization",
            name="Localization",
            requirement="The response belongs to the sample.",
            expected_observation="The response persists after contact and lead contributions are excluded.",
            falsifying_outcome="The response disappears in four-wire mode.",
            theory_evidence_ref_ids=[f"{source.id}:evidence"],
        ),
        RequiredSignature(
            id="signature-specificity",
            name="Specificity",
            requirement="A transition-specific signature is measured.",
            expected_observation="A predeclared transition signature is present.",
            falsifying_outcome="Only a generic monotonic trend is present.",
        ),
    ]
    store.record_signatures(run_id, signatures)
    store.record_alignments(
        run_id,
        [
            AlignmentAdjudication(signature_id="signature-response", status="Observed", rationale="The deterministic trace decreases.", evidence_ref_ids=["data-001:rows-2-9"]),
            AlignmentAdjudication(signature_id="signature-localization", status="Confounded", rationale="Two-wire total resistance cannot locate the change.", evidence_ref_ids=["data-001:rows-2-9", f"{source.id}:evidence"], alternative_explanation="Temperature-dependent contact resistance can produce the same trace."),
            AlignmentAdjudication(signature_id="signature-specificity", status="Missing", rationale="No transition-specific observable is in the packet.", missing_reason="not_measured"),
        ],
    )
    store.record_control_contract(
        run_id,
        ControlProposal(
            confound="Contact and lead contribution",
            experiment="Repeat the same sweep in four-wire mode.",
            preconditions=["Same sample", "Same current", "Same mounting", "Same temperature program"],
            outcomes=[
                {"if": "The decrease persists", "then": "Sample-intrinsic R(T) gains support."},
                {"if": "The decrease weakens", "then": "Contact contribution is supported."},
            ],
            signature_ref_ids=["signature-localization"],
            closes_signature_ids=["signature-localization"],
            leaves_open_signature_ids=["signature-specificity"],
            priority="high",
            feasibility="One matched sweep.",
        ),
    )

    report = store.export_report(run_id)
    assert report.convergence is not None
    assert [item.status for item in report.convergence.alignments] == ["Observed", "Confounded", "Missing"]
    assert report.convergence.control is not None
    assert report.convergence.control.closes_signature_ids == ["signature-localization"]
    assert report.verdict.label == "MECHANISM_NOT_ESTABLISHED"

    markdown = store.get_report_markdown(run_id)
    assert "## Convergence Map" in markdown
    assert "### Required signatures" in markdown
    assert "`signature-response`" in markdown
    assert "Expected observation: Resistance decreases across temperature." in markdown
    assert "### Signature alignments" in markdown
    assert "`signature-localization` — **Confounded**" in markdown
    assert "Alternative explanation: Temperature-dependent contact resistance can produce the same trace." in markdown
    assert "### Dominant gap" in markdown
    assert report.convergence.dominant_gap in markdown
    assert "### Source roles" in markdown
    assert "`src-method-limit` — **method limit** (direct)" in markdown
    assert "### Control contract" in markdown
    assert "Closes signatures: signature-localization" in markdown
    assert "Leaves open signatures: signature-specificity" in markdown
    assert "If The decrease persists, then Sample-intrinsic R(T) gains support." in markdown


def test_draft_projection_makes_deterministic_gap_visible(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    detail = store.create_codex_run(
        ClaimInput(claim="A two-wire resistance decrease demonstrates a bulk transition."),
        "Two-wire resistance was recorded during a temperature sweep with fixed current and mounting.",
        (FIXTURE / "dataset.csv").read_bytes(),
    )
    projection = store.get_convergence_map(detail["run"]["run_id"])
    assert projection.freeze_status == "DRAFT"
    assert [item.status for item in projection.alignments] == ["Observed", "Confounded", "Missing"]
