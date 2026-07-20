from __future__ import annotations

from typing import Iterable

from .models import (
    AlignmentAdjudication,
    ConvergenceMap,
    DatasetAnalysis,
    EvidenceRef,
    Report,
    RequiredSignature,
    now_iso,
)


def default_signatures(
    claim: str,
    *,
    theory_evidence_ref_ids: list[str] | None = None,
) -> list[RequiredSignature]:
    """Return the narrow transport fixture's conservative signature set.

    Codex can replace these with claim-specific signatures. The defaults make a
    newly uploaded run legible immediately without pretending that a generic
    temperature trend proves a mechanism-specific transition.
    """

    refs = theory_evidence_ref_ids or []
    return [
        RequiredSignature(
            id="signature-response",
            name="Response",
            requirement="The supplied measurement contains the response named by the claim.",
            expected_observation="Resistance decreases across the recorded temperature sweep.",
            falsifying_outcome="The trace is flat or moves in the opposite direction.",
            theory_evidence_ref_ids=refs,
        ),
        RequiredSignature(
            id="signature-localization",
            name="Localization",
            requirement="The response must be attributable to the sample rather than the measurement path.",
            expected_observation="The decrease remains after contact and lead contributions are excluded.",
            falsifying_outcome="The decrease weakens or disappears when sensing topology isolates the sample.",
            theory_evidence_ref_ids=refs,
        ),
        RequiredSignature(
            id="signature-specificity",
            name="Specificity",
            requirement="A mechanism-specific signature must be present beyond generic temperature dependence.",
            expected_observation="A predeclared transition signature appears in the measured observables.",
            falsifying_outcome="Only a generic monotonic trend is present; no transition-specific observable was measured.",
            theory_evidence_ref_ids=refs,
        ),
    ]


def preview_map(
    claim: str,
    measurement_method: str,
    dataset: DatasetAnalysis,
    data_ref_id: str,
    source_ref_ids: list[str] | None = None,
) -> ConvergenceMap:
    """Build a deterministic, explicitly provisional map for an editable run."""

    source_refs = source_ref_ids or []
    four_wire = any(
        token in measurement_method.lower()
        for token in ("four-wire", "four wire", "four-terminal", "four terminal", "4-wire", "4 wire")
    )
    response_status = "Observed" if dataset.change_ohm < 0 else "Contradicted"
    response_reason = (
        f"The frozen CSV records {dataset.first_resistance_ohm:g} Ω → "
        f"{dataset.last_resistance_ohm:g} Ω ({dataset.percent_change:+.1f}%)."
        if response_status == "Observed"
        else "The frozen CSV does not contain the claimed resistance decrease."
    )
    localization_status = "Observed" if four_wire else "Confounded"
    localization_reason = (
        "Four-terminal sensing localizes the sensed voltage drop to the sample path."
        if four_wire
        else "Two-wire resistance is a total loop measurement; sample, contact, and lead contributions are not separable."
    )
    alignments = [
        AlignmentAdjudication(
            signature_id="signature-response",
            status=response_status,
            rationale=response_reason,
            evidence_ref_ids=[data_ref_id],
        ),
        AlignmentAdjudication(
            signature_id="signature-localization",
            status=localization_status,
            rationale=localization_reason,
            evidence_ref_ids=[data_ref_id, *source_refs],
            alternative_explanation=None if four_wire else "Temperature-dependent contact or lead resistance can produce the same two-wire trend.",
        ),
        AlignmentAdjudication(
            signature_id="signature-specificity",
            status="Missing",
            rationale="Onset, discontinuity, hysteresis, scaling, or another transition-specific observable is not specified in the current packet.",
            missing_reason="not_measured",
        ),
    ]
    return ConvergenceMap(
        claim=claim,
        measurement_method=measurement_method,
        signatures=default_signatures(claim, theory_evidence_ref_ids=source_refs[:1]),
        alignments=alignments,
        dominant_gap="The measurement shows a real response, but its sample origin is not identifiable from this method.",
        freeze_status="DRAFT",
        recorded_at=now_iso(),
    )


def legacy_projection(report: Report) -> ConvergenceMap:
    """Project a pre-Convergence-Map report into the current visual contract."""

    findings = {finding.status: finding for finding in report.findings}
    response = findings.get("Observed")
    inferred = findings.get("Inferred")
    unresolved = findings.get("Unresolved")
    established = findings.get("Established")
    signatures = default_signatures(
        report.claim,
        theory_evidence_ref_ids=established.evidence_ref_ids if established else [],
    )
    alignments = [
        AlignmentAdjudication(
            signature_id="signature-response",
            status="Observed" if response else "Missing",
            rationale=response.reasoning if response else "No deterministic response finding was recorded.",
            evidence_ref_ids=response.evidence_ref_ids if response else [],
        ),
        AlignmentAdjudication(
            signature_id="signature-localization",
            status="Confounded" if inferred else "Missing",
            rationale=inferred.reasoning if inferred else "No localization adjudication was recorded.",
            evidence_ref_ids=inferred.evidence_ref_ids if inferred else [],
            alternative_explanation=inferred.alternative_explanation if inferred else None,
        ),
        AlignmentAdjudication(
            signature_id="signature-specificity",
            status="Missing" if unresolved else "Confounded",
            rationale=unresolved.reasoning if unresolved else "The legacy report did not record a transition-specific signature.",
            evidence_ref_ids=unresolved.evidence_ref_ids if unresolved else [],
            missing_reason="not_measured" if unresolved else None,
        ),
    ]
    control = report.control
    if control:
        control = control.model_copy(
            update={
                "closes_signature_ids": control.closes_signature_ids or ["signature-localization"],
                "leaves_open_signature_ids": control.leaves_open_signature_ids or ["signature-specificity"],
            }
        )
    return ConvergenceMap(
        claim=report.claim,
        measurement_method="Two-wire resistance–temperature sweep",
        signatures=signatures,
        alignments=alignments,
        dominant_gap=report.verdict.reason,
        control=control,
        freeze_status="FROZEN",
        recorded_at=report.exported_at,
    )


def validate_alignment_records(
    signatures: list[RequiredSignature],
    alignments: list[AlignmentAdjudication],
    refs: Iterable[EvidenceRef],
) -> list[AlignmentAdjudication]:
    signature_ids = [item.id for item in signatures]
    if len(signature_ids) != len(set(signature_ids)):
        raise ValueError("required signatures must have unique ids")
    alignment_ids = [item.signature_id for item in alignments]
    if set(alignment_ids) != set(signature_ids) or len(alignment_ids) != len(signature_ids):
        raise ValueError("alignment adjudications must cover every required signature exactly once")
    known_refs = {ref.id: ref for ref in refs}
    for item in alignments:
        if any(ref_id not in known_refs for ref_id in item.evidence_ref_ids):
            raise ValueError(f"{item.signature_id} references unsupported evidence")
        linked = [known_refs[ref_id] for ref_id in item.evidence_ref_ids]
        if item.status in ("Observed", "Contradicted") and not any(ref.kind == "data" for ref in linked):
            raise ValueError(f"{item.status} alignment requires data evidence")
        if item.status == "Confounded":
            if not item.alternative_explanation:
                raise ValueError("Confounded alignment requires a named alternative explanation")
            if not item.evidence_ref_ids:
                raise ValueError("Confounded alignment requires evidence")
        if item.status == "Missing" and not item.missing_reason:
            raise ValueError("Missing alignment requires a missing_reason")
    return alignments
