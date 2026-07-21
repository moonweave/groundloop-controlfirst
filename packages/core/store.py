from __future__ import annotations

import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from .analysis import parse_dataset, screen_source_relevance, source_refs
from .convergence import legacy_projection, preview_map, validate_alignment_records
from .generic_tabular import infer_modality, materialize_evidence, profile_csv
from .models import (
    AuditEvent,
    AlignmentAdjudication,
    ClaimInput,
    ConvergenceMap,
    ControlProposal,
    DataEvidence,
    DatasetArtifact,
    DatasetBinding,
    DatasetAnalysis,
    DatasetProfile,
    EvidenceRef,
    Finding,
    LiteratureCandidate,
    MechanismVerdict,
    MeasurementModalityProposal,
    Report,
    RequiredSignature,
    RunState,
    RunSummary,
    SourceAdjudication,
    SourceInput,
    SourceReview,
    now_iso,
)
from .validation import mechanism_not_established_verdict, validate_control, validate_findings


def _retrieval_provider_label(sources: list[SourceInput]) -> str:
    providers = {source.retrieval_provider for source in sources}
    if providers == {"openalex", "arxiv"}:
        return "OpenAlex + arXiv candidate retrieval"
    if providers == {"arxiv"}:
        return "arXiv preprint candidate retrieval"
    if providers == {"openalex"}:
        return "OpenAlex indexed-abstract candidate retrieval"
    return " + ".join(sorted(providers)) + " candidate retrieval"


def _retrieval_summary(sources: list[SourceInput]) -> str:
    openalex_count = sum(source.retrieval_provider == "openalex" for source in sources)
    arxiv_count = sum(source.retrieval_provider == "arxiv" for source in sources)
    parts: list[str] = []
    if openalex_count:
        parts.append(f"{openalex_count} OpenAlex indexed abstract candidate(s)")
    if arxiv_count:
        parts.append(f"{arxiv_count} arXiv preprint candidate(s)")
    return " + ".join(parts) or "No source candidates"


def _canonical_source_identity(value: str) -> str:
    identity = value.strip().lower().rstrip("/")
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if identity.startswith(prefix):
            return identity[len(prefix):]
    return identity


CAPABILITY_PACK_IDS = {
    "generic",
    "generic_spectrum",
    "generic_sweep",
    "generic_time_series",
    "generic_cyclic_trace",
    "grouped_comparison",
    "electrical_transport_rt",
    "actuator_dynamics",
}


