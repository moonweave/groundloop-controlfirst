from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from .analysis import parse_dataset, source_refs
from .models import (
    ClaimInput,
    ControlProposal,
    Finding,
    Report,
    RunState,
    RunSummary,
    SourceInput,
    now_iso,
)
from .validation import validate_control, validate_findings


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
        return summary

    def list_runs(self) -> list[RunSummary]:
        result: list[RunSummary] = []
        for manifest in self.root.glob("*/manifest.json"):
            try:
                result.append(RunSummary.model_validate(self._read(manifest)))
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
        return summary

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

    def update_methods(self, run_id: str, methods: str) -> RunSummary:
        run = self._require_draft(run_id)
        if len(methods.strip()) < 20 or len(methods) > 20_000:
            raise ValueError("methods must contain 20–20,000 characters")
        (run / "inputs" / "methods.md").write_text(methods, encoding="utf-8")
        return self.get_summary(run_id)

    def update_dataset(self, run_id: str, dataset: bytes) -> dict[str, Any]:
        run = self._require_draft(run_id)
        analysis, ref = parse_dataset(dataset)
        (run / "inputs" / "dataset.csv").write_bytes(dataset)
        return {"run": self.get_summary(run_id).model_dump(mode="json"), "dataset": analysis.model_dump(mode="json"), "evidence_ref": ref.model_dump(mode="json")}

    def prepare_packet(self, run_id: str) -> dict[str, Any]:
        run = self._require_state(run_id, RunState.DRAFT)
        claim, sources, methods, raw = self._load_inputs(run)
        if not sources:
            raise ValueError("at least one source is required")
        dataset, data_ref = parse_dataset(raw)
        refs = [*source_refs(sources), data_ref]
        packet = {
            "claim": claim.model_dump(mode="json"),
            "sources": [source.model_dump(mode="json") for source in sources],
            "methods": methods,
            "dataset": dataset.model_dump(mode="json"),
            "evidence_refs": [ref.model_dump(mode="json") for ref in refs],
        }
        self._write(run / "analysis" / "evidence-packet.json", packet)
        return self._transition(run_id, RunState.PACKET_READY).model_dump(mode="json")

    def inspect_sources(self, run_id: str, expectations: list[dict[str, Any]]) -> dict[str, Any]:
        run = self._require_state(run_id, RunState.PACKET_READY)
        packet = self._packet(run)
        known_ids = {item["id"] for item in packet["evidence_refs"] if item["kind"] == "source"}
        for expectation in expectations:
            evidence_ids = expectation.get("evidence_ref_ids", [])
            if not evidence_ids or any(item not in known_ids for item in evidence_ids):
                raise ValueError("source inspection must cite supplied source evidence")
        payload = {"expectations": expectations, "inspected_at": now_iso()}
        self._write(run / "analysis" / "source-inspection.json", payload)
        return self._transition(run_id, RunState.SOURCES_INSPECTED).model_dump(mode="json")

    def analyze_dataset(self, run_id: str) -> dict[str, Any]:
        run = self._require_state(run_id, RunState.SOURCES_INSPECTED)
        packet = self._packet(run)
        payload = {"dataset": packet["dataset"], "analyzed_at": now_iso()}
        self._write(run / "analysis" / "dataset-analysis.json", payload)
        return self._transition(run_id, RunState.DATA_ANALYZED).model_dump(mode="json")

    def reconcile_findings(self, run_id: str, findings: list[Finding]) -> dict[str, Any]:
        run = self._require_state(run_id, RunState.DATA_ANALYZED)
        packet = self._packet(run)
        from .models import DatasetAnalysis, EvidenceRef

        refs = [EvidenceRef.model_validate(item) for item in packet["evidence_refs"]]
        dataset = DatasetAnalysis.model_validate(packet["dataset"])
        checked = validate_findings(findings, refs, dataset)
        payload = {"findings": [item.model_dump(mode="json") for item in checked], "validated_at": now_iso()}
        self._write(run / "report" / "findings.json", payload)
        return self._transition(run_id, RunState.FINDINGS_VALIDATED).model_dump(mode="json")

    def propose_control(self, run_id: str, control: ControlProposal) -> dict[str, Any]:
        run = self._require_state(run_id, RunState.FINDINGS_VALIDATED)
        finding_data = self._read(run / "report" / "findings.json")["findings"]
        checked = validate_control(control, [Finding.model_validate(item) for item in finding_data])
        self._write(run / "report" / "control.json", {"control": checked.model_dump(mode="json"), "validated_at": now_iso()})
        return self._transition(run_id, RunState.CONTROL_VALIDATED).model_dump(mode="json")

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
            dataset=DatasetAnalysis.model_validate(packet["dataset"]),
            exported_at=now_iso(),
        )
        self._write(run / "report" / "report.json", report.model_dump(mode="json"))
        self._transition(run_id, RunState.EXPORTED)
        return report

    def get_report(self, run_id: str) -> Report:
        return Report.model_validate(self._read(self._run_dir(run_id) / "report" / "report.json"))

    def get_packet(self, run_id: str) -> dict[str, Any]:
        return self._packet(self._run_dir(run_id))

    def get_detail(self, run_id: str) -> dict[str, Any]:
        summary = self.get_summary(run_id)
        run = self._run_dir(run_id)
        result: dict[str, Any] = {"run": summary.model_dump(mode="json")}
        if summary.state == RunState.DRAFT:
            present = [path.name for path in (run / "inputs").iterdir() if path.is_file()]
            result["input_artifacts"] = sorted(present)
        else:
            result["packet"] = self._packet(run)
        if summary.state == RunState.EXPORTED:
            result["report"] = self.get_report(run_id).model_dump(mode="json")
        return result

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
        for source in report.sources:
            locator = source.locator.section or (f"page {source.locator.page}" if source.locator.page else "provided excerpt")
            lines.append(f"- {source.id}: {source.title} ({source.year}), {locator}")
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

    def _transition(self, run_id: str, state: RunState) -> RunSummary:
        previous = self.get_summary(run_id)
        updated = previous.model_copy(update={"state": state})
        self._write(self._run_dir(run_id) / "manifest.json", updated.model_dump(mode="json"))
        return updated

    @staticmethod
    def _read(path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write(path: Path, value: Any) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
