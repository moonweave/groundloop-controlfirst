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
CYCLIC_TRACE = b"potential_v,current_ua,direction\n-0.40,0.2,forward\n-0.20,0.4,forward\n0.00,1.2,forward\n0.15,4.8,forward\n0.30,2.0,forward\n0.45,0.8,forward\n0.60,0.3,forward\n0.45,-0.4,reverse\n0.30,-1.6,reverse\n0.15,-3.9,reverse\n0.00,-1.0,reverse\n-0.15,-0.3,reverse\n-0.30,-0.1,reverse\n"
IV_TRAP_SWEEP = b"voltage_v,current_a\n0.2,4.554603e-11\n0.3,1.183316e-10\n0.5,3.917102e-10\n0.8,1.184055e-09\n1.2,3.068870e-09\n1.8,7.954893e-09\n2.5,1.722466e-08\n3.5,3.795740e-08\n5.0,8.800754e-08\n7.0,1.932585e-07\n10.0,4.477442e-07\n"
GROUPED_TRAP_DENSITY = b"sample_id,condition,trap_density_cm3\nc1,control,1.2e16\nc2,control,1.1e16\nc3,control,1.3e16\nt1,treated,7.0e15\nt2,treated,8.0e15\nt3,treated,7.5e15\n"
IMPEDANCE_RESPONSE = b"frequency_hz,z_abs_ohm,phase_deg\n1,820,-78\n3,760,-75\n10,690,-70\n100,310,-42\n1000,155,-18\n10000,128,-7\n100000,121,-3\n"


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