class RunStore:
    """A local-only, typed filesystem store. Callers never provide a file path."""

    def __init__(self, root: Path | str = ".groundloop/runs") -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _artifact_csv_path(self, run: Path, artifact_id: str) -> Path:
        return run / "inputs" / "artifacts" / f"{artifact_id}.csv"

    def _sync_primary_artifact_mirror(self, run: Path, artifact: DatasetArtifact, profile: DatasetProfile, raw: bytes) -> None:
        (run / "inputs" / "dataset.csv").write_bytes(raw)
        self._write(run / "inputs" / "dataset-artifact.json", artifact.model_dump(mode="json"))
        self._write(run / "inputs" / "dataset-profile.json", profile.model_dump(mode="json"))

    def _write_artifact_ledger(
        self,
        run: Path,
        artifacts: list[DatasetArtifact],
        profiles: list[DatasetProfile],
    ) -> None:
        if not artifacts:
            raise ValueError("at least one measurement artifact is required")
        ids = [artifact.artifact_id for artifact in artifacts]
        hashes = [artifact.sha256 for artifact in artifacts]
        if len(ids) != len(set(ids)):
            raise ValueError("measurement artifact IDs must be unique")
        if len(hashes) != len(set(hashes)):
            raise ValueError("duplicate measurement artifact hash")
        profile_ids = {profile.artifact_id for profile in profiles}
        if profile_ids != set(ids):
            raise ValueError("measurement artifact profiles must cover every artifact")
        self._write(run / "inputs" / "artifacts.json", [item.model_dump(mode="json") for item in artifacts])
        self._write(run / "inputs" / "artifact-profiles.json", [item.model_dump(mode="json") for item in profiles])

    def _measurement_artifacts(self, run: Path) -> tuple[list[DatasetArtifact], list[DatasetProfile]]:
        artifacts_path = run / "inputs" / "artifacts.json"
        profiles_path = run / "inputs" / "artifact-profiles.json"
        if artifacts_path.is_file() and profiles_path.is_file():
            return (
                [DatasetArtifact.model_validate(item) for item in self._read(artifacts_path)],
                [DatasetProfile.model_validate(item) for item in self._read(profiles_path)],
            )
        artifact = DatasetArtifact.model_validate(self._read(run / "inputs" / "dataset-artifact.json"))
        profile = DatasetProfile.model_validate(self._read(run / "inputs" / "dataset-profile.json"))
        return [artifact], [profile]

    def _artifact_bindings(self, run: Path) -> list[DatasetBinding]:
        path = run / "inputs" / "artifact-bindings.json"
        if path.is_file() and not self._generic_binding_invalidated(run):
            return [DatasetBinding.model_validate(item) for item in self._read(path)]
        legacy = run / "inputs" / "dataset-binding.json"
        if legacy.is_file() and not self._generic_binding_invalidated(run):
            return [DatasetBinding.model_validate(self._read(legacy))]
        return []

    def _write_artifact_bindings(self, run: Path, bindings: list[DatasetBinding]) -> None:
        ids = [binding.artifact_id for binding in bindings]
        if len(ids) != len(set(ids)):
            raise ValueError("artifact binding IDs must be unique")
        self._write(run / "inputs" / "artifact-bindings.json", [item.model_dump(mode="json") for item in bindings])
        primary = next((binding for binding in bindings if binding.artifact_id == "artifact-001"), bindings[0] if bindings else None)
        if primary:
            self._write(run / "inputs" / "dataset-binding.json", primary.model_dump(mode="json"))

    def _invalidate_generic_measurement_context(self, run: Path, summary: str) -> None:
        self._write(run / "inputs" / "binding-invalidated.json", {"invalid": True, "at": now_iso()})
        self._write(run / "inputs" / "codex-routing-invalidated.json", {"invalid": True, "at": now_iso()})
        self._record_event(run, action="generic_binding_invalidated", state=RunState.DRAFT, summary=summary)
        self._record_event(run, action="codex_measurement_routing_invalidated", state=RunState.DRAFT, summary="Claim, method, source boundary, or artifact changed; Codex should review measurement routing again, but generic reasoning remains available.")

    def create_run(self, fixture: str | None = None) -> RunSummary:
        run_id = str(uuid.uuid4())
        run_dir = self.root / run_id
        run_dir.mkdir()
        summary = RunSummary(run_id=run_id, state=RunState.DRAFT, fixture=fixture, created_at=now_iso())
        self._write(run_dir / "manifest.json", summary.model_dump(mode="json"))
        for directory in ("inputs", "analysis", "report"):
            (run_dir / directory).mkdir()
        self._record_event(
            run_dir,
            action="run_created",
            state=RunState.DRAFT,
            summary="Local research run created.",
        )
        return summary

    def create_generic_run(
        self,
        claim: ClaimInput,
        methods: str,
        dataset: bytes,
        sources: list[SourceInput] | None = None,
        *,
        filename: str = "dataset.csv",
        provenance: str = "USER_MEASUREMENT",
    ) -> dict[str, Any]:
        """Create a v2, domain-neutral Run from one bounded tabular artifact.

        The same filesystem Run is used as v1, but v2 never calls the transport
        parser unless a researcher later confirms that optional recipe.
        """
        if len(methods.strip()) < 20 or len(methods) > 20_000:
            raise ValueError("methods must contain 20–20,000 characters")
        if sources is not None and len(sources) > 20:
            raise ValueError("at most 20 source candidates are supported")
        artifact, profile = profile_csv(dataset)
        summary = self.create_run()
        summary = summary.model_copy(update={"schema_version": 2, "workflow": "generic_v2"})
        run = self._run_dir(summary.run_id)
        self._write(run / "manifest.json", summary.model_dump(mode="json"))
        artifact = DatasetArtifact.model_validate(artifact.model_copy(update={"filename": filename, "provenance": provenance, "label": "primary_measurement"}).model_dump(mode="json"))
        (run / "inputs" / "artifacts").mkdir(exist_ok=True)
        self._write(run / "inputs" / "claim.json", claim.model_dump(mode="json"))
        self._write(run / "inputs" / "sources.json", [item.model_dump(mode="json") for item in sources or []])
        (run / "inputs" / "methods.md").write_text(methods, encoding="utf-8")
        self._artifact_csv_path(run, artifact.artifact_id).write_bytes(dataset)
        self._sync_primary_artifact_mirror(run, artifact, profile, dataset)
        self._write_artifact_ledger(run, [artifact], [profile])
        self._write(run / "inputs" / "modality-proposal.json", infer_modality(profile, methods))
        self._write(run / "inputs" / "dataset-provenance.json", {"kind": provenance})
        self._record_event(run, action="generic_dataset_profiled", state=RunState.DRAFT, summary=f"Profiled {profile.row_count} rows and {profile.column_count} columns without selecting a scientific interpretation.")
        return self.get_detail(summary.run_id)

    def create_generic_fixture_run(self, fixture_root: Path | str) -> dict[str, Any]:
        root = Path(fixture_root).resolve()
        required = ("claim.json", "methods.md", "dataset.csv", "sources.json")
        missing = [name for name in required if not (root / name).is_file()]
        if missing:
            raise ValueError(f"fixture is missing: {', '.join(missing)}")
        return self.create_generic_run(
            ClaimInput.model_validate(self._read(root / "claim.json")),
            (root / "methods.md").read_text(encoding="utf-8"),
            (root / "dataset.csv").read_bytes(),
            [SourceInput.model_validate(item) for item in self._read(root / "sources.json")],
            filename="dataset.csv", provenance="LABELLED_DEMO",
        )

    def inspect_dataset_profile(self, run_id: str) -> dict[str, Any]:
        run = self._run_dir(run_id)
        if self.get_summary(run_id).workflow != "generic_v2":
            raise ValueError("dataset profiles are available through the generic v2 workflow")
        binding_invalidated = self._generic_binding_invalidated(run)
        artifacts, profiles = self._measurement_artifacts(run)
        bindings = self._artifact_bindings(run)
        return {
            "artifact": artifacts[0].model_dump(mode="json"),
            "profile": profiles[0].model_dump(mode="json"),
            "artifacts": [item.model_dump(mode="json") for item in artifacts],
            "profiles": [item.model_dump(mode="json") for item in profiles],
            "modality_proposal": self._active_measurement_routing(run),
            "heuristic_modality_signal": self._heuristic_modality_signal(run),
            "binding": bindings[0].model_dump(mode="json") if bindings and not binding_invalidated else None,
            "bindings": [item.model_dump(mode="json") for item in bindings] if not binding_invalidated else [],
        }

    def add_measurement_artifact(
        self,
        run_id: str,
        dataset: bytes,
        *,
        artifact_id: str,
        filename: str = "dataset.csv",
        provenance: str = "USER_MEASUREMENT",
        label: str | None = None,
    ) -> dict[str, Any]:
        """Attach another bounded CSV artifact to an editable generic Run."""
        run = self._require_draft(run_id)
        if self.get_summary(run_id).workflow != "generic_v2":
            raise ValueError("measurement artifacts are available through the generic v2 workflow")
        artifact, profile = profile_csv(dataset, artifact_id=artifact_id)
        artifact = DatasetArtifact.model_validate(artifact.model_copy(update={"filename": filename, "provenance": provenance, "label": label}).model_dump(mode="json"))
        artifacts, profiles = self._measurement_artifacts(run)
        if artifact.artifact_id in {item.artifact_id for item in artifacts}:
            raise ValueError("duplicate measurement artifact ID")
        if artifact.sha256 in {item.sha256 for item in artifacts}:
            raise ValueError("duplicate measurement artifact hash")
        (run / "inputs" / "artifacts").mkdir(exist_ok=True)
        self._artifact_csv_path(run, artifact.artifact_id).write_bytes(dataset)
        artifacts.append(artifact)
        profiles.append(profile)
        self._write_artifact_ledger(run, artifacts, profiles)
        self._invalidate_generic_measurement_context(
            run,
            "Measurement artifact set changed; researcher confirmation of every artifact binding and capability pack is required again.",
        )
        self._record_event(run, action="measurement_artifact_added", state=RunState.DRAFT, summary=f"Added bounded CSV artifact {artifact.artifact_id}; no rows were merged.")
        return self.inspect_measurement_artifacts(run_id)

    def inspect_measurement_artifacts(self, run_id: str) -> dict[str, Any]:
        run = self._run_dir(run_id)
        if self.get_summary(run_id).workflow != "generic_v2":
            raise ValueError("measurement artifacts are available through the generic v2 workflow")
        artifacts, profiles = self._measurement_artifacts(run)
        bindings = self._artifact_bindings(run)
        bound_ids = {binding.artifact_id for binding in bindings}
        return {
            "artifacts": [item.model_dump(mode="json") for item in artifacts],
            "profiles": [item.model_dump(mode="json") for item in profiles],
            "bindings": [item.model_dump(mode="json") for item in bindings],
            "binding_status": [
                {
                    "artifact_id": artifact.artifact_id,
                    "status": "confirmed" if artifact.artifact_id in bound_ids and not self._generic_binding_invalidated(run) else "required",
                }
                for artifact in artifacts
            ],
            "binding_invalidated": self._generic_binding_invalidated(run),
        }

    def import_literature_candidates(
        self, run_id: str, candidates: list[LiteratureCandidate]
    ) -> dict[str, Any]:
        """Import bounded Codex-discovered literature without fetching any URL."""
        run = self._require_draft(run_id)
        if self.get_summary(run_id).workflow != "generic_v2":
            raise ValueError("literature candidate import is available through the generic v2 workflow")
        if not 1 <= len(candidates) <= 20:
            raise ValueError("import between 1 and 20 literature candidates")

        candidate_sources = [
            SourceInput(
                id=item.id,
                title=item.title,
                authors=item.authors,
                year=item.year,
                url_or_doi=item.url_or_doi,
                locator=item.locator,
                untrusted_content=item.excerpt,
                retrieval_provider=item.retrieval_provider,
                publication_status=item.publication_status,
                retrieved_at=item.retrieved_at,
                search_query=item.search_query,
                discovery_rationale=item.discovery_rationale,
                content_sha256=item.content_sha256,
            )
            for item in candidates
        ]
        existing_path = run / "inputs" / "retrieval-candidates.json"
        existing_raw = self._read(existing_path) if existing_path.is_file() else self._read(run / "inputs" / "sources.json")
        existing = [SourceInput.model_validate(item) for item in existing_raw]
        all_sources = [*existing, *candidate_sources]
        seen_ids: set[str] = set()
        seen_urls: set[str] = set()
        seen_hashes: set[str] = set()
        duplicates: list[str] = []
        for source in all_sources:
            canonical = _canonical_source_identity(source.url_or_doi)
            content_hash = source.content_sha256 or ""
            if source.id in seen_ids or canonical in seen_urls or (content_hash and content_hash in seen_hashes):
                duplicates.append(source.id)
            seen_ids.add(source.id)
            seen_urls.add(canonical)
            if content_hash:
                seen_hashes.add(content_hash)
        if duplicates:
            raise ValueError(f"duplicate literature candidate identity: {', '.join(sorted(set(duplicates)))}")

        self._write(existing_path, [source.model_dump(mode="json") for source in all_sources])
        self._write(run / "inputs" / "sources.json", [source.model_dump(mode="json") for source in all_sources])
        review_path = run / "analysis" / "source-adjudication.json"
        if review_path.is_file():
            review_path.unlink()
            self._record_event(run, action="literature_review_invalidated", state=RunState.DRAFT, summary="Imported literature candidates changed the source boundary; Codex must review every candidate again.")
        self._write(run / "inputs" / "codex-routing-invalidated.json", {"invalid": True, "at": now_iso()})
        self._record_event(run, action="literature_candidates_imported", state=RunState.DRAFT, summary=f"Imported {len(candidate_sources)} bounded literature candidate(s) from Codex; no URL was fetched by GroundLoop.")
        return self.get_detail(run_id)

    def propose_measurement_modality(self, run_id: str) -> dict[str, Any]:
        """Return a header/method heuristic only; it cannot constrain Codex reasoning."""
        run = self._require_draft(run_id)
        if self.get_summary(run_id).workflow != "generic_v2":
            raise ValueError("measurement routing is available through the generic v2 workflow")
        profile = DatasetProfile.model_validate(self._read(run / "inputs" / "dataset-profile.json"))
        methods = (run / "inputs" / "methods.md").read_text(encoding="utf-8")
        proposal = MeasurementModalityProposal.model_validate(infer_modality(profile, methods))
        self._write(run / "inputs" / "modality-proposal.json", proposal.model_dump(mode="json"))
        return proposal.model_dump(mode="json")

    def record_measurement_modality(
        self, run_id: str, proposal: MeasurementModalityProposal
    ) -> dict[str, Any]:
        """Persist Codex's literature- and method-aware routing proposal.

        This records an auditable proposal, never a scientific interpretation or
        activation gate. A researcher still confirms the column binding and may
        always retain the generic capability pack.
        """
        run = self._require_draft(run_id)
        if self.get_summary(run_id).workflow != "generic_v2":
            raise ValueError("measurement routing is available through the generic v2 workflow")
        if proposal.authority != "codex":
            raise ValueError("recorded measurement routing must be Codex-authored")
        recorded = proposal.model_copy(update={"recorded_at": now_iso()})
        self._write(run / "inputs" / "codex-modality-proposal.json", recorded.model_dump(mode="json"))
        self._write(run / "inputs" / "codex-routing-invalidated.json", {"invalid": False, "at": now_iso()})
        self._record_event(
            run,
            action="codex_measurement_modality_recorded",
            state=RunState.DRAFT,
            summary=f"Codex recorded '{recorded.candidate}' as a proposed measurement modality; researcher confirmation is still required.",
        )
        return self.inspect_dataset_profile(run_id)

    def set_dataset_binding(self, run_id: str, binding: DatasetBinding, recipe: str = "generic") -> dict[str, Any]:
        return self.set_artifact_binding(run_id, binding, recipe)

    def set_artifact_binding(self, run_id: str, binding: DatasetBinding, recipe: str = "generic") -> dict[str, Any]:
        run = self._require_draft(run_id)
        if self.get_summary(run_id).workflow != "generic_v2":
            raise ValueError("dataset binding is available through the generic v2 workflow")
        artifacts, profiles = self._measurement_artifacts(run)
        artifact_ids = {artifact.artifact_id for artifact in artifacts}
        if binding.artifact_id not in artifact_ids:
            raise ValueError("binding must target a known measurement artifact")
        profile = next(item for item in profiles if item.artifact_id == binding.artifact_id)
        known = {column.column_id for column in profile.columns}
        assigned = [binding.x_column_id, *binding.y_column_ids, binding.group_column_id, binding.acquisition_order_column_id]
        if any(item not in known for item in assigned if item):
            raise ValueError("binding references an unknown column")
        if any(column_id not in known for column_id in binding.confirmed_units):
            raise ValueError("confirmed units reference an unknown column")
        if recipe not in CAPABILITY_PACK_IDS:
            raise ValueError("unsupported measurement capability pack")
        routing = MeasurementModalityProposal.model_validate(self._active_measurement_routing(run))
        bindings = [item for item in self._artifact_bindings(run) if item.artifact_id != binding.artifact_id]
        bindings.append(binding)
        bindings = sorted(bindings, key=lambda item: item.artifact_id)
        self._write_artifact_bindings(run, bindings)
        self._write(run / "inputs" / "recipe.json", {
            "kind": "measurement_capability_pack",
            "id": recipe,
            "version": "1",
            "confirmed_by": "researcher",
            "confirmed_at": now_iso(),
            "routing_authority": routing.authority,
            "routing_candidate": routing.candidate,
            "routing_match_required": False,
            "scope": "Deterministic evidence operation guidance only; does not constrain Codex signatures, alignments, controls, or scientific conclusions.",
        })
        self._write(run / "inputs" / "binding-invalidated.json", {"invalid": False, "at": now_iso()})
        self._record_event(run, action="dataset_binding_confirmed", state=RunState.DRAFT, summary=f"Researcher confirmed binding for {binding.artifact_id} and '{recipe}' measurement capability pack.")
        return self.inspect_measurement_artifacts(run_id)

    def _heuristic_modality_signal(self, run: Path) -> dict[str, Any]:
        return self._read(run / "inputs" / "modality-proposal.json")

    def _generic_binding_invalidated(self, run: Path) -> bool:
        path = run / "inputs" / "binding-invalidated.json"
        return path.is_file() and self._read(path).get("invalid", False)

    def _active_measurement_routing(self, run: Path) -> dict[str, Any]:
        """Prefer a current Codex proposal; otherwise expose only an advisory signal."""
        codex_path = run / "inputs" / "codex-modality-proposal.json"
        invalidated_path = run / "inputs" / "codex-routing-invalidated.json"
        invalidated = invalidated_path.is_file() and self._read(invalidated_path).get("invalid", False)
        if codex_path.is_file() and not invalidated:
            return self._read(codex_path)
        return self._heuristic_modality_signal(run)

    def create_codex_run(
        self,
        claim: ClaimInput,
        methods: str,
        dataset: bytes,
        sources: list[SourceInput] | None = None,
    ) -> dict[str, Any]:
        """Create a complete draft from Codex without requiring the web UI."""

        summary = self.create_run()
        self.update_editable_inputs(summary.run_id, claim, methods, dataset, sources or None)
        return self.get_detail(summary.run_id)

    def list_runs(self) -> list[RunSummary]:
        result: list[RunSummary] = []
        for manifest in self.root.glob("*/manifest.json"):
            try:
                summary = RunSummary.model_validate(self._read(manifest))
                canonical_id = str(uuid.UUID(summary.run_id))
                if manifest.parent.name != canonical_id or summary.run_id != canonical_id:
                    continue
                result.append(summary)
            except (OSError, ValueError):
                continue
        return sorted(result, key=lambda item: item.created_at, reverse=True)

    def get_summary(self, run_id: str) -> RunSummary:
        return RunSummary.model_validate(self._read(self._run_dir(run_id) / "manifest.json"))

    def create_fixture_run(self, fixture_root: Path | str) -> RunSummary:
        root = Path(fixture_root).resolve()
        required = ("claim.json", "sources.json", "methods.md", "dataset.csv")
        missing = [name for name in required if not (root / name).is_file()]
        if missing:
            raise ValueError(f"fixture is missing: {', '.join(missing)}")
        summary = self.create_run(fixture=root.name)
        run = self._run_dir(summary.run_id)
        for name in required:
            shutil.copyfile(root / name, run / "inputs" / name)
        self._write(run / "inputs" / "dataset-provenance.json", {"kind": "FIXTURE_DEMO"})
        self._record_event(
            run,
            action="fixture_loaded",
            state=RunState.DRAFT,
            summary="Fixture inputs loaded for a labelled demonstration run.",
        )
        return summary

    def create_guided_demo_run(self, fixture_root: Path | str) -> Report:
        """Create a labelled, reproducible report without requiring an MCP session.

        This path is intentionally fixture-only. It runs the same state machine as
        the MCP workflow with fixed, reviewable inputs so a first-time reviewer can
        inspect the product outcome before choosing the manual integration path.
        """
        summary = self.create_fixture_run(fixture_root)
        self.record_source_reviews(
            summary.run_id,
            [
                SourceAdjudication(
                    source_id="src-four-wire-principle",
                    verdict="direct",
                    role="theory_basis",
                    rationale="The supplied excerpt states the four-terminal measurement principle used to isolate the sensed voltage.",
                ),
                SourceAdjudication(
                    source_id="src-contact-contribution",
                    verdict="direct",
                    role="method_limit",
                    rationale="The supplied excerpt states why two-wire resistance can include measurement error and why four-wire sensing is the control.",
                ),
            ],
        )
        self.prepare_packet(summary.run_id)
        self.inspect_sources(
            summary.run_id,
            [
                {
                    "expected_observation": "Four-terminal sensing separates current delivery from voltage sensing and reduces lead and contact error.",
                    "condition": "The same mounted sample, excitation current, and temperature program are held fixed.",
                    "falsifier": "The supplied measurement-principle sources do not describe separating the sensed voltage from current delivery.",
                    "evidence_ref_ids": ["src-four-wire-principle:evidence"],
                }
            ],
        )
        self.analyze_dataset(summary.run_id)
        self.reconcile_findings(
            summary.run_id,
            [
                Finding(
                    id="finding-four-wire-principle",
                    statement="Four-terminal sensing separates current delivery from voltage sensing.",
                    status="Established",
                    evidence_ref_ids=["src-four-wire-principle:evidence"],
                    reasoning="The supplied measurement principle distinguishes the current path from the sensed voltage path.",
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
                    reasoning="The observed trend is compatible with the stated interpretation but the two-wire measurement does not isolate the sample resistance.",
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
            ],
        )
        self.propose_control(
            summary.run_id,
            ControlProposal(
                confound="Temperature-dependent lead or contact resistance",
                experiment="Repeat the same temperature sweep in four-terminal mode while holding the sample, current, mounting, and temperature program fixed.",
                preconditions=["Same sample", "Same current", "Same mounting", "Same temperature program"],
                outcomes=[
                    {"if": "The trend persists in four-terminal mode", "then": "Support for a bulk contribution increases."},
                    {"if": "The trend weakens substantially in four-terminal mode", "then": "A contact or lead contribution becomes more plausible."},
                ],
                finding_ref_ids=["finding-bulk-inference", "finding-contact-unresolved"],
                priority="high",
                feasibility="A matched four-terminal sweep is a bounded next measurement.",
            ),
        )
        return self.export_report(summary.run_id)

    def save_inputs(
        self,
        run_id: str,
        claim: ClaimInput,
        sources: list[SourceInput],
        methods: str,
        dataset: bytes,
    ) -> RunSummary:
        run = self._require_draft(run_id)
        if len(methods.strip()) < 20 or len(methods) > 20_000:
            raise ValueError("methods must contain 20–20,000 characters")
        parse_dataset(dataset)
        self._write(run / "inputs" / "claim.json", claim.model_dump(mode="json"))
        self._write(run / "inputs" / "sources.json", [source.model_dump(mode="json") for source in sources])
        (run / "inputs" / "methods.md").write_text(methods, encoding="utf-8")
        (run / "inputs" / "dataset.csv").write_bytes(dataset)
        self._write(run / "inputs" / "dataset-provenance.json", {"kind": "USER_MEASUREMENT"})
        return self.get_summary(run_id)

    def update_claim(self, run_id: str, claim: ClaimInput) -> RunSummary:
        run = self._require_draft(run_id)
        if self.get_summary(run_id).workflow == "generic_v2":
            self.update_editable_inputs(run_id, claim=claim)
            return self.get_summary(run_id)
        self._write(run / "inputs" / "claim.json", claim.model_dump(mode="json"))
        return self.get_summary(run_id)

    def update_sources(self, run_id: str, sources: list[SourceInput]) -> RunSummary:
        run = self._require_draft(run_id)
        if not sources:
            raise ValueError("at least one source is required")
        if self.get_summary(run_id).workflow == "generic_v2":
            self.update_editable_inputs(run_id, sources=sources)
            return self.get_summary(run_id)
        self._write(run / "inputs" / "sources.json", [source.model_dump(mode="json") for source in sources])
        return self.get_summary(run_id)

    def update_editable_inputs(
        self,
        run_id: str,
        claim: ClaimInput | None = None,
        methods: str | None = None,
        dataset: bytes | None = None,
        sources: list[SourceInput] | None = None,
    ) -> dict[str, Any]:
        """Validate and persist a partial draft update without partial writes."""

        run = self._require_draft(run_id)
        if self.get_summary(run_id).workflow == "generic_v2":
            return self._update_generic_editable_inputs(run_id, run, claim, methods, dataset, sources)
        if methods is not None and (len(methods.strip()) < 20 or len(methods) > 20_000):
            raise ValueError("methods must contain 20–20,000 characters")
        if dataset is not None:
            parse_dataset(dataset)
        if sources is not None and not sources:
            raise ValueError("at least one source is required")

        if claim is not None:
            self._write(run / "inputs" / "claim.json", claim.model_dump(mode="json"))
        if methods is not None:
            (run / "inputs" / "methods.md").write_text(methods, encoding="utf-8")
        if dataset is not None:
            (run / "inputs" / "dataset.csv").write_bytes(dataset)
            self._write(run / "inputs" / "dataset-provenance.json", {"kind": "USER_MEASUREMENT"})
        if sources is not None:
            self._write(run / "inputs" / "sources.json", [source.model_dump(mode="json") for source in sources])
        return self.get_detail(run_id)

    def _update_generic_editable_inputs(
        self,
        run_id: str,
        run: Path,
        claim: ClaimInput | None,
        methods: str | None,
        dataset: bytes | None,
        sources: list[SourceInput] | None,
    ) -> dict[str, Any]:
        """Atomically update v2 editable inputs and invalidate stale binding on semantic changes."""
        if methods is not None and (len(methods.strip()) < 20 or len(methods) > 20_000):
            raise ValueError("methods must contain 20–20,000 characters")
        if sources is not None and len(sources) > 20:
            raise ValueError("at most 20 source candidates are supported")
        artifact: DatasetArtifact | None = None
        profile: DatasetProfile | None = None
        if dataset is not None:
            artifact, profile = profile_csv(dataset)
            previous = DatasetArtifact.model_validate(self._read(run / "inputs" / "dataset-artifact.json"))
            artifact = DatasetArtifact.model_validate(artifact.model_copy(update={"filename": previous.filename, "provenance": previous.provenance, "label": previous.label}).model_dump(mode="json"))
        next_methods = methods if methods is not None else (run / "inputs" / "methods.md").read_text(encoding="utf-8")
        next_profile = profile or DatasetProfile.model_validate(self._read(run / "inputs" / "dataset-profile.json"))
        if claim is not None:
            self._write(run / "inputs" / "claim.json", claim.model_dump(mode="json"))
        if methods is not None:
            (run / "inputs" / "methods.md").write_text(methods, encoding="utf-8")
        if dataset is not None and artifact and profile:
            artifacts, profiles = self._measurement_artifacts(run)
            next_artifacts = [artifact if item.artifact_id == artifact.artifact_id else item for item in artifacts]
            next_profiles = [profile if item.artifact_id == profile.artifact_id else item for item in profiles]
            (run / "inputs" / "artifacts").mkdir(exist_ok=True)
            self._artifact_csv_path(run, artifact.artifact_id).write_bytes(dataset)
            self._sync_primary_artifact_mirror(run, artifact, profile, dataset)
            self._write_artifact_ledger(run, next_artifacts, next_profiles)
        if sources is not None:
            source_payload = [item.model_dump(mode="json") for item in sources]
            self._write(run / "inputs" / "sources.json", source_payload)
            if (run / "inputs" / "retrieval-candidates.json").is_file():
                self._write(run / "inputs" / "retrieval-candidates.json", source_payload)
            review_path = run / "analysis" / "source-adjudication.json"
            if review_path.is_file():
                review_path.unlink()
                self._record_event(run, action="generic_source_review_invalidated", state=RunState.DRAFT, summary="Source candidates changed; Codex must review source roles again before freezing.")
        routing_context_changed = any(item is not None for item in (claim, methods, dataset, sources))
        if routing_context_changed:
            if dataset is not None or methods is not None:
                self._invalidate_generic_measurement_context(run, "Method or artifact changed; researcher confirmation of binding and recipe is required again.")
            else:
                self._write(run / "inputs" / "codex-routing-invalidated.json", {"invalid": True, "at": now_iso()})
                self._record_event(run, action="codex_measurement_routing_invalidated", state=RunState.DRAFT, summary="Claim, method, source boundary, or artifact changed; Codex should review measurement routing again, but generic reasoning remains available.")
        self._write(run / "inputs" / "modality-proposal.json", infer_modality(next_profile, next_methods))
        return self.get_detail(run_id)

    def save_research_setup(self, run_id: str, claim: ClaimInput, sources: list[SourceInput]) -> RunSummary:
        """Persist unreviewed retrieval candidates while the run is still editable."""
        run = self._require_draft(run_id)
        if not sources:
            raise ValueError("the literature search did not return usable source abstracts")
        self._write(run / "inputs" / "claim.json", claim.model_dump(mode="json"))
        self._write(
            run / "inputs" / "retrieval-candidates.json",
            [source.model_dump(mode="json") for source in sources],
        )
        review_path = run / "analysis" / "source-adjudication.json"
        if review_path.exists():
            review_path.unlink()
        self._record_event(
            run,
            action="references_retrieved",
            state=RunState.DRAFT,
            summary=f"{_retrieval_summary(sources)} retrieved; source review is required before freezing.",
        )
        return self.get_summary(run_id)

    def adjudicate_retrieved_sources(
        self, run_id: str, adjudications: list[SourceAdjudication]
    ) -> dict[str, Any]:
        """Select decision-eligible sources from a retrieved candidate set.

        This is intentionally a DRAFT-only operation: Codex can reason over the
        supplied excerpts, but the evidence boundary is not frozen until the
        researcher explicitly prepares the packet afterwards.
        """
        run = self._require_draft(run_id)
        candidates_path = run / "inputs" / "retrieval-candidates.json"
        if not candidates_path.is_file():
            raise ValueError("source adjudication is only required for automatically retrieved candidates")
        candidates = [SourceInput.model_validate(item) for item in self._read(candidates_path)]
        candidate_ids = {source.id for source in candidates}
        adjudication_ids = [item.source_id for item in adjudications]
        if len(adjudication_ids) != len(set(adjudication_ids)):
            raise ValueError("each retrieved candidate must receive exactly one source adjudication")
        if set(adjudication_ids) != candidate_ids:
            raise ValueError("source adjudication must classify every retrieved candidate exactly once")
        selected_ids = {
            item.source_id for item in adjudications if item.verdict == "direct"
        }
        if not selected_ids:
            raise ValueError("at least one retrieved source must be adjudicated direct before freezing")
        selected_sources = [source for source in candidates if source.id in selected_ids]
        self._write(
            run / "analysis" / "source-adjudication.json",
            {
                "provider": _retrieval_provider_label(candidates),
                "adjudications": [item.model_dump(mode="json", exclude_none=True) for item in adjudications],
                "direct_source_ids": [source.id for source in selected_sources],
                "adjudicated_at": now_iso(),
            },
        )
        self._write(
            run / "inputs" / "sources.json",
            [source.model_dump(mode="json") for source in selected_sources],
        )
        self._record_event(
            run,
            action="sources_adjudicated",
            state=RunState.DRAFT,
            summary=f"Codex reviewed {len(adjudications)} candidate(s) and selected {len(selected_sources)} direct decision source(s).",
        )
        return self._draft(run)

    def update_methods(self, run_id: str, methods: str) -> RunSummary:
        run = self._require_draft(run_id)
        if self.get_summary(run_id).workflow == "generic_v2":
            self.update_editable_inputs(run_id, methods=methods)
            return self.get_summary(run_id)
        if len(methods.strip()) < 20 or len(methods) > 20_000:
            raise ValueError("methods must contain 20–20,000 characters")
        methods_path = run / "inputs" / "methods.md"
        methods_path.write_text(methods, encoding="utf-8")
        return self.get_summary(run_id)

    def record_source_reviews(
        self, run_id: str, adjudications: list[SourceAdjudication]
    ) -> dict[str, Any]:
        """Record role-aware semantic source review for UI- or Codex-created runs."""

        run = self._require_draft(run_id)
        candidates_path = run / "inputs" / "retrieval-candidates.json"
        source_path = candidates_path if candidates_path.is_file() else run / "inputs" / "sources.json"
        if not source_path.is_file():
            raise ValueError("source review requires supplied source candidates")
        candidates = [SourceInput.model_validate(item) for item in self._read(source_path)]
        candidate_ids = {source.id for source in candidates}
        review_ids = [item.source_id for item in adjudications]
        if len(review_ids) != len(set(review_ids)) or set(review_ids) != candidate_ids:
            raise ValueError("source review must classify every supplied source exactly once")
        if any(item.verdict == "direct" and item.role is None for item in adjudications):
            raise ValueError("every direct source must receive one explicit evidence role")
        direct = [item.source_id for item in adjudications if item.verdict == "direct"]
        if not direct:
            raise ValueError("at least one supplied source must be reviewed direct before freezing")
        selected = [source for source in candidates if source.id in direct]
        self._write(
            run / "analysis" / "source-adjudication.json",
            {
                "provider": _retrieval_provider_label(candidates),
                "adjudications": [item.model_dump(mode="json", exclude_none=True) for item in adjudications],
                "direct_source_ids": [source.id for source in selected],
                "adjudicated_at": now_iso(),
            },
        )
        self._write(run / "inputs" / "sources.json", [source.model_dump(mode="json") for source in selected])
        self._record_event(
            run,
            action="source_roles_reviewed",
            state=RunState.DRAFT,
            summary=f"Semantic review assigned roles to {len(adjudications)} source candidate(s); {len(selected)} direct source(s) remain eligible.",
        )
        if self.get_summary(run_id).workflow == "generic_v2":
            return self._get_generic_detail(self.get_summary(run_id), run)["draft"]
        return self._draft(run)

    def update_dataset(self, run_id: str, dataset: bytes) -> dict[str, Any]:
        run = self._require_draft(run_id)
        if self.get_summary(run_id).workflow == "generic_v2":
            detail = self.update_editable_inputs(run_id, dataset=dataset)
            profile = self.inspect_dataset_profile(run_id)
            return {"run": detail["run"], "artifact": profile["artifact"], "dataset_profile": profile["profile"], "modality_proposal": profile["modality_proposal"]}
        analysis, ref = parse_dataset(dataset)
        (run / "inputs" / "dataset.csv").write_bytes(dataset)
        self._write(run / "inputs" / "dataset-provenance.json", {"kind": "USER_MEASUREMENT"})
        return {"run": self.get_summary(run_id).model_dump(mode="json"), "dataset": analysis.model_dump(mode="json"), "evidence_ref": ref.model_dump(mode="json")}

    def load_demo_data(self, run_id: str, fixture_root: Path | str) -> RunSummary:
        """Copy only the explicitly labelled demonstration dataset into a draft run."""
        run = self._require_draft(run_id)
        root = Path(fixture_root).resolve()
        methods = (root / "methods.md").read_text(encoding="utf-8")
        dataset = (root / "dataset.csv").read_bytes()
        if len(methods.strip()) < 20:
            raise ValueError("demo methods are invalid")
        parse_dataset(dataset)
        methods_path = run / "inputs" / "methods.md"
        if not methods_path.is_file() or len(methods_path.read_text(encoding="utf-8").strip()) < 20:
            methods_path.write_text(methods, encoding="utf-8")
        (run / "inputs" / "dataset.csv").write_bytes(dataset)
        self._write(run / "inputs" / "dataset-provenance.json", {"kind": "LABELLED_DEMO"})
        return self.get_summary(run_id)

    def explore_draft(self, run_id: str) -> dict[str, Any]:
        """Return a bounded editable draft for Codex exploration without freezing it."""
        run = self._require_draft(run_id)
        draft = self._draft(run)
        sources = [SourceInput.model_validate(item) for item in draft["sources"]]
        result: dict[str, Any] = {
            "run": self.get_summary(run_id).model_dump(mode="json"),
            "frozen": False,
            "advisory": "This is an editable exploration view. Retrieval signals orient review but do not support or block a conclusion. Freeze a packet only when the researcher wants a decision-ready evidence boundary.",
            "claim": draft["claim"],
            "sources": draft["sources"],
            "source_relevance": draft["source_relevance"],
            "methods": draft["methods"],
            "dataset": None,
            "evidence_refs": [ref.model_dump(mode="json") for ref in source_refs(sources)],
        }
        if "retrieval_review" in draft:
            result["retrieval_review"] = draft["retrieval_review"]
        dataset_path = run / "inputs" / "dataset.csv"
        if dataset_path.is_file():
            dataset, data_ref = parse_dataset(dataset_path.read_bytes())
            result["dataset"] = dataset.model_dump(mode="json")
            result["evidence_refs"].append(data_ref.model_dump(mode="json"))
        return result

    def prepare_packet(self, run_id: str) -> dict[str, Any]:
        run = self._require_state(run_id, RunState.DRAFT)
        if self.get_summary(run_id).workflow == "generic_v2":
            return self._prepare_generic_packet(run_id, run)
        self._require_retrieval_adjudication(run)
        claim, sources, methods, raw = self._load_inputs(run)
        if not sources:
            raise ValueError("at least one source is required")
        dataset, data_ref = parse_dataset(raw)
        source_relevance = screen_source_relevance(claim, sources)
        refs = [*source_refs(sources), data_ref]
        source_review = self._selected_source_review(run, sources)
        packet = {
            "claim": claim.model_dump(mode="json"),
            "sources": [source.model_dump(mode="json") for source in sources],
            "source_relevance": [item.model_dump(mode="json") for item in source_relevance],
            "methods": methods,
            "dataset": dataset.model_dump(mode="json"),
            "dataset_provenance": self._dataset_provenance(run),
            "evidence_refs": [ref.model_dump(mode="json") for ref in refs],
        }
        if source_review:
            packet["source_review"] = source_review
        self._write(run / "analysis" / "evidence-packet.json", packet)
        return self._transition(
            run_id,
            RunState.PACKET_READY,
            action="evidence_packet_frozen",
            summary=f"Evidence packet frozen with {len(sources)} selected source(s) and one local dataset.",
        ).model_dump(mode="json")

    def _prepare_generic_packet(self, run_id: str, run: Path) -> dict[str, Any]:
        """Freeze v2 inputs without treating the raw CSV as a scientific fact."""
        claim, sources, methods, raw = self._load_inputs(run)
        if not sources:
            raise ValueError("at least one reviewed direct source is required before freezing")
        if not (run / "analysis" / "source-adjudication.json").is_file():
            raise ValueError("source roles must be reviewed before freezing")
        if self._generic_binding_invalidated(run):
            raise ValueError("method or dataset changed; researcher must reconfirm the dataset binding before freezing")
        artifacts, profiles = self._measurement_artifacts(run)
        bindings = self._artifact_bindings(run)
        if not artifacts:
            raise ValueError("at least one measurement artifact is required before freezing")
        artifact_ids = [artifact.artifact_id for artifact in artifacts]
        artifact_hashes = [artifact.sha256 for artifact in artifacts]
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("measurement artifact IDs must be unique before freezing")
        if len(artifact_hashes) != len(set(artifact_hashes)):
            raise ValueError("duplicate measurement artifact hash before freezing")
        bound_ids = {binding.artifact_id for binding in bindings}
        if bound_ids != set(artifact_ids):
            missing = sorted(set(artifact_ids) - bound_ids)
            raise ValueError(f"researcher must confirm a binding for every measurement artifact before freezing: {', '.join(missing)}")
        artifact = artifacts[0]
        profile = profiles[0]
        binding = bindings[0]
        recipe = self._read(run / "inputs" / "recipe.json")
        routing = MeasurementModalityProposal.model_validate(self._active_measurement_routing(run))
        source_review = self._selected_source_review(run, sources)
        candidate_path = run / "inputs" / "retrieval-candidates.json"
        candidate_sources = self._read(candidate_path) if candidate_path.is_file() else [source.model_dump(mode="json") for source in sources]
        candidate_review = self._read(run / "analysis" / "source-adjudication.json")
        method_ref = EvidenceRef(
            id="method-evidence-frozen", kind="method", artifact_id="method-001",
            locator={"section": "frozen-method-context"}, excerpt=methods[:1000],
            sha256=__import__("hashlib").sha256(methods.encode("utf-8")).hexdigest(),
        )
        packet = {
            "schema_version": 2,
            "claim": claim.model_dump(mode="json"),
            "sources": [source.model_dump(mode="json") for source in sources],
            "source_candidates": candidate_sources,
            "candidate_review": candidate_review,
            "source_relevance": [item.model_dump(mode="json") for item in screen_source_relevance(claim, sources)],
            "methods": methods,
            "artifact": artifact.model_dump(mode="json"),
            "artifacts": [item.model_dump(mode="json") for item in artifacts],
            "dataset_profile": profile.model_dump(mode="json"),
            "dataset_profiles": [item.model_dump(mode="json") for item in profiles],
            "dataset_binding": binding.model_dump(mode="json"),
            "artifact_bindings": [item.model_dump(mode="json") for item in bindings],
            "recipe": recipe,
            "measurement_routing": routing.model_dump(mode="json"),
            "heuristic_modality_signal": self._heuristic_modality_signal(run),
            "dataset_provenance": self._dataset_provenance(run),
            "evidence_refs": [*(item.model_dump(mode="json") for item in source_refs(sources)), method_ref.model_dump(mode="json")],
            "source_review": source_review,
        }
        self._write(run / "analysis" / "evidence-packet.json", packet)
        return self._transition(run_id, RunState.PACKET_READY, action="generic_evidence_packet_frozen", summary=f"Frozen {len(artifacts)} bounded CSV artifact(s), confirmed binding(s), and {len(sources)} reviewed source(s).").model_dump(mode="json")

    def inspect_sources(self, run_id: str, expectations: list[dict[str, Any]]) -> dict[str, Any]:
        run = self._require_state(run_id, RunState.PACKET_READY)
        packet = self._packet(run)
        known_ids = {item["id"] for item in packet["evidence_refs"] if item["kind"] == "source"}
        for expectation in expectations:
            evidence_ids = expectation.get("evidence_ref_ids", [])
            if not evidence_ids or any(item not in known_ids for item in evidence_ids):
                raise ValueError("source inspection must cite supplied source evidence")
        payload = {
            "expectations": expectations,
            "source_relevance": packet.get("source_relevance", []),
            "inspected_at": now_iso(),
        }
        self._write(run / "analysis" / "source-inspection.json", payload)
        return self._transition(
            run_id,
            RunState.SOURCES_INSPECTED,
            action="sources_inspected",
            summary="Codex saved the source inspection for the frozen evidence packet.",
        ).model_dump(mode="json")

    def analyze_dataset(self, run_id: str) -> dict[str, Any]:
        run = self._require_state(run_id, RunState.SOURCES_INSPECTED)
        packet = self._packet(run)
        if self.get_summary(run_id).workflow == "generic_v2":
            payload = {"dataset_profile": packet["dataset_profile"], "analyzed_at": now_iso()}
            self._write(run / "analysis" / "dataset-analysis.json", payload)
            return self._transition(run_id, RunState.DATA_ANALYZED, action="generic_dataset_profile_confirmed", summary="Generic tabular profile is available; materialize deterministic data evidence before adjudicating observations.").model_dump(mode="json")
        payload = {"dataset": packet["dataset"], "analyzed_at": now_iso()}
        self._write(run / "analysis" / "dataset-analysis.json", payload)
        return self._transition(
            run_id,
            RunState.DATA_ANALYZED,
            action="dataset_analyzed",
            summary="Codex saved deterministic analysis of the frozen dataset.",
        ).model_dump(mode="json")

    def materialize_data_evidence(
        self, run_id: str, operation: str, selected_columns: list[str], row_start: int, row_end: int,
        parameters: dict[str, Any] | None = None,
        artifact_id: str | None = None,
    ) -> dict[str, Any]:
        """Materialize a reproducible v2 data fact using the allowlisted engine."""
        run = self._run_dir(run_id)
        if self.get_summary(run_id).workflow != "generic_v2":
            raise ValueError("materialized generic evidence is available through the generic v2 workflow")
        state = self.get_summary(run_id).state
        if state not in {RunState.SOURCES_INSPECTED, RunState.DATA_ANALYZED}:
            raise ValueError("materialize data evidence after source inspection and before alignment adjudication")
        packet = self._packet(run)
        artifacts = [DatasetArtifact.model_validate(item) for item in packet.get("artifacts", [packet["artifact"]])]
        profiles = [DatasetProfile.model_validate(item) for item in packet.get("dataset_profiles", [packet["dataset_profile"]])]
        bindings = [DatasetBinding.model_validate(item) for item in packet.get("artifact_bindings", [packet["dataset_binding"]])]
        by_artifact = {item.artifact_id: item for item in artifacts}
        by_profile = {item.artifact_id: item for item in profiles}
        by_binding = {item.artifact_id: item for item in bindings}
        if artifact_id is None:
            if len(artifacts) != 1:
                raise ValueError("multi-artifact data evidence requires explicit artifact_id")
            artifact_id = artifacts[0].artifact_id
        if artifact_id not in by_artifact:
            raise ValueError("materialized data evidence must target a frozen artifact ID")
        if artifact_id not in by_binding:
            raise ValueError("materialized data evidence requires a confirmed binding for the target artifact")
        raw_path = self._artifact_csv_path(run, artifact_id)
        raw = raw_path.read_bytes() if raw_path.is_file() else (run / "inputs" / "dataset.csv").read_bytes()
        evidence = materialize_evidence(raw, by_artifact[artifact_id], by_profile[artifact_id], by_binding[artifact_id], operation, selected_columns, row_start, row_end, parameters)
        path = run / "analysis" / "data-evidence.json"
        existing = self._read(path).get("evidence", []) if path.is_file() else []
        by_id = {item["evidence_id"]: item for item in existing}
        by_id[evidence.evidence_id] = evidence.model_dump(mode="json")
        self._write(path, {"evidence": list(by_id.values()), "updated_at": now_iso()})
        if state == RunState.SOURCES_INSPECTED:
            self._transition(run_id, RunState.DATA_ANALYZED, action="data_evidence_materialized", summary=f"Materialized {operation} evidence from frozen artifact {artifact_id}.")
        else:
            self._record_event(run, action="data_evidence_materialized", state=RunState.DATA_ANALYZED, summary=f"Materialized {operation} evidence from frozen artifact {artifact_id}.")
        return evidence.model_dump(mode="json")

    def record_signatures(
        self, run_id: str, signatures: list[RequiredSignature]
    ) -> dict[str, Any]:
        """Persist Codex's claim decomposition without changing the frozen packet."""

        run = self._require_state(run_id, RunState.DATA_ANALYZED)
        packet = self._packet(run)
        refs = [EvidenceRef.model_validate(item) for item in packet["evidence_refs"]]
        ref_ids = {ref.id for ref in refs}
        if not 2 <= len(signatures) <= 5:
            raise ValueError("Codex must record between 2 and 5 required signatures")
        ids = [signature.id for signature in signatures]
        if len(ids) != len(set(ids)):
            raise ValueError("required signatures must have unique ids")
        if any(ref_id not in ref_ids for signature in signatures for ref_id in signature.theory_evidence_ref_ids):
            raise ValueError("required signatures reference unsupported evidence")
        self._write(
            run / "analysis" / "signatures.json",
            {"signatures": [item.model_dump(mode="json") for item in signatures], "recorded_at": now_iso()},
        )
        self._record_event(
            run,
            action="signatures_recorded",
            state=RunState.DATA_ANALYZED,
            summary=f"Codex decomposed the claim into {len(signatures)} required signatures.",
        )
        return self.get_convergence_map(run_id).model_dump(mode="json", by_alias=True)

    def record_alignments(
        self, run_id: str, alignments: list[AlignmentAdjudication]
    ) -> dict[str, Any]:
        """Persist one adjudication for every required signature."""

        run = self._require_state(run_id, RunState.DATA_ANALYZED)
        signatures_path = run / "analysis" / "signatures.json"
        if not signatures_path.is_file():
            raise ValueError("record required signatures before alignment adjudications")
        signatures = [RequiredSignature.model_validate(item) for item in self._read(signatures_path)["signatures"]]
        packet = self._packet(run)
        refs = self._run_evidence_refs(run, packet)
        if self.get_summary(run_id).workflow == "generic_v2":
            known = {ref.id: ref for ref in refs}
            for alignment in alignments:
                linked = [known[item] for item in alignment.evidence_ref_ids if item in known]
                if alignment.status in {"Observed", "Contradicted"} and not any(item.id.startswith("data-evidence-") for item in linked):
                    raise ValueError(f"{alignment.status} alignment requires GroundLoop-materialized data evidence")
                if alignment.status == "Confounded" and (not any(item.id.startswith("data-evidence-") for item in linked) or not any(item.kind in {"source", "method"} for item in linked)):
                    raise ValueError("Confounded alignment requires materialized data evidence and a method or source boundary")
        checked = validate_alignment_records(signatures, alignments, refs)
        self._write(
            run / "analysis" / "alignments.json",
            {"alignments": [item.model_dump(mode="json") for item in checked], "recorded_at": now_iso()},
        )
        self._record_event(
            run,
            action="alignment_adjudicated",
            state=RunState.DATA_ANALYZED,
            summary="Codex recorded the claim-to-measurement alignment for every required signature.",
        )
        return self.get_convergence_map(run_id).model_dump(mode="json", by_alias=True)

    def record_control_contract(
        self, run_id: str, control: ControlProposal
    ) -> dict[str, Any]:
        """Persist a single control contract against signature IDs."""

        run = self._require_state(run_id, RunState.DATA_ANALYZED)
        signatures_path = run / "analysis" / "signatures.json"
        alignments_path = run / "analysis" / "alignments.json"
        if not signatures_path.is_file() or not alignments_path.is_file():
            raise ValueError("record signatures and alignments before the control contract")
        signatures = [RequiredSignature.model_validate(item) for item in self._read(signatures_path)["signatures"]]
        signature_ids = {signature.id for signature in signatures}
        target_ids = [*control.closes_signature_ids, *control.leaves_open_signature_ids, *control.signature_ref_ids]
        if not control.closes_signature_ids:
            raise ValueError("control must name at least one signature it closes")
        if any(signature_id not in signature_ids for signature_id in target_ids):
            raise ValueError("control references an unsupported signature")
        if len(control.outcomes) != 2:
            raise ValueError("control requires exactly two outcomes")
        if any(word in (control.experiment + control.confound).lower() for word in ("email", "publish", "execute shell", "curl", "http://")):
            raise ValueError("Control contains an external action")
        self._write(run / "report" / "control.json", {"control": control.model_dump(mode="json", by_alias=True), "validated_at": now_iso()})
        self._transition(
            run_id,
            RunState.CONTROL_VALIDATED,
            action="convergence_control_validated",
            summary="GroundLoop committed one signature-targeted discriminating control.",
        )
        return self.get_convergence_map(run_id).model_dump(mode="json", by_alias=True)

    def reconcile_findings(self, run_id: str, findings: list[Finding]) -> dict[str, Any]:
        run = self._require_state(run_id, RunState.DATA_ANALYZED)
        packet = self._packet(run)
        from .models import DatasetAnalysis, EvidenceRef

        refs = [EvidenceRef.model_validate(item) for item in packet["evidence_refs"]]
        dataset = DatasetAnalysis.model_validate(packet["dataset"])
        checked = validate_findings(findings, refs, dataset)
        payload = {"findings": [item.model_dump(mode="json") for item in checked], "validated_at": now_iso()}
        self._write(run / "report" / "findings.json", payload)
        return self._transition(
            run_id,
            RunState.FINDINGS_VALIDATED,
            action="four_state_findings_validated",
            summary="Codex saved exactly one Established, Observed, Inferred, and Unresolved finding.",
        ).model_dump(mode="json")

    def propose_control(self, run_id: str, control: ControlProposal) -> dict[str, Any]:
        run = self._require_state(run_id, RunState.FINDINGS_VALIDATED)
        finding_data = self._read(run / "report" / "findings.json")["findings"]
        checked = validate_control(control, [Finding.model_validate(item) for item in finding_data])
        self._write(run / "report" / "control.json", {"control": checked.model_dump(mode="json"), "validated_at": now_iso()})
        return self._transition(
            run_id,
            RunState.CONTROL_VALIDATED,
            action="control_first_validated",
            summary="Codex saved one primary ControlFirst experiment with two discriminating outcomes.",
        ).model_dump(mode="json")

    def export_report(self, run_id: str) -> Report | dict[str, Any]:
        run = self._require_state(run_id, RunState.CONTROL_VALIDATED)
        if self.get_summary(run_id).workflow == "generic_v2":
            return self._export_generic_report(run_id, run)
        packet = self._packet(run)
        control = ControlProposal.model_validate(self._read(run / "report" / "control.json")["control"])
        from .models import DatasetAnalysis

        convergence: ConvergenceMap | None = None
        findings: list[Finding] = []
        if (run / "analysis" / "signatures.json").is_file():
            convergence = self.get_convergence_map(run_id).model_copy(update={"freeze_status": "FROZEN", "control": control})
            blockers = [item.signature_id for item in convergence.alignments if item.status != "Observed"]
            while len(blockers) < 2:
                blockers.append("signature-specificity")
            verdict = MechanismVerdict(
                label="MECHANISM_NOT_ESTABLISHED",
                reason=convergence.dominant_gap,
                blocking_finding_ids=blockers[:20],
            )
        else:
            findings = [Finding.model_validate(item) for item in self._read(run / "report" / "findings.json")["findings"]]
            verdict = mechanism_not_established_verdict(findings)
            convergence = legacy_projection(
                Report(
                    run_id=run_id,
                    claim=packet["claim"]["claim"],
                    state=RunState.EXPORTED,
                    findings=findings,
                    control=control,
                    sources=[SourceInput.model_validate(item) for item in packet["sources"]],
                    source_relevance=[],
                    source_review=SourceReview.model_validate(packet["source_review"]) if packet.get("source_review") else None,
                    dataset=DatasetAnalysis.model_validate(packet["dataset"]),
                    dataset_provenance=packet.get("dataset_provenance", "USER_MEASUREMENT"),
                    verdict=verdict,
                    exported_at=now_iso(),
                )
            )
        report = Report(
            run_id=run_id,
            claim=packet["claim"]["claim"],
            state=RunState.EXPORTED,
            findings=findings,
            control=control,
            sources=[SourceInput.model_validate(item) for item in packet["sources"]],
            # Lexical ordering belongs to pre-freeze discovery, never to a report's evidence surface.
            source_relevance=[],
            source_review=SourceReview.model_validate(packet["source_review"]) if packet.get("source_review") else None,
            dataset=DatasetAnalysis.model_validate(packet["dataset"]),
            dataset_provenance=packet.get("dataset_provenance", "USER_MEASUREMENT"),
            verdict=verdict,
            exported_at=now_iso(),
            convergence=convergence,
        )
        self._write(
            run / "report" / "report.json",
            report.model_dump(mode="json", by_alias=True),
        )
        self._transition(
            run_id,
            RunState.EXPORTED,
            action="report_exported",
            summary="Validated report exported from the completed four-state review.",
        )
        return report

    def get_report(self, run_id: str) -> Report | dict[str, Any]:
        if self.get_summary(run_id).state != RunState.EXPORTED:
            raise ValueError("run must be EXPORTED")
        if self.get_summary(run_id).workflow == "generic_v2":
            return self._read(self._run_dir(run_id) / "report" / "report.json")
        payload = self._read(self._run_dir(run_id) / "report" / "report.json")
        # Existing local demo runs predate the explicit verdict contract. They remain
        # readable, but are rendered with the same conservative red-team verdict.
        if "verdict" not in payload:
            findings = [Finding.model_validate(item) for item in payload["findings"]]
            payload["verdict"] = mechanism_not_established_verdict(findings).model_dump(mode="json")
        payload.setdefault("source_relevance", [])
        payload.setdefault("dataset_provenance", self._dataset_provenance(self._run_dir(run_id)))
        report = Report.model_validate(payload)
        if report.convergence is None:
            report = report.model_copy(update={"convergence": legacy_projection(report)})
        return report

    def get_convergence_map(self, run_id: str) -> ConvergenceMap:
        """Return the persisted map, a legacy projection, or an explicit draft preview."""

        run = self._run_dir(run_id)
        if self.get_summary(run_id).workflow == "generic_v2":
            return self._generic_convergence_map(run_id, run)
        report_path = run / "report" / "report.json"
        if report_path.is_file() and self.get_summary(run_id).state == RunState.EXPORTED:
            report = self.get_report(run_id)
            if report.convergence is None:
                raise ValueError("report convergence map is unavailable")
            return report.convergence

        packet_path = run / "analysis" / "evidence-packet.json"
        if packet_path.is_file():
            packet = self._read(packet_path)
            claim = packet["claim"]["claim"]
            method = packet["methods"]
            dataset = DatasetAnalysis.model_validate(packet["dataset"])
            refs = [EvidenceRef.model_validate(item) for item in packet["evidence_refs"]]
            data_ref = next(item.id for item in refs if item.kind == "data")
            source_ref_ids = [item.id for item in refs if item.kind == "source"]
            cmap = preview_map(claim, method, dataset, data_ref, source_ref_ids)
            signatures_path = run / "analysis" / "signatures.json"
            alignments_path = run / "analysis" / "alignments.json"
            if signatures_path.is_file():
                signatures = [RequiredSignature.model_validate(item) for item in self._read(signatures_path)["signatures"]]
                cmap = cmap.model_copy(update={"signatures": signatures})
                if not alignments_path.is_file():
                    cmap = cmap.model_copy(
                        update={
                            "alignments": [
                                AlignmentAdjudication(
                                    signature_id=signature.id,
                                    status="Missing",
                                    rationale="Alignment is awaiting Codex adjudication.",
                                    missing_reason="not_specified_by_theory",
                                )
                                for signature in signatures
                            ]
                        }
                    )
            if alignments_path.is_file():
                cmap = cmap.model_copy(
                    update={"alignments": [AlignmentAdjudication.model_validate(item) for item in self._read(alignments_path)["alignments"]]}
                )
            control_path = run / "report" / "control.json"
            if control_path.is_file():
                cmap = cmap.model_copy(update={"control": ControlProposal.model_validate(self._read(control_path)["control"])})
            if self.get_summary(run_id).state != RunState.DRAFT:
                cmap = cmap.model_copy(update={"freeze_status": "FROZEN"})
            return cmap

        draft = self._draft(run)
        claim = draft.get("claim")
        dataset_path = run / "inputs" / "dataset.csv"
        if not claim or not draft.get("methods") or not dataset_path.is_file():
            raise ValueError("claim, method, and dataset are required for a convergence preview")
        dataset, data_ref = parse_dataset(dataset_path.read_bytes())
        sources = [SourceInput.model_validate(item) for item in draft.get("sources", [])]
        source_refs_for_preview = [item.id for item in source_refs(sources)]
        return preview_map(claim["claim"], draft["methods"], dataset, data_ref.id, source_refs_for_preview)

    def _run_evidence_refs(self, run: Path, packet: dict[str, Any]) -> list[EvidenceRef]:
        refs = [EvidenceRef.model_validate(item) for item in packet["evidence_refs"]]
        evidence_path = run / "analysis" / "data-evidence.json"
        if not evidence_path.is_file():
            return refs
        for raw_evidence in self._read(evidence_path).get("evidence", []):
            evidence = DataEvidence.model_validate(raw_evidence)
            refs.append(EvidenceRef(
                id=evidence.evidence_id, kind="data", artifact_id=evidence.artifact_id,
                locator={"columns": evidence.selected_columns, "row_start": evidence.row_start, "row_end": evidence.row_end},
                excerpt=evidence.fact_text, sha256=evidence.operation_sha256,
            ))
        return refs

    def _generic_default_signatures(self, claim: str, source_ref_ids: list[str]) -> list[RequiredSignature]:
        return [
            RequiredSignature(
                id="signature-measured-response", name="Measured response",
                requirement="The frozen artifact must contain the response named by the claim.",
                expected_observation="A reproducible data-evidence operation identifies the claimed pattern.",
                falsifying_outcome="The materialized operation does not show the claimed pattern.",
                theory_evidence_ref_ids=source_ref_ids[:1],
            ),
            RequiredSignature(
                id="signature-attribution", name="Mechanism attribution",
                requirement="The measured response must be distinguishable from relevant alternatives.",
                expected_observation="The method and control boundary separate the proposed mechanism from alternatives.",
                falsifying_outcome="A compatible alternative remains inseparable in the frozen boundary.",
                theory_evidence_ref_ids=source_ref_ids[:1],
            ),
            RequiredSignature(
                id="signature-specificity", name="Mechanism specificity",
                requirement="A mechanism-specific condition must be measured rather than inferred from a generic trend.",
                expected_observation="A predeclared discriminating signature is present in a capable measurement.",
                falsifying_outcome="Only a non-specific pattern is present or the signature was not measured.",
                theory_evidence_ref_ids=source_ref_ids[:1],
            ),
        ]

    @staticmethod
    def _generic_dominant_gap(signatures: list[RequiredSignature], alignments: list[AlignmentAdjudication]) -> str:
        by_id = {item.id: item for item in signatures}
        priority = {"Contradicted": 0, "Confounded": 1, "Missing": 2, "Observed": 3}
        target = sorted(alignments, key=lambda item: priority[item.status])[0]
        name = by_id[target.signature_id].name
        if target.status == "Confounded":
            detail = (target.alternative_explanation or "a named alternative explanation").strip().rstrip(".;: ")
            if re.search(r"\bremain(?:s|ed|ing)?\b|\binseparable\b|\bcompatible\b", detail, flags=re.IGNORECASE):
                return f"{name} is confounded: {detail}."
            return f"{name} is confounded: {detail}. The alternative remains inseparable within the frozen method and data boundary."
        if target.status == "Missing":
            return f"{name} is missing: {target.missing_reason or 'the required condition was not recorded'} within the frozen boundary."
        if target.status == "Contradicted":
            return f"{name} is contradicted by the cited materialized data evidence."
        return "All currently recorded signatures are observed within the frozen evidence boundary."

    def _generic_convergence_map(self, run_id: str, run: Path) -> ConvergenceMap:
        report_path = run / "report" / "report.json"
        if report_path.is_file() and self.get_summary(run_id).state == RunState.EXPORTED:
            return ConvergenceMap.model_validate(self._read(report_path)["convergence"])
        claim = self._read(run / "inputs" / "claim.json")["claim"]
        methods = (run / "inputs" / "methods.md").read_text(encoding="utf-8")
        source_ids: list[str] = []
        packet_path = run / "analysis" / "evidence-packet.json"
        if packet_path.is_file():
            packet = self._read(packet_path)
            source_ids = [item["id"] for item in packet["evidence_refs"] if item["kind"] == "source"]
        else:
            source_ids = [item.id for item in source_refs([SourceInput.model_validate(item) for item in self._read(run / "inputs" / "sources.json")])]
        signatures_path = run / "analysis" / "signatures.json"
        signatures = [RequiredSignature.model_validate(item) for item in self._read(signatures_path)["signatures"]] if signatures_path.is_file() else self._generic_default_signatures(claim, source_ids)
        alignments_path = run / "analysis" / "alignments.json"
        alignments = [AlignmentAdjudication.model_validate(item) for item in self._read(alignments_path)["alignments"]] if alignments_path.is_file() else [
            AlignmentAdjudication(signature_id=item.id, status="Missing", rationale="Codex has not yet adjudicated this required signature against materialized evidence.", missing_reason="required_condition_not_recorded") for item in signatures
        ]
        control_path = run / "report" / "control.json"
        control = ControlProposal.model_validate(self._read(control_path)["control"]) if control_path.is_file() else None
        return ConvergenceMap(
            claim=claim, measurement_method=methods, signatures=signatures, alignments=alignments,
            dominant_gap=self._generic_dominant_gap(signatures, alignments), control=control,
            freeze_status="FROZEN" if packet_path.is_file() else "DRAFT", recorded_at=now_iso(),
        )

    def _export_generic_report(self, run_id: str, run: Path) -> dict[str, Any]:
        packet = self._packet(run)
        convergence = self._generic_convergence_map(run_id, run).model_copy(update={"freeze_status": "FROZEN"})
        statuses = {item.status for item in convergence.alignments}
        label = "CONTRADICTED_BY_CURRENT_EVIDENCE" if "Contradicted" in statuses else "NOT_ESTABLISHED" if statuses & {"Confounded", "Missing"} else "SUPPORTED_WITHIN_FROZEN_BOUNDARY"
        control = ControlProposal.model_validate(self._read(run / "report" / "control.json")["control"])
        data_evidence = self._read(run / "analysis" / "data-evidence.json").get("evidence", []) if (run / "analysis" / "data-evidence.json").is_file() else []
        report = {
            "schema_version": 2, "run_id": run_id, "claim": packet["claim"]["claim"], "state": "EXPORTED",
            "artifact": packet["artifact"], "dataset_profile": packet["dataset_profile"], "dataset_binding": packet["dataset_binding"],
            "artifacts": packet.get("artifacts", [packet["artifact"]]),
            "dataset_profiles": packet.get("dataset_profiles", [packet["dataset_profile"]]),
            "artifact_bindings": packet.get("artifact_bindings", [packet["dataset_binding"]]),
            "recipe": packet["recipe"], "sources": packet["sources"], "source_review": packet.get("source_review"),
            "source_candidates": packet.get("source_candidates", packet["sources"]), "candidate_review": packet.get("candidate_review"),
            "methods": packet["methods"], "data_evidence": data_evidence, "control": control.model_dump(mode="json", by_alias=True),
            "convergence": convergence.model_dump(mode="json", by_alias=True),
            "verdict": {"label": label, "reason": convergence.dominant_gap, "blocking_signature_ids": [item.signature_id for item in convergence.alignments if item.status != "Observed"]},
            "exported_at": now_iso(),
        }
        self._write(run / "report" / "report.json", report)
        self._transition(run_id, RunState.EXPORTED, action="generic_decision_exported", summary="Evidence-bound generic research decision exported.")
        return report

    def get_packet(self, run_id: str) -> dict[str, Any]:
        return self._packet(self._run_dir(run_id))

    def get_detail(self, run_id: str) -> dict[str, Any]:
        summary = self.get_summary(run_id)
        run = self._run_dir(run_id)
        if summary.workflow == "generic_v2":
            return self._get_generic_detail(summary, run)
        result: dict[str, Any] = {
            "run": summary.model_dump(mode="json"),
            "timeline": self._timeline(run),
        }
        if summary.state == RunState.DRAFT:
            present = [path.name for path in (run / "inputs").iterdir() if path.is_file()]
            result["input_artifacts"] = sorted(present)
            result["draft"] = self._draft(run)
        else:
            result["packet"] = self._packet(run)
        try:
            result["convergence"] = self.get_convergence_map(run_id).model_dump(mode="json", by_alias=True)
        except ValueError:
            pass
        if summary.state == RunState.EXPORTED:
            result["report"] = self.get_report(run_id).model_dump(
                mode="json", by_alias=True
            )
        return result

    def _get_generic_detail(self, summary: RunSummary, run: Path) -> dict[str, Any]:
        result: dict[str, Any] = {"run": summary.model_dump(mode="json"), "timeline": self._timeline(run)}
        if summary.state == RunState.DRAFT:
            binding_invalidated = self._generic_binding_invalidated(run)
            artifacts, profiles = self._measurement_artifacts(run)
            bindings = self._artifact_bindings(run)
            source_candidates_path = run / "inputs" / "retrieval-candidates.json"
            source_candidates = self._read(source_candidates_path) if source_candidates_path.is_file() else self._read(run / "inputs" / "sources.json")
            review_path = run / "analysis" / "source-adjudication.json"
            review = self._read(review_path) if review_path.is_file() else None
            result["input_artifacts"] = sorted(path.name for path in (run / "inputs").iterdir() if path.is_file())
            result["draft"] = {
                "claim": self._read(run / "inputs" / "claim.json"),
                "methods": (run / "inputs" / "methods.md").read_text(encoding="utf-8"),
                "sources": source_candidates,
                "artifact": artifacts[0].model_dump(mode="json"),
                "artifacts": [item.model_dump(mode="json") for item in artifacts],
                "dataset_profile": profiles[0].model_dump(mode="json"),
                "dataset_profiles": [item.model_dump(mode="json") for item in profiles],
                "modality_proposal": self._active_measurement_routing(run),
                "heuristic_modality_signal": self._heuristic_modality_signal(run),
                "retrieval_review": {
                    "provider": _retrieval_provider_label([SourceInput.model_validate(item) for item in source_candidates]) if source_candidates else "Codex-imported candidates",
                    "status": "completed" if review else "required",
                    "candidate_count": len(source_candidates),
                    "direct_source_ids": review.get("direct_source_ids", []) if review else [],
                    "adjudications": review.get("adjudications", []) if review else [],
                },
                "dataset_binding": bindings[0].model_dump(mode="json") if bindings and not binding_invalidated else None,
                "artifact_bindings": [item.model_dump(mode="json") for item in bindings] if not binding_invalidated else [],
                "recipe": self._read(run / "inputs" / "recipe.json") if (run / "inputs" / "recipe.json").is_file() else None,
            }
        else:
            result["packet"] = self._packet(run)
        result["convergence"] = self._generic_convergence_map(summary.run_id, run).model_dump(mode="json", by_alias=True)
        evidence_path = run / "analysis" / "data-evidence.json"
        if evidence_path.is_file():
            result["data_evidence"] = self._read(evidence_path).get("evidence", [])
        if summary.state == RunState.EXPORTED:
            result["report"] = self._read(run / "report" / "report.json")
        return result

    def _draft(self, run: Path) -> dict[str, Any]:
        claim = self._read(run / "inputs" / "claim.json") if (run / "inputs" / "claim.json").is_file() else None
        candidates_path = run / "inputs" / "retrieval-candidates.json"
        candidates = self._read(candidates_path) if candidates_path.is_file() else None
        selected_sources = self._read(run / "inputs" / "sources.json") if (run / "inputs" / "sources.json").is_file() else []
        sources = candidates if candidates is not None else selected_sources
        methods = (run / "inputs" / "methods.md").read_text(encoding="utf-8") if (run / "inputs" / "methods.md").is_file() else ""
        relevance: list[dict[str, Any]] = []
        if claim and sources:
            relevance = [
                item.model_dump(mode="json")
                for item in screen_source_relevance(
                    ClaimInput.model_validate(claim),
                    [SourceInput.model_validate(item) for item in sources],
                )
            ]
        result: dict[str, Any] = {
            "claim": claim,
            "sources": sources,
            "source_relevance": relevance,
            "methods": methods,
            "dataset_ready": (run / "inputs" / "dataset.csv").is_file(),
            "dataset": None,
            "dataset_provenance": self._dataset_provenance(run),
        }
        dataset_path = run / "inputs" / "dataset.csv"
        if dataset_path.is_file():
            dataset, data_ref = parse_dataset(dataset_path.read_bytes())
            result["dataset"] = dataset.model_dump(mode="json")
            result["dataset_evidence_ref"] = data_ref.model_dump(mode="json")
        if candidates is not None:
            review_path = run / "analysis" / "source-adjudication.json"
            review = self._read(review_path) if review_path.is_file() else None
            result["retrieval_review"] = {
                "provider": _retrieval_provider_label(
                    [SourceInput.model_validate(item) for item in candidates]
                ),
                "status": "completed" if review else "required",
                "candidate_count": len(candidates),
                "direct_source_ids": review.get("direct_source_ids", []) if review else [],
                "adjudications": review.get("adjudications", []) if review else [],
            }
        return result

    def _require_retrieval_adjudication(self, run: Path) -> None:
        """Block candidate retrieval from becoming a decision boundary by accident."""
        candidates_path = run / "inputs" / "retrieval-candidates.json"
        if not candidates_path.is_file():
            return
        review_path = run / "analysis" / "source-adjudication.json"
        if not review_path.is_file():
            raise ValueError("Codex must adjudicate all retrieved candidates before the evidence packet can be locked")
        review = self._read(review_path)
        candidates = [SourceInput.model_validate(item) for item in self._read(candidates_path)]
        adjudications = [SourceAdjudication.model_validate(item) for item in review.get("adjudications", [])]
        candidate_ids = {source.id for source in candidates}
        if {item.source_id for item in adjudications} != candidate_ids or len(adjudications) != len(candidate_ids):
            raise ValueError("the saved source adjudication does not cover every retrieved candidate")
        selected_ids = [item.source_id for item in adjudications if item.verdict == "direct"]
        if not selected_ids:
            raise ValueError("the saved source adjudication contains no direct source")
        selected = [SourceInput.model_validate(item) for item in self._read(run / "inputs" / "sources.json")]
        if [source.id for source in selected] != selected_ids:
            raise ValueError("the saved decision sources do not match the direct source adjudication")

    def _dataset_provenance(self, run: Path) -> str:
        provenance_path = run / "inputs" / "dataset-provenance.json"
        if not provenance_path.is_file():
            methods_path = run / "inputs" / "methods.md"
            if methods_path.is_file() and "demonstration run" in methods_path.read_text(encoding="utf-8").lower():
                return "LABELLED_DEMO"
            return "USER_MEASUREMENT"
        kind = self._read(provenance_path).get("kind")
        if kind not in {"USER_MEASUREMENT", "LABELLED_DEMO", "FIXTURE_DEMO"}:
            raise ValueError("dataset provenance is invalid")
        return kind

    def get_report_markdown(self, run_id: str) -> str:
        if self.get_summary(run_id).workflow == "generic_v2":
            return self._generic_report_markdown(run_id)
        report = self.get_report(run_id)
        groups = {status: [item for item in report.findings if item.status == status] for status in ("Established", "Observed", "Inferred", "Unresolved")}
        lines = [
            "# GroundLoop: ControlFirst report",
            "",
            f"**Run:** `{report.run_id}`",
            "",
            "## Claim",
            "",
            report.claim,
            "",
            "## Dataset provenance",
            "",
            report.dataset_provenance.replace("_", " "),
            "",
            "## Mechanism verdict",
            "",
            f"**{report.verdict.label.replace('_', ' ')}** — {report.verdict.reason}",
            f"- Blocking findings: {', '.join(report.verdict.blocking_finding_ids)}",
            "",
            "## Findings",
        ]
        for status, findings in groups.items():
            lines.extend(["", f"### {status}"])
            for finding in findings:
                lines.extend([f"- {finding.statement}", f"  - Evidence: {', '.join(finding.evidence_ref_ids)}"])
                if finding.uncertainty:
                    lines.append(f"  - Uncertainty: {finding.uncertainty}")
                if finding.alternative_explanation:
                    lines.append(f"  - Alternative: {finding.alternative_explanation}")

        convergence = report.convergence
        if convergence:
            lines.extend(
                [
                    "",
                    "## Convergence Map",
                    "",
                    f"- Measurement method: {convergence.measurement_method}",
                    f"- Freeze status: {convergence.freeze_status}",
                    f"- Recorded at: {convergence.recorded_at}",
                    "",
                    "### Required signatures",
                    "",
                ]
            )
            for signature in convergence.signatures:
                lines.extend(
                    [
                        f"- `{signature.id}` — **{signature.name}**",
                        f"  - Requirement: {signature.requirement}",
                        f"  - Expected observation: {signature.expected_observation}",
                        f"  - Falsifying outcome: {signature.falsifying_outcome}",
                        f"  - Theory evidence: {', '.join(signature.theory_evidence_ref_ids) or 'none recorded'}",
                    ]
                )
            lines.extend(["", "### Signature alignments", ""])
            for alignment in convergence.alignments:
                lines.extend(
                    [
                        f"- `{alignment.signature_id}` — **{alignment.status}**",
                        f"  - Rationale: {alignment.rationale}",
                        f"  - Evidence: {', '.join(alignment.evidence_ref_ids) or 'none recorded'}",
                    ]
                )
                if alignment.alternative_explanation:
                    lines.append(f"  - Alternative explanation: {alignment.alternative_explanation}")
                if alignment.missing_reason:
                    lines.append(f"  - Missing reason: {alignment.missing_reason}")
            lines.extend(["", "### Dominant gap", "", convergence.dominant_gap])

            lines.extend(["", "### Source roles", ""])
            if report.source_review:
                for review in report.source_review.adjudications:
                    role = review.role.replace("_", " ") if review.role else "unassigned"
                    lines.extend(
                        [
                            f"- `{review.source_id}` — **{role}** ({review.verdict})",
                            f"  - Rationale: {review.rationale}",
                        ]
                    )
            else:
                lines.append("- No semantic source roles were recorded.")

            lines.extend(["", "### Control contract", ""])
            control = convergence.control
            if control:
                lines.extend(
                    [
                        f"- Confound: {control.confound}",
                        f"- Experiment: {control.experiment}",
                        f"- Preconditions: {', '.join(control.preconditions)}",
                        f"- Closes signatures: {', '.join(control.closes_signature_ids) or 'none recorded'}",
                        f"- Leaves open signatures: {', '.join(control.leaves_open_signature_ids) or 'none recorded'}",
                        f"- Signature references: {', '.join(control.signature_ref_ids) or 'none recorded'}",
                        f"- Priority: {control.priority}",
                        f"- Feasibility: {control.feasibility}",
                        "- Outcomes:",
                    ]
                )
                for outcome in control.outcomes:
                    lines.append(f"  - If {outcome.if_}, then {outcome.then}")
            else:
                lines.append("- CONTROL PENDING — Codex has not committed a control contract.")

        lines.extend(["", "## ControlFirst", "", f"**Confound:** {report.control.confound}", "", report.control.experiment, "", "### Outcomes"])
        for outcome in report.control.outcomes:
            lines.append(f"- If {outcome.if_}, then {outcome.then}")
        lines.extend(["", "## Provenance", ""])
        if report.source_review:
            lines.extend(["### Source selection", ""])
            for review in report.source_review.adjudications:
                lines.append(
                    f"- {review.source_id}: selected after semantic source review — {review.rationale}"
                )
            lines.append("")
        for source in report.sources:
            locator = source.locator.section or (f"page {source.locator.page}" if source.locator.page else "provided excerpt")
            status = "arXiv preprint, not peer-reviewed" if source.retrieval_provider == "arxiv" else "OpenAlex indexed abstract"
            lines.append(f"- {source.id}: {source.title} ({source.year}), {status}, {locator}")
        return "\n".join(lines) + "\n"

    def _generic_report_markdown(self, run_id: str) -> str:
        report = self._read(self._run_dir(run_id) / "report" / "report.json")
        convergence = ConvergenceMap.model_validate(report["convergence"])
        artifacts = [DatasetArtifact.model_validate(item) for item in report.get("artifacts", [report["artifact"]])]
        profiles = {item.artifact_id: item for item in [DatasetProfile.model_validate(item) for item in report.get("dataset_profiles", [report["dataset_profile"]])]}
        bindings = {item.artifact_id: item for item in [DatasetBinding.model_validate(item) for item in report.get("artifact_bindings", [report["dataset_binding"]])]}
        profile = profiles[artifacts[0].artifact_id]
        binding = bindings[artifacts[0].artifact_id]
        candidates = [SourceInput.model_validate(item) for item in report.get("source_candidates", report["sources"])]
        candidate_review = {item["source_id"]: item for item in (report.get("candidate_review") or {}).get("adjudications", [])}
        evidence_artifacts = {item["evidence_id"]: item["artifact_id"] for item in report.get("data_evidence", [])}
        lines = [
            "# GroundLoop research decision", "", f"**Run:** `{report['run_id']}`", "", "## Claim", "", report["claim"], "",
            "## Evidence boundary", "", f"- Artifact: `{report['artifact']['filename']}` (`{report['artifact']['sha256']}`)",
            f"- Profile: {profile.row_count} rows × {profile.column_count} columns; row order preserved.",
            f"- Capability pack: `{report['recipe']['id']}` v{report['recipe']['version']}",
            f"- Binding: X `{binding.x_column_id}`; Y {', '.join(binding.y_column_ids)}", "",
            "## Measurement artifacts", "",
        ]
        for artifact in artifacts:
            artifact_profile = profiles[artifact.artifact_id]
            artifact_binding = bindings.get(artifact.artifact_id)
            binding_text = f"X `{artifact_binding.x_column_id}`; Y {', '.join(artifact_binding.y_column_ids)}" if artifact_binding else "not confirmed"
            lines.extend([
                f"- `{artifact.artifact_id}` — **{artifact.label or 'unlabelled'}**",
                f"  - Filename: `{artifact.filename}`",
                f"  - Provenance: {artifact.provenance}",
                f"  - SHA-256: `{artifact.sha256}`",
                f"  - Profile: {artifact_profile.row_count} rows × {artifact_profile.column_count} columns; row order preserved.",
                f"  - Binding: {binding_text}",
                f"  - Confirmation status: {'confirmed' if artifact_binding else 'required'}",
            ])
        lines.extend([
            "## Literature provenance", "",
            "GroundLoop stored only the bounded excerpts supplied by Codex. It did not fetch any URL or DOI.", "",
        ])
        for source in candidates:
            review = candidate_review.get(source.id, {})
            lines.extend([
                f"- `{source.id}` — **{review.get('verdict', 'unreviewed')}** / {(review.get('role') or 'unassigned').replace('_', ' ')}",
                f"  - {source.title} ({source.year}); provider `{source.retrieval_provider}`; status `{source.publication_status}`",
                f"  - Locator: {source.locator.section or source.locator.page or 'bounded excerpt'}",
                f"  - Excerpt SHA-256: `{source.content_sha256 or 'not recorded'}`",
                f"  - Search query: {source.search_query or 'not recorded'}",
                f"  - Discovery rationale: {source.discovery_rationale or 'not recorded'}",
            ])
        lines.extend([
            "",
            "## Verdict", "", f"**{report['verdict']['label'].replace('_', ' ')}** — {report['verdict']['reason']}", "",
            "## Required signatures", "",
        ])
        for signature in convergence.signatures:
            lines.extend([f"- `{signature.id}` — **{signature.name}**", f"  - Requirement: {signature.requirement}", f"  - Expected observation: {signature.expected_observation}", f"  - Falsifying outcome: {signature.falsifying_outcome}", f"  - Theory evidence: {', '.join(signature.theory_evidence_ref_ids) or 'none recorded'}"])
        lines.extend(["", "## Materialized data evidence", ""])
        for evidence in report.get("data_evidence", []):
            lines.extend([f"- `{evidence['evidence_id']}` — **{evidence['operation']}**", f"  - Artifact: `{evidence['artifact_id']}` (`{evidence['artifact_sha256']}`)", f"  - Selector: columns {', '.join(evidence['selected_columns'])}; rows {evidence['row_start']}–{evidence['row_end']}", f"  - Fact: {evidence['fact_text']}", f"  - Binding hash: `{evidence['binding_sha256']}`", f"  - Operation hash: `{evidence['operation_sha256']}`"])
        lines.extend(["", "## Signature alignments", ""])
        for alignment in convergence.alignments:
            lines.extend([f"- `{alignment.signature_id}` — **{alignment.status}**", f"  - Rationale: {alignment.rationale}", f"  - Evidence: {', '.join(alignment.evidence_ref_ids) or 'none recorded'}"])
            if alignment.artifact_relation_rationale:
                lines.append(f"  - Artifact relation: {alignment.artifact_relation_rationale}")
            if alignment.alternative_explanation:
                lines.append(f"  - Alternative explanation: {alignment.alternative_explanation}")
            if alignment.missing_reason:
                lines.append(f"  - Missing reason: {alignment.missing_reason}")
        lines.extend(["", "## Cross-artifact evidence", ""])
        for alignment in convergence.alignments:
            cited = [item for item in alignment.evidence_ref_ids if item in evidence_artifacts]
            artifact_ids = sorted({evidence_artifacts[item] for item in cited})
            if artifact_ids:
                lines.extend([
                    f"- `{alignment.signature_id}`",
                    f"  - Evidence IDs: {', '.join(cited)}",
                    f"  - Artifact IDs: {', '.join(artifact_ids)}",
                    f"  - Rationale: {alignment.artifact_relation_rationale or alignment.rationale}",
                ])
        lines.extend(["", "## Dominant gap", "", convergence.dominant_gap, "", "## Source roles", ""])
        for review in (report.get("source_review") or {}).get("adjudications", []):
            lines.extend([f"- `{review['source_id']}` — **{(review.get('role') or 'unassigned').replace('_', ' ')}** ({review['verdict']})", f"  - Rationale: {review['rationale']}"])
        control = convergence.control
        lines.extend(["", "## Control contract", ""])
        if control:
            lines.extend([f"- Confound: {control.confound}", f"- Primary experiment: {control.experiment}", f"- Fixed conditions: {', '.join(control.preconditions)}", f"- Closes signatures: {', '.join(control.closes_signature_ids)}", f"- Leaves open signatures: {', '.join(control.leaves_open_signature_ids)}"])
            if control.required_artifact_labels:
                lines.append(f"- Required follow-up artifacts: {', '.join(control.required_artifact_labels)}")
            lines.append("- Outcomes:")
            lines.extend([f"  - If {outcome.if_}, then {outcome.then}" for outcome in control.outcomes])
        return "\n".join(lines) + "\n"

    def _run_dir(self, run_id: str) -> Path:
        try:
            parsed = str(uuid.UUID(run_id))
        except ValueError as exc:
            raise ValueError("invalid run id") from exc
        if parsed != run_id:
            raise ValueError("invalid run id")
        directory = self.root / run_id
        if not directory.is_dir():
            raise FileNotFoundError("run not found")
        return directory

    def _require_draft(self, run_id: str) -> Path:
        return self._require_state(run_id, RunState.DRAFT)

    def _require_state(self, run_id: str, expected: RunState) -> Path:
        run = self._run_dir(run_id)
        if self.get_summary(run_id).state != expected:
            raise ValueError(f"run must be {expected.value}")
        return run

    def _load_inputs(self, run: Path) -> tuple[ClaimInput, list[SourceInput], str, bytes]:
        try:
            claim = ClaimInput.model_validate(self._read(run / "inputs" / "claim.json"))
            sources = [SourceInput.model_validate(item) for item in self._read(run / "inputs" / "sources.json")]
            methods = (run / "inputs" / "methods.md").read_text(encoding="utf-8")
            raw = (run / "inputs" / "dataset.csv").read_bytes()
        except FileNotFoundError as exc:
            raise ValueError("claim, sources, methods, and dataset are required") from exc
        return claim, sources, methods, raw

    def _packet(self, run: Path) -> dict[str, Any]:
        try:
            return self._read(run / "analysis" / "evidence-packet.json")
        except FileNotFoundError as exc:
            raise ValueError("evidence packet is not available") from exc

    def _transition(
        self, run_id: str, state: RunState, *, action: str, summary: str
    ) -> RunSummary:
        previous = self.get_summary(run_id)
        updated = previous.model_copy(update={"state": state})
        run = self._run_dir(run_id)
        self._write(run / "manifest.json", updated.model_dump(mode="json"))
        self._record_event(run, action=action, state=state, summary=summary)
        return updated

    def _selected_source_review(
        self, run: Path, sources: list[SourceInput]
    ) -> dict[str, Any] | None:
        review_path = run / "analysis" / "source-adjudication.json"
        if not review_path.is_file():
            return None
        raw = self._read(review_path)
        selected_ids = {source.id for source in sources}
        adjudications = [
            SourceAdjudication.model_validate(item)
            for item in raw.get("adjudications", [])
            if item.get("source_id") in selected_ids
        ]
        return SourceReview(
            provider=raw["provider"],
            adjudications=adjudications,
            adjudicated_at=raw["adjudicated_at"],
        ).model_dump(mode="json", exclude_none=True)

    def _timeline(self, run: Path) -> list[dict[str, Any]]:
        path = run / "analysis" / "audit-timeline.json"
        if not path.is_file():
            return []
        return [AuditEvent.model_validate(item).model_dump(mode="json") for item in self._read(path)]

    def _record_event(
        self, run: Path, *, action: str, state: RunState, summary: str
    ) -> None:
        path = run / "analysis" / "audit-timeline.json"
        existing = self._read(path) if path.is_file() else []
        existing.append(
            AuditEvent(at=now_iso(), action=action, state=state, summary=summary).model_dump(
                mode="json"
            )
        )
        self._write(path, existing)

    @staticmethod
    def _read(path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write(path: Path, value: Any) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
