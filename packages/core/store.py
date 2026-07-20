from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from .analysis import parse_dataset, screen_source_relevance, source_refs
from .models import (
    AuditEvent,
    ClaimInput,
    ControlProposal,
    Finding,
    Report,
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
    return "OpenAlex indexed-abstract candidate retrieval"


def _retrieval_summary(sources: list[SourceInput]) -> str:
    openalex_count = sum(source.retrieval_provider == "openalex" for source in sources)
    arxiv_count = sum(source.retrieval_provider == "arxiv" for source in sources)
    parts: list[str] = []
    if openalex_count:
        parts.append(f"{openalex_count} OpenAlex indexed abstract candidate(s)")
    if arxiv_count:
        parts.append(f"{arxiv_count} arXiv preprint candidate(s)")
    return " + ".join(parts) or "No source candidates"


class RunStore:
    """A local-only, typed filesystem store. Callers never provide a file path."""

    def __init__(self, root: Path | str = ".groundloop/runs") -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

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
        self._write(run / "inputs" / "claim.json", claim.model_dump(mode="json"))
        return self.get_summary(run_id)

    def update_sources(self, run_id: str, sources: list[SourceInput]) -> RunSummary:
        run = self._require_draft(run_id)
        if not sources:
            raise ValueError("at least one source is required")
        self._write(run / "inputs" / "sources.json", [source.model_dump(mode="json") for source in sources])
        return self.get_summary(run_id)

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
                "adjudications": [item.model_dump(mode="json") for item in adjudications],
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
        if len(methods.strip()) < 20 or len(methods) > 20_000:
            raise ValueError("methods must contain 20–20,000 characters")
        methods_path = run / "inputs" / "methods.md"
        if not methods_path.is_file() or len(methods_path.read_text(encoding="utf-8").strip()) < 20:
            methods_path.write_text(methods, encoding="utf-8")
        return self.get_summary(run_id)

    def update_dataset(self, run_id: str, dataset: bytes) -> dict[str, Any]:
        run = self._require_draft(run_id)
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
        payload = {"dataset": packet["dataset"], "analyzed_at": now_iso()}
        self._write(run / "analysis" / "dataset-analysis.json", payload)
        return self._transition(
            run_id,
            RunState.DATA_ANALYZED,
            action="dataset_analyzed",
            summary="Codex saved deterministic analysis of the frozen dataset.",
        ).model_dump(mode="json")

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

    def export_report(self, run_id: str) -> Report:
        run = self._require_state(run_id, RunState.CONTROL_VALIDATED)
        packet = self._packet(run)
        findings = [Finding.model_validate(item) for item in self._read(run / "report" / "findings.json")["findings"]]
        control = ControlProposal.model_validate(self._read(run / "report" / "control.json")["control"])
        from .models import DatasetAnalysis

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
            verdict=mechanism_not_established_verdict(findings),
            exported_at=now_iso(),
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

    def get_report(self, run_id: str) -> Report:
        if self.get_summary(run_id).state != RunState.EXPORTED:
            raise ValueError("run must be EXPORTED")
        payload = self._read(self._run_dir(run_id) / "report" / "report.json")
        # Existing local demo runs predate the explicit verdict contract. They remain
        # readable, but are rendered with the same conservative red-team verdict.
        if "verdict" not in payload:
            findings = [Finding.model_validate(item) for item in payload["findings"]]
            payload["verdict"] = mechanism_not_established_verdict(findings).model_dump(mode="json")
        payload.setdefault("source_relevance", [])
        payload.setdefault("dataset_provenance", self._dataset_provenance(self._run_dir(run_id)))
        return Report.model_validate(payload)

    def get_packet(self, run_id: str) -> dict[str, Any]:
        return self._packet(self._run_dir(run_id))

    def get_detail(self, run_id: str) -> dict[str, Any]:
        summary = self.get_summary(run_id)
        run = self._run_dir(run_id)
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
        if summary.state == RunState.EXPORTED:
            result["report"] = self.get_report(run_id).model_dump(
                mode="json", by_alias=True
            )
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
            "dataset_provenance": self._dataset_provenance(run),
        }
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
        ).model_dump(mode="json")

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