def _iv_literature_candidate(source_id: str, title: str, excerpt: str, role_query: str) -> LiteratureCandidate:
    return LiteratureCandidate(
        id=source_id,
        title=title,
        authors=["Test Lab"],
        year=2024,
        url_or_doi=f"https://example.invalid/{source_id}",
        retrieval_provider="codex-web-search",
        publication_status="peer_reviewed",
        excerpt=excerpt,
        locator={"section": "bounded excerpt"},
        retrieved_at="2026-07-21T00:00:00+00:00",
        search_query=role_query,
        discovery_rationale="Codex found this source while checking whether a single I-V sweep can identify trap-limited conduction.",
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
            required_artifact_labels=["temperature series"],
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
    assert markdown.index("- Required follow-up artifacts:") < markdown.index("- Outcomes:")
    assert "two-wire" not in markdown.lower()


def test_local_peak_materializes_pl_peak_without_treating_any_maximum_as_peak(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    run_id, _ = _complete_to_analysis(store)

    peak = store.materialize_data_evidence(
        run_id,
        "local_peak",
        ["col-001", "col-002"],
        2,
        6,
        {"target_x": 620, "x_tolerance": 2, "minimum_prominence_fraction": 0.2},
    )

    assert peak["result"]["peak_count"] == 1
    assert peak["result"]["target_observed"] is True
    assert peak["result"]["target_peak"]["x"] == 620
    assert peak["result"]["target_peak"]["prominence"] == 46
    assert "strict local peak" in peak["fact_text"]

    monotonic = b"wavelength_nm,intensity_counts\n580,12\n600,28\n620,45\n640,65\n"
    detail = store.create_generic_run(
        ClaimInput(claim="A monotonic PL spectrum contains a defect peak near 620 nm."),
        "Steady-state photoluminescence was exported as wavelength and intensity values under fixed excitation.",
        monotonic,
        [_source()],
        filename="monotonic-pl.csv",
    )
    monotonic_run = detail["run"]["run_id"]
    store.record_measurement_modality(monotonic_run, _codex_spectrum_proposal())
    store.set_dataset_binding(
        monotonic_run,
        DatasetBinding(artifact_id="artifact-001", x_column_id="col-001", y_column_ids=["col-002"], confirmed_at="2026-07-21T00:00:00+00:00"),
        "generic_spectrum",
    )
    store.record_source_reviews(monotonic_run, [SourceAdjudication(source_id="src-spectrum-limit", verdict="direct", role="method_limit", rationale="The supplied source limits peak assignment from a steady-state spectrum.")])
    store.prepare_packet(monotonic_run)
    store.inspect_sources(monotonic_run, [{"expected_observation": "peak assignment is limited", "condition": "source excerpt is frozen", "falsifier": "excerpt does not describe the limitation", "evidence_ref_ids": ["src-spectrum-limit:evidence"]}])
    store.analyze_dataset(monotonic_run)

    no_peak = store.materialize_data_evidence(
        monotonic_run,
        "local_peak",
        ["col-001", "col-002"],
        2,
        5,
        {"target_x": 620, "x_tolerance": 2},
    )

    assert no_peak["result"]["peak_count"] == 0
    assert no_peak["result"]["target_observed"] is False
    assert "no strict local peak" in no_peak["fact_text"]


def test_generic_iv_trap_scenario_keeps_mechanism_confounded(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    detail = store.create_generic_run(
        ClaimInput(claim="An amorphous material's charge-trap behavior is established by a single I-V curve."),
        "Two-terminal dark I-V sweep on an amorphous thin-film device at room temperature. Device thickness, electrode injection barrier, temperature dependence, area scaling, and illumination history were not varied.",
        IV_TRAP_SWEEP,
        [],
        filename="amorphous_iv_trap_candidate.csv",
    )
    run_id = detail["run"]["run_id"]
    store.import_literature_candidates(
        run_id,
        [
            _iv_literature_candidate(
                "src-iv-theory",
                "Trap-limited space-charge current theory",
                "Trap-filled-limit behavior can produce a steep current rise under idealized contact assumptions.",
                "trap filled limit space charge limited current I-V",
            ),
            _iv_literature_candidate(
                "src-iv-method-limit",
                "SCLC measurement reporting limits",
                "SCLC interpretation requires careful control of thickness, temperature, contacts, and reporting practice.",
                "SCLC thickness temperature contact control reporting",
            ),
        ],
    )
    store.record_measurement_modality(
        run_id,
        MeasurementModalityProposal(
            candidate="generic_sweep",
            confidence="medium",
            reasons=["The artifact is a two-terminal voltage-current sweep; headers alone do not identify trap physics."],
            alternatives=["unknown"],
            authority="codex",
        ),
    )
    store.set_artifact_binding(
        run_id,
        DatasetBinding(
            artifact_id="artifact-001",
            x_column_id="col-001",
            y_column_ids=["col-002"],
            confirmed_units={"col-001": "V", "col-002": "A"},
            confirmed_at="2026-07-21T00:00:00+00:00",
        ),
        "generic",
    )
    store.record_source_reviews(
        run_id,
        [
            SourceAdjudication(source_id="src-iv-theory", verdict="direct", role="theory_basis", rationale="The excerpt makes superlinear I-V relevant but assumes a contact boundary."),
            SourceAdjudication(source_id="src-iv-method-limit", verdict="direct", role="method_limit", rationale="The excerpt limits mechanism assignment from a single room-temperature I-V sweep."),
        ],
    )
    store.prepare_packet(run_id)
    store.inspect_sources(
        run_id,
        [
            {
                "expected_observation": "Trap-limited conduction can produce superlinear I-V behavior.",
                "condition": "Only the bounded excerpts are in the source boundary.",
                "falsifier": "The excerpt does not connect trap physics to I-V shape.",
                "evidence_ref_ids": ["src-iv-theory:evidence"],
            },
            {
                "expected_observation": "Single-device I-V remains method-limited without thickness, temperature, or contact controls.",
                "condition": "The supplied method records no control variation.",
                "falsifier": "The source says single I-V alone is sufficient.",
                "evidence_ref_ids": ["src-iv-method-limit:evidence"],
            },
        ],
    )
    store.analyze_dataset(run_id)
    delta = store.materialize_data_evidence(run_id, "endpoint_delta", ["col-001", "col-002"], 2, 12)
    slope = store.materialize_data_evidence(run_id, "power_law_fit", ["col-001", "col-002"], 2, 12)
    monotonicity = store.materialize_data_evidence(run_id, "monotonicity", ["col-001", "col-002"], 2, 12)
    assert slope["result"]["exponent"] > 2
    assert slope["result"]["r_squared"] > 0.99
    store.record_signatures(
        run_id,
        [
            RequiredSignature(id="signature-superlinear-iv", name="Superlinear I-V response", requirement="Trap-limited conduction should produce non-ohmic current growth over a relevant voltage range.", expected_observation="Log current versus log voltage has a slope substantially above 1 and current rises monotonically.", falsifying_outcome="The I-V curve is ohmic or current does not rise with voltage.", theory_evidence_ref_ids=["src-iv-theory:evidence"]),
            RequiredSignature(id="signature-trap-specificity", name="Trap-specific mechanism", requirement="The I-V shape must be distinguishable from injection-limited, contact-limited, heating, or percolation alternatives.", expected_observation="A discriminator such as temperature, thickness, electrode, or illumination dependence separates trap physics from alternatives.", falsifying_outcome="The same shape is compatible with non-trap alternatives.", theory_evidence_ref_ids=["src-iv-method-limit:evidence"]),
            RequiredSignature(id="signature-tfl-threshold", name="Trap-filled-limit threshold", requirement="A trap-filled-limit interpretation requires a reproducible threshold or regime transition tied to device/material parameters.", expected_observation="A threshold/regime boundary is measured and compared across device thickness or temperature.", falsifying_outcome="Only one smooth I-V sweep is recorded without control variation.", theory_evidence_ref_ids=["src-iv-theory:evidence", "src-iv-method-limit:evidence"]),
        ],
    )
    convergence = store.record_alignments(
        run_id,
        [
            AlignmentAdjudication(signature_id="signature-superlinear-iv", status="Observed", rationale="GroundLoop materialized monotonic current increase and an OLS log-log slope above 1 from the supplied I-V artifact.", evidence_ref_ids=[delta["evidence_id"], slope["evidence_id"], monotonicity["evidence_id"]]),
            AlignmentAdjudication(signature_id="signature-trap-specificity", status="Confounded", rationale="The I-V shape is compatible with trap-limited conduction, but the method does not separate injection, contact, heating, or percolation alternatives.", evidence_ref_ids=[slope["evidence_id"], "method-evidence-frozen", "src-iv-method-limit:evidence"], alternative_explanation="Injection-limited current, contact barriers, self-heating, or percolative transport can also yield nonlinear I-V behavior."),
            AlignmentAdjudication(signature_id="signature-tfl-threshold", status="Missing", rationale="The artifact records one smooth I-V sweep and does not vary thickness, temperature, electrode, or repeated threshold conditions.", evidence_ref_ids=["src-iv-theory:evidence", "src-iv-method-limit:evidence"], missing_reason="not_measured"),
        ],
    )
    assert [(item["signature_id"], item["status"]) for item in convergence["alignments"]] == [
        ("signature-superlinear-iv", "Observed"),
        ("signature-trap-specificity", "Confounded"),
        ("signature-tfl-threshold", "Missing"),
    ]
    store.record_control_contract(
        run_id,
        ControlProposal(
            confound="Nonlinear I-V caused by injection/contact or geometry effects rather than bulk trap-limited conduction.",
            experiment="Repeat the I-V sweep on matched devices with at least two film thicknesses while holding electrode material, area, sweep rate, temperature, and illumination history fixed.",
            preconditions=["same material batch", "same electrode stack", "same area", "same sweep rate", "same temperature"],
            outcomes=[
                {"if": "the regime boundary shifts systematically with thickness while the extracted slope remains consistent", "then": "the trap-limited interpretation gains support for the specificity signature."},
                {"if": "the nonlinearity does not scale with thickness or changes with contacts", "then": "injection/contact or geometry effects remain the dominant explanation."},
            ],
            signature_ref_ids=["signature-trap-specificity", "signature-tfl-threshold"],
            closes_signature_ids=["signature-tfl-threshold"],
            leaves_open_signature_ids=["signature-trap-specificity"],
            required_artifact_labels=["matched thickness-series I-V artifact"],
            priority="high",
            feasibility="Requires matched devices or existing thickness-series measurements.",
        ),
    )
    report = store.export_report(run_id)
    markdown = store.get_report_markdown(run_id)
    assert report["verdict"]["label"] == "NOT_ESTABLISHED"
    assert report["convergence"]["dominant_gap"].startswith("Trap-specific mechanism is confounded")
    assert "amorphous_iv_trap_candidate.csv" in markdown
    assert "src-iv-method-limit" in markdown
    assert "## Control contract" in markdown


def test_power_law_fit_rejects_nonpositive_selected_range(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    source = SourceInput(
        id="src-power-law-limit",
        title="Power-law fitting boundary",
        authors=["Test Lab"],
        year=2026,
        url_or_doi="https://example.invalid/power-law",
        locator={"section": "Methods"},
        untrusted_content="A power-law fit on log-transformed variables requires a positive selected range.",
    )
    detail = store.create_generic_run(
        ClaimInput(claim="A signed I-V curve establishes a power-law conduction mechanism."),
        "Two-terminal I-V sweep crossing zero current and voltage.",
        b"voltage_v,current_a\n-1,-2e-9\n0,0\n1,2e-9\n2,8e-9\n",
        [source],
        filename="signed_iv.csv",
    )
    run_id = detail["run"]["run_id"]
    store.set_artifact_binding(
        run_id,
        DatasetBinding(artifact_id="artifact-001", x_column_id="col-001", y_column_ids=["col-002"], confirmed_units={"col-001": "V", "col-002": "A"}, confirmed_at="2026-07-21T00:00:00+00:00"),
        "generic",
    )
    store.record_source_reviews(run_id, [SourceAdjudication(source_id="src-power-law-limit", verdict="direct", role="method_limit", rationale="The source limits power-law fitting to positive selected ranges.")])
    store.prepare_packet(run_id)
    store.inspect_sources(
        run_id,
        [{
            "expected_observation": "Power-law fitting requires a positive selected range.",
            "condition": "The selected rows include zero or negative values.",
            "falsifier": "The selected rows are all positive.",
            "evidence_ref_ids": ["src-power-law-limit:evidence"],
        }],
    )
    store.analyze_dataset(run_id)
    with pytest.raises(ValueError, match="positive row range"):
        store.materialize_data_evidence(run_id, "power_law_fit", ["col-001", "col-002"], 2, 5)
    evidence = store.materialize_data_evidence(run_id, "power_law_fit", ["col-001", "col-002"], 4, 5)
    assert evidence["result"]["exponent"] == pytest.approx(2)
    assert evidence["result"]["r_squared"] == pytest.approx(1)


def test_grouped_extrema_materializes_forward_reverse_peaks_without_codex_arithmetic(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    detail = store.create_generic_run(
        ClaimInput(claim="A single cyclic trace establishes a reversible surface-confined mechanism."),
        "A three-electrode cyclic trace contains potential, current, and forward/reverse direction. Only one scan rate was measured.",
        CYCLIC_TRACE,
        [_source()],
        filename="cyclic-trace.csv",
    )
    run_id = detail["run"]["run_id"]
    store.record_measurement_modality(
        run_id,
        MeasurementModalityProposal(
            candidate="generic_cyclic_trace",
            confidence="high",
            reasons=["Potential/current columns and a direction group describe a cyclic trace."],
            authority="codex",
        ),
    )
    store.set_dataset_binding(
        run_id,
        DatasetBinding(artifact_id="artifact-001", x_column_id="col-001", y_column_ids=["col-002"], group_column_id="col-003", confirmed_at="2026-07-21T00:00:00+00:00"),
        "generic_cyclic_trace",
    )
    store.record_source_reviews(
        run_id,
        [SourceAdjudication(source_id="src-spectrum-limit", verdict="direct", role="method_limit", rationale="The supplied source limits mechanism assignment from a single trace.")],
    )
    store.prepare_packet(run_id)
    store.inspect_sources(run_id, [{"expected_observation": "A single trace does not establish the mechanism.", "condition": "Only the bounded excerpt is frozen.", "falsifier": "The excerpt does not state the limitation.", "evidence_ref_ids": ["src-spectrum-limit:evidence"]}])
    store.analyze_dataset(run_id)
    evidence = store.materialize_data_evidence(run_id, "grouped_extrema", ["col-003", "col-001", "col-002"], 2, 14)
    assert evidence["result"]["forward"]["max"] == {"x": 0.15, "y": 4.8}
    assert evidence["result"]["reverse"]["min"] == {"x": 0.15, "y": -3.9}
    assert evidence["artifact_id"] == "artifact-001"


def test_grouped_comparison_keeps_treatment_mechanism_confounded(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    source = SourceInput(
        id="src-group-limit",
        title="Grouped device-comparison limits",
        authors=["Test Lab"],
        year=2026,
        url_or_doi="https://example.invalid/grouped-comparison",
        locator={"section": "Methods"},
        untrusted_content="A treated-versus-control difference can support a response comparison, but mechanism assignment requires matched devices, batch controls, and an independent discriminator.",
        retrieval_provider="manual",
        publication_status="unknown",
    )
    detail = store.create_generic_run(
        ClaimInput(claim="A surface treatment lowers trap density in the amorphous device material."),
        "Trap density estimates were exported for three control devices and three treated devices. The method did not record batch randomization, thickness matching, electrode contact checks, or an independent trap-specific measurement.",
        GROUPED_TRAP_DENSITY,
        [source],
        filename="grouped-trap-density.csv",
    )
    run_id = detail["run"]["run_id"]
    store.record_measurement_modality(
        run_id,
        MeasurementModalityProposal(
            candidate="grouped_comparison",
            confidence="high",
            reasons=["The artifact contains condition labels and trap-density estimates for control and treated groups."],
            authority="codex",
        ),
    )
    store.set_dataset_binding(
        run_id,
        DatasetBinding(
            artifact_id="artifact-001",
            x_column_id="col-001",
            y_column_ids=["col-003"],
            group_column_id="col-002",
            confirmed_units={"col-003": "cm^-3"},
            confirmed_at="2026-07-21T00:00:00+00:00",
        ),
        "generic",
    )
    store.record_source_reviews(run_id, [SourceAdjudication(source_id="src-group-limit", verdict="direct", role="method_limit", rationale="The excerpt permits grouped response comparison but limits mechanism assignment.")])
    store.prepare_packet(run_id)
    store.inspect_sources(run_id, [{"expected_observation": "Grouped response comparison does not establish mechanism by itself.", "condition": "Only the bounded excerpt is frozen.", "falsifier": "The excerpt says treated-versus-control means prove the mechanism.", "evidence_ref_ids": ["src-group-limit:evidence"]}])
    store.analyze_dataset(run_id)
    comparison = store.materialize_data_evidence(
        run_id,
        "group_comparison",
        ["col-002", "col-003"],
        2,
        7,
        {"reference_group": "control", "comparison_group": "treated"},
    )
    assert comparison["result"]["reference"]["count"] == 3
    assert comparison["result"]["comparison"]["mean"] == pytest.approx(7.5e15)
    assert comparison["result"]["delta_mean"] == pytest.approx(-4.5e15)
    assert comparison["result"]["percent_change"] == pytest.approx(-37.5)
    store.record_signatures(
        run_id,
        [
            RequiredSignature(id="signature-group-response", name="Grouped response", requirement="Treated devices should show lower measured trap-density estimates than controls.", expected_observation="The treated mean is lower than the control mean.", falsifying_outcome="The treated mean is equal to or above the control mean.", theory_evidence_ref_ids=["src-group-limit:evidence"]),
            RequiredSignature(id="signature-treatment-attribution", name="Treatment attribution", requirement="The lower estimate must be attributable to treatment rather than batch, thickness, contact, or extraction artifacts.", expected_observation="Matched design and independent checks separate treatment from alternatives.", falsifying_outcome="Batch/device/method alternatives remain compatible.", theory_evidence_ref_ids=["src-group-limit:evidence"]),
            RequiredSignature(id="signature-independent-discriminator", name="Independent discriminator", requirement="A trap-specific independent measurement must corroborate the extracted density change.", expected_observation="A separate trap-sensitive artifact changes consistently with the extracted density.", falsifying_outcome="Only the grouped estimate table is present.", theory_evidence_ref_ids=["src-group-limit:evidence"]),
        ],
    )
    convergence = store.record_alignments(
        run_id,
        [
            AlignmentAdjudication(signature_id="signature-group-response", status="Observed", rationale="GroundLoop materialized a lower treated group mean relative to the control group.", evidence_ref_ids=[comparison["evidence_id"]]),
            AlignmentAdjudication(signature_id="signature-treatment-attribution", status="Confounded", rationale="The grouped difference is real within the artifact, but the method does not separate treatment from batch, device geometry, contact, or extraction alternatives.", evidence_ref_ids=[comparison["evidence_id"], "method-evidence-frozen", "src-group-limit:evidence"], alternative_explanation="Batch variation, unmatched thickness, contact differences, or extraction-model artifacts can produce the same group mean difference."),
            AlignmentAdjudication(signature_id="signature-independent-discriminator", status="Missing", rationale="The Run contains no independent trap-sensitive artifact such as temperature-dependent I-V, DLTS-like spectroscopy, or matched impedance evidence.", missing_reason="not_measured"),
        ],
    )
    assert convergence["dominant_gap"].startswith("Treatment attribution is confounded")
    store.record_control_contract(
        run_id,
        ControlProposal(
            confound="Treatment effect is not separated from batch/device/method artifacts.",
            experiment="Repeat the grouped comparison with randomized matched control and treated devices from the same batch, then add one independent trap-sensitive measurement on the same devices.",
            preconditions=["same material batch", "matched thickness", "same electrode stack", "same extraction model"],
            outcomes=[
                {"if": "the treated group remains lower and the independent trap-sensitive artifact shifts consistently", "then": "treatment attribution gains bounded support."},
                {"if": "the group difference disappears or the independent artifact does not shift consistently", "then": "batch/device/method artifacts remain the dominant explanation."},
            ],
            signature_ref_ids=["signature-treatment-attribution", "signature-independent-discriminator"],
            closes_signature_ids=["signature-independent-discriminator"],
            leaves_open_signature_ids=["signature-treatment-attribution"],
            required_artifact_labels=["matched randomized grouped table", "independent trap-sensitive control"],
            priority="high",
            feasibility="Requires a matched repeat or existing replicate/control artifacts.",
        ),
    )
    report = store.export_report(run_id)
    markdown = store.get_report_markdown(run_id)
    assert report["verdict"]["label"] == "NOT_ESTABLISHED"
    assert "grouped-trap-density.csv" in markdown
    assert "Treatment attribution is confounded" in markdown


def test_group_comparison_requires_explicit_group_roles(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    detail = store.create_generic_run(
        ClaimInput(claim="A treatment changes a grouped measurement."),
        "Grouped measurements were exported without enough context to choose a reference group automatically.",
        GROUPED_TRAP_DENSITY,
        [_source()],
        filename="grouped-trap-density.csv",
    )
    run_id = detail["run"]["run_id"]
    store.set_dataset_binding(
        run_id,
        DatasetBinding(artifact_id="artifact-001", x_column_id="col-001", y_column_ids=["col-003"], group_column_id="col-002", confirmed_at="2026-07-21T00:00:00+00:00"),
        "generic",
    )
    store.record_source_reviews(run_id, [SourceAdjudication(source_id="src-spectrum-limit", verdict="direct", role="method_limit", rationale="The source limits mechanism assignment.")])
    store.prepare_packet(run_id)
    store.inspect_sources(run_id, [{"expected_observation": "assignment is limited", "condition": "source excerpt is frozen", "falsifier": "excerpt does not describe a limitation", "evidence_ref_ids": ["src-spectrum-limit:evidence"]}])
    store.analyze_dataset(run_id)
    with pytest.raises(ValueError, match="reference_group and comparison_group"):
        store.materialize_data_evidence(run_id, "group_comparison", ["col-002", "col-003"], 2, 7)


def test_impedance_band_comparison_keeps_bulk_transport_confounded(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    source = SourceInput(
        id="src-impedance-limit",
        title="Impedance attribution limits",
        authors=["Test Lab"],
        year=2026,
        url_or_doi="https://example.invalid/impedance-limit",
        locator={"section": "Methods"},
        untrusted_content="Low-frequency impedance dispersion can arise from electrode polarization, interfaces, blocking contacts, or bulk ion transport; attribution requires geometry, electrode, temperature, or equivalent-circuit controls.",
        retrieval_provider="manual",
        publication_status="unknown",
    )
    detail = store.create_generic_run(
        ClaimInput(claim="The low-frequency impedance response identifies bulk ion transport in the amorphous material."),
        "Two-electrode impedance magnitude and phase were measured across frequency at room temperature. Electrode material, sample thickness, temperature, and equivalent-circuit fits were not varied.",
        IMPEDANCE_RESPONSE,
        [source],
        filename="impedance-frequency-response.csv",
    )
    run_id = detail["run"]["run_id"]
    store.record_measurement_modality(
        run_id,
        MeasurementModalityProposal(
            candidate="generic_sweep",
            confidence="medium",
            reasons=["The artifact is a frequency sweep of impedance magnitude and phase; headers alone do not identify bulk ion transport."],
            alternatives=["unknown"],
            authority="codex",
        ),
    )
    store.set_dataset_binding(
        run_id,
        DatasetBinding(
            artifact_id="artifact-001",
            x_column_id="col-001",
            y_column_ids=["col-002", "col-003"],
            confirmed_units={"col-001": "Hz", "col-002": "ohm", "col-003": "deg"},
            confirmed_at="2026-07-21T00:00:00+00:00",
        ),
        "generic",
    )
    store.record_source_reviews(run_id, [SourceAdjudication(source_id="src-impedance-limit", verdict="direct", role="method_limit", rationale="The excerpt lists non-bulk alternatives and required controls for low-frequency impedance attribution.")])
    store.prepare_packet(run_id)
    store.inspect_sources(run_id, [{"expected_observation": "Low-frequency impedance dispersion is non-unique.", "condition": "Only the bounded excerpt is frozen.", "falsifier": "The excerpt says a single frequency sweep proves bulk ion transport.", "evidence_ref_ids": ["src-impedance-limit:evidence"]}])
    store.analyze_dataset(run_id)
    band = store.materialize_data_evidence(
        run_id,
        "band_comparison",
        ["col-001", "col-002"],
        2,
        8,
        {"reference_label": "high_frequency", "reference_min": 10000, "reference_max": 100000, "comparison_label": "low_frequency", "comparison_min": 1, "comparison_max": 10},
    )
    phase = store.materialize_data_evidence(
        run_id,
        "band_comparison",
        ["col-001", "col-003"],
        2,
        8,
        {"reference_label": "high_frequency", "reference_min": 10000, "reference_max": 100000, "comparison_label": "low_frequency", "comparison_min": 1, "comparison_max": 10},
    )
    assert band["result"]["reference_band"]["mean"] == pytest.approx(124.5)
    assert band["result"]["comparison_band"]["mean"] == pytest.approx(756.6666666667)
    assert band["result"]["percent_change"] > 500
    assert phase["result"]["comparison_band"]["mean"] == pytest.approx(-74.3333333333)
    store.record_signatures(
        run_id,
        [
            RequiredSignature(id="signature-frequency-dispersion", name="Frequency dispersion", requirement="The impedance response should change between high and low frequency bands.", expected_observation="Low-frequency impedance magnitude is substantially different from the high-frequency band.", falsifying_outcome="No frequency-band difference is present.", theory_evidence_ref_ids=["src-impedance-limit:evidence"]),
            RequiredSignature(id="signature-bulk-attribution", name="Bulk transport attribution", requirement="The low-frequency response must be separable from electrode polarization, interface, blocking-contact, or fitting artifacts.", expected_observation="A geometry, electrode, temperature, or equivalent-circuit control separates bulk from interface alternatives.", falsifying_outcome="The same response remains compatible with electrode/interface alternatives.", theory_evidence_ref_ids=["src-impedance-limit:evidence"]),
            RequiredSignature(id="signature-control-dependent-scaling", name="Control-dependent scaling", requirement="Bulk ion transport should scale consistently with sample geometry or temperature rather than only electrode boundary conditions.", expected_observation="A matched control artifact records the expected scaling.", falsifying_outcome="No scaling control is recorded.", theory_evidence_ref_ids=["src-impedance-limit:evidence"]),
        ],
    )
    convergence = store.record_alignments(
        run_id,
        [
            AlignmentAdjudication(signature_id="signature-frequency-dispersion", status="Observed", rationale="GroundLoop materialized a large low-frequency versus high-frequency impedance-band difference and a strong low-frequency phase shift.", evidence_ref_ids=[band["evidence_id"], phase["evidence_id"]]),
            AlignmentAdjudication(signature_id="signature-bulk-attribution", status="Confounded", rationale="The low-frequency response is real, but this two-electrode method does not separate bulk transport from electrode polarization, interface, blocking-contact, or fitting alternatives.", evidence_ref_ids=[band["evidence_id"], phase["evidence_id"], "method-evidence-frozen", "src-impedance-limit:evidence"], alternative_explanation="Electrode polarization, interfacial capacitance, blocking contacts, or equivalent-circuit non-uniqueness can produce the same low-frequency dispersion."),
            AlignmentAdjudication(signature_id="signature-control-dependent-scaling", status="Missing", rationale="The Run contains no electrode, thickness, temperature, or equivalent-circuit control artifact.", missing_reason="not_measured"),
        ],
    )
    assert convergence["dominant_gap"].startswith("Bulk transport attribution is confounded")
    store.record_control_contract(
        run_id,
        ControlProposal(
            confound="Low-frequency impedance response is not separated from electrode/interface polarization.",
            experiment="Repeat the frequency response with matched blocking and non-blocking electrodes, or matched thickness series, while holding material batch, temperature, area, and amplitude fixed.",
            preconditions=["same material batch", "same temperature", "same AC amplitude", "same area normalization"],
            outcomes=[
                {"if": "the dispersion scales with geometry or temperature consistently across electrode controls", "then": "bulk ion transport attribution gains bounded support."},
                {"if": "the dispersion changes primarily with electrode boundary condition", "then": "electrode/interface polarization remains the dominant explanation."},
            ],
            signature_ref_ids=["signature-bulk-attribution", "signature-control-dependent-scaling"],
            closes_signature_ids=["signature-control-dependent-scaling"],
            leaves_open_signature_ids=["signature-bulk-attribution"],
            required_artifact_labels=["electrode-control impedance sweep", "thickness-or-temperature sweep"],
            priority="high",
            feasibility="Requires one matched impedance control series.",
        ),
    )
    report = store.export_report(run_id)
    markdown = store.get_report_markdown(run_id)
    assert report["verdict"]["label"] == "NOT_ESTABLISHED"
    assert "impedance-frequency-response.csv" in markdown
    assert "Bulk transport attribution is confounded" in markdown


def test_band_comparison_requires_explicit_non_overlapping_bands(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    detail = store.create_generic_run(
        ClaimInput(claim="A frequency response changes across bands."),
        "Frequency response data were exported without enough context to choose bands automatically.",
        IMPEDANCE_RESPONSE,
        [_source()],
        filename="impedance-frequency-response.csv",
    )
    run_id = detail["run"]["run_id"]
    store.set_dataset_binding(
        run_id,
        DatasetBinding(artifact_id="artifact-001", x_column_id="col-001", y_column_ids=["col-002"], confirmed_at="2026-07-21T00:00:00+00:00"),
        "generic",
    )
    store.record_source_reviews(run_id, [SourceAdjudication(source_id="src-spectrum-limit", verdict="direct", role="method_limit", rationale="The source limits mechanism assignment.")])
    store.prepare_packet(run_id)
    store.inspect_sources(run_id, [{"expected_observation": "assignment is limited", "condition": "source excerpt is frozen", "falsifier": "excerpt does not describe a limitation", "evidence_ref_ids": ["src-spectrum-limit:evidence"]}])
    store.analyze_dataset(run_id)
    with pytest.raises(ValueError, match="reference_min"):
        store.materialize_data_evidence(run_id, "band_comparison", ["col-001", "col-002"], 2, 8)
    with pytest.raises(ValueError, match="non-overlapping"):
        store.materialize_data_evidence(run_id, "band_comparison", ["col-001", "col-002"], 2, 8, {"reference_min": 1, "reference_max": 100, "comparison_min": 10, "comparison_max": 1000})


def test_hysteresis_window_materializes_matched_group_separation(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs")
    detail = store.create_generic_run(
        ClaimInput(claim="A cyclic trace contains a hysteretic electrical response."),
        "A cyclic trace contains potential, current, and forward/reverse sweep direction. Only one scan rate was measured.",
        CYCLIC_TRACE,
        [_source()],
        filename="cyclic-trace.csv",
    )
    run_id = detail["run"]["run_id"]
    store.record_measurement_modality(
        run_id,
        MeasurementModalityProposal(
            candidate="generic_cyclic_trace",
            confidence="high",
            reasons=["Potential/current columns and a direction group describe a cyclic trace."],
            authority="codex",
        ),
    )
    store.set_dataset_binding(
        run_id,
        DatasetBinding(artifact_id="artifact-001", x_column_id="col-001", y_column_ids=["col-002"], group_column_id="col-003", confirmed_at="2026-07-21T00:00:00+00:00"),
        "generic_cyclic_trace",
    )
    store.record_source_reviews(
        run_id,
        [SourceAdjudication(source_id="src-spectrum-limit", verdict="direct", role="method_limit", rationale="The supplied source limits mechanism assignment from a single trace.")],
    )
    store.prepare_packet(run_id)
    store.inspect_sources(run_id, [{"expected_observation": "A single trace does not establish the mechanism.", "condition": "Only the bounded excerpt is frozen.", "falsifier": "The excerpt does not state the limitation.", "evidence_ref_ids": ["src-spectrum-limit:evidence"]}])
    store.analyze_dataset(run_id)
    evidence = store.materialize_data_evidence(run_id, "hysteresis_window", ["col-003", "col-001", "col-002"], 2, 14)
    assert evidence["operation"] == "hysteresis_window"
    assert evidence["result"]["matched_x_count"] == 4
    assert evidence["result"]["max_window"] == {"x": 0.15, "window": 8.7, "values": {"forward": 4.8, "reverse": -3.9}}
    assert "maximum group separation of 8.7" in evidence["fact_text"]


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
    with pytest.raises(ValueError, match="explicit artifact_id"):
        store.materialize_data_evidence(run_id, "argmax", ["col-001", "col-002"], 2, 6)
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
