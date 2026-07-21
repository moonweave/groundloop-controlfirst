from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from packages.core.analysis import parse_hioki_sm7120_transient
from packages.core.discovery import DualIndexReferenceDiscovery, ReferenceDiscovery, ReferenceDiscoveryError
from packages.core.models import (
    AlignmentAdjudication,
    ClaimInput,
    ControlProposal,
    DatasetBinding,
    MeasurementModalityProposal,
    RequiredSignature,
    SourceAdjudication,
    SourceInput,
)
from packages.core.store import RunStore


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateRunRequest(StrictRequest):
    fixture_name: str | None = Field(
        default=None,
        pattern=r"^(?:four_wire_contact_control(?:_guided)?|generic_spectrum)$",
    )
    claim: str | None = Field(default=None, min_length=1, max_length=1000)
    methods: str | None = Field(default=None, min_length=20, max_length=20_000)
    dataset_csv: str | None = Field(default=None, min_length=1, max_length=5 * 1024 * 1024)
    sources: list[SourceInput] | None = Field(default=None, max_length=20)


class UpdateRunRequest(StrictRequest):
    claim: str | None = Field(default=None, min_length=1, max_length=1000)
    methods: str | None = Field(default=None, min_length=20, max_length=20_000)
    dataset_csv: str | None = Field(default=None, min_length=1, max_length=5 * 1024 * 1024)
    sources: list[SourceInput] | None = Field(default=None, max_length=20)


class SourcesRequest(StrictRequest):
    sources: list[SourceInput] = Field(min_length=1, max_length=3)


class MethodsRequest(StrictRequest):
    methods: str = Field(min_length=20, max_length=20_000)


class GatherReferencesRequest(StrictRequest):
    research_question: str = Field(min_length=10, max_length=1000)


class SourceReviewsRequest(StrictRequest):
    adjudications: list[SourceAdjudication] = Field(min_length=1, max_length=20)


class SignaturesRequest(StrictRequest):
    signatures: list[RequiredSignature] = Field(min_length=2, max_length=5)


class AlignmentsRequest(StrictRequest):
    alignments: list[AlignmentAdjudication] = Field(min_length=2, max_length=5)


class ControlContractRequest(StrictRequest):
    control: ControlProposal


class GenericCreateRunRequest(StrictRequest):
    claim: str = Field(min_length=1, max_length=1000)
    methods: str = Field(min_length=20, max_length=20_000)
    dataset_csv: str = Field(min_length=1, max_length=5 * 1024 * 1024)
    sources: list[SourceInput] = Field(default_factory=list, max_length=20)
    filename: str = Field(default="dataset.csv", min_length=1, max_length=255)


class DatasetBindingRequest(StrictRequest):
    binding: DatasetBinding
    recipe: str = Field(default="generic", min_length=1, max_length=80)


class MeasurementModalityRequest(StrictRequest):
    proposal: MeasurementModalityProposal


class DataEvidenceRequest(StrictRequest):
    operation: str = Field(min_length=1, max_length=80)
    selected_columns: list[str] = Field(min_length=1, max_length=8)
    row_start: int = Field(ge=2)
    row_end: int = Field(ge=2)
    parameters: dict[str, Any] = Field(default_factory=dict)


class SourceInspectionRequest(StrictRequest):
    expectations: list[dict[str, Any]] = Field(min_length=1, max_length=20)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _store() -> RunStore:
    return RunStore(os.environ.get("GROUNDLOOP_DATA_DIR", str(_repo_root() / ".groundloop" / "runs")))


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND", "message": "Run was not found.", "details": []})
    if isinstance(exc, ReferenceDiscoveryError):
        no_match = str(exc).startswith("No measurement-relevant") or str(exc).startswith("No indexed abstracts")
        return HTTPException(
            status_code=422 if no_match else 503,
            detail={
                "code": "NO_MEASUREMENT_RELEVANT_SOURCE" if no_match else "REFERENCE_DISCOVERY_UNAVAILABLE",
                "message": str(exc),
                "details": [],
            },
        )
    message = str(exc)
    code = "INVALID_STATE" if message.startswith("run must be") else "INPUT_LIMIT_EXCEEDED" if "limit" in message or "MiB" in message else "INVALID_INPUT"
    return HTTPException(status_code=422, detail={"code": code, "message": message, "details": []})


def create_app(store: RunStore | None = None, discovery: ReferenceDiscovery | None = None) -> FastAPI:
    app = FastAPI(title="GroundLoop local API", docs_url=None, redoc_url=None)
    app.state.store = store or _store()
    app.state.discovery = discovery or DualIndexReferenceDiscovery()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[os.environ.get("GROUNDLOOP_WEB_ORIGIN", "http://127.0.0.1:5173")],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/runs")
    def list_runs() -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in app.state.store.list_runs()]

    @app.post("/api/runs")
    def create_run(request: CreateRunRequest) -> dict[str, Any]:
        try:
            if request.fixture_name:
                fixture = _repo_root() / "fixtures" / "four_wire_contact_control"
                if request.fixture_name == "generic_spectrum":
                    return app.state.store.create_generic_fixture_run(_repo_root() / "fixtures" / "generic_spectrum")
                if request.fixture_name == "four_wire_contact_control_guided":
                    return app.state.store.create_guided_demo_run(fixture).model_dump(mode="json")
                return app.state.store.create_fixture_run(fixture).model_dump(mode="json")
            if request.claim or request.methods or request.dataset_csv:
                if not request.claim or not request.methods or not request.dataset_csv:
                    raise ValueError("Codex-created runs require claim, methods, and dataset_csv together")
                return app.state.store.create_codex_run(
                    ClaimInput(claim=request.claim),
                    request.methods,
                    request.dataset_csv.encode("utf-8"),
                    request.sources,
                )
            return app.state.store.create_run().model_dump(mode="json")
        except Exception as exc:
            raise _error(exc) from exc

    @app.post("/api/generic/runs")
    def create_generic_run(request: GenericCreateRunRequest) -> dict[str, Any]:
        try:
            return app.state.store.create_generic_run(
                ClaimInput(claim=request.claim), request.methods, request.dataset_csv.encode("utf-8"),
                request.sources, filename=request.filename,
            )
        except Exception as exc:
            raise _error(exc) from exc

    @app.get("/api/generic/runs/{run_id}/dataset-profile")
    def dataset_profile(run_id: str) -> dict[str, Any]:
        try:
            return app.state.store.inspect_dataset_profile(run_id)
        except Exception as exc:
            raise _error(exc) from exc

    @app.post("/api/generic/runs/{run_id}/modality")
    def modality(run_id: str) -> dict[str, Any]:
        try:
            return app.state.store.propose_measurement_modality(run_id)
        except Exception as exc:
            raise _error(exc) from exc

    @app.post("/api/generic/runs/{run_id}/measurement-modality")
    def record_measurement_modality(run_id: str, request: MeasurementModalityRequest) -> dict[str, Any]:
        try:
            return app.state.store.record_measurement_modality(run_id, request.proposal)
        except Exception as exc:
            raise _error(exc) from exc

    @app.post("/api/generic/runs/{run_id}/binding")
    def binding(run_id: str, request: DatasetBindingRequest) -> dict[str, Any]:
        try:
            return app.state.store.set_dataset_binding(run_id, request.binding, request.recipe)
        except Exception as exc:
            raise _error(exc) from exc

    @app.post("/api/generic/runs/{run_id}/source-inspection")
    def generic_source_inspection(run_id: str, request: SourceInspectionRequest) -> dict[str, Any]:
        try:
            return app.state.store.inspect_sources(run_id, request.expectations)
        except Exception as exc:
            raise _error(exc) from exc

    @app.post("/api/generic/runs/{run_id}/analyze")
    def generic_analyze(run_id: str) -> dict[str, Any]:
        try:
            return app.state.store.analyze_dataset(run_id)
        except Exception as exc:
            raise _error(exc) from exc

    @app.post("/api/generic/runs/{run_id}/data-evidence")
    def generic_data_evidence(run_id: str, request: DataEvidenceRequest) -> dict[str, Any]:
        try:
            return app.state.store.materialize_data_evidence(run_id, request.operation, request.selected_columns, request.row_start, request.row_end, request.parameters)
        except Exception as exc:
            raise _error(exc) from exc

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        try:
            return app.state.store.get_detail(run_id)
        except Exception as exc:
            raise _error(exc) from exc

    @app.put("/api/runs/{run_id}/claim")
    def update_claim(run_id: str, request: ClaimInput) -> dict[str, Any]:
        try:
            return app.state.store.update_claim(run_id, request).model_dump(mode="json")
        except Exception as exc:
            raise _error(exc) from exc

    @app.patch("/api/runs/{run_id}")
    def update_run(run_id: str, request: UpdateRunRequest) -> dict[str, Any]:
        try:
            return app.state.store.update_editable_inputs(
                run_id,
                ClaimInput(claim=request.claim) if request.claim is not None else None,
                request.methods,
                request.dataset_csv.encode("utf-8") if request.dataset_csv is not None else None,
                request.sources,
            )
        except Exception as exc:
            raise _error(exc) from exc

    @app.post("/api/runs/{run_id}/gather-references")
    def gather_references(run_id: str, request: GatherReferencesRequest) -> dict[str, Any]:
        try:
            sources = app.state.discovery.search(request.research_question)
            app.state.store.save_research_setup(run_id, ClaimInput(claim=request.research_question), sources)
            return app.state.store.get_detail(run_id)
        except Exception as exc:
            raise _error(exc) from exc

    @app.post("/api/runs/{run_id}/sources")
    def update_sources(run_id: str, request: SourcesRequest) -> dict[str, Any]:
        try:
            return app.state.store.update_sources(run_id, request.sources).model_dump(mode="json")
        except Exception as exc:
            raise _error(exc) from exc

    @app.put("/api/runs/{run_id}/methods")
    def update_methods(run_id: str, request: MethodsRequest) -> dict[str, Any]:
        try:
            return app.state.store.update_methods(run_id, request.methods).model_dump(mode="json")
        except Exception as exc:
            raise _error(exc) from exc

    @app.post("/api/runs/{run_id}/dataset")
    async def update_dataset(run_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
        try:
            if file.content_type not in {"text/csv", "application/csv", "application/vnd.ms-excel", "application/octet-stream"}:
                raise ValueError("dataset must be a CSV upload")
            raw = await file.read(5 * 1024 * 1024 + 1)
            return app.state.store.update_dataset(run_id, raw)
        except Exception as exc:
            raise _error(exc) from exc

    @app.post("/api/transient-audit")
    async def audit_hioki_transient(file: UploadFile = File(...)) -> dict[str, Any]:
        """Return a bounded SM7120 V/R diagnostic without persisting raw research data."""
        try:
            if file.content_type not in {"text/csv", "application/csv", "application/vnd.ms-excel", "application/octet-stream"}:
                raise ValueError("dataset must be a CSV upload")
            raw = await file.read(5 * 1024 * 1024 + 1)
            analysis, evidence_ref = parse_hioki_sm7120_transient(raw, artifact_id="transient-001")
            return {
                "analysis": analysis.model_dump(mode="json"),
                "evidence_ref": evidence_ref.model_dump(mode="json"),
                "scope": "Single Hioki SM7120 resistance transient only; the reported exponent is an OLS diagnostic, not a mechanism conclusion or replacement for a separately configured robust fit.",
            }
        except Exception as exc:
            raise _error(exc) from exc

    @app.post("/api/runs/{run_id}/demo-data")
    def load_demo_data(run_id: str) -> dict[str, Any]:
        try:
            fixture = _repo_root() / "fixtures" / "four_wire_contact_control"
            app.state.store.load_demo_data(run_id, fixture)
            return app.state.store.get_detail(run_id)
        except Exception as exc:
            raise _error(exc) from exc

    @app.post("/api/runs/{run_id}/prepare")
    def prepare(run_id: str) -> dict[str, Any]:
        try:
            app.state.store.prepare_packet(run_id)
            return app.state.store.get_detail(run_id)
        except Exception as exc:
            raise _error(exc) from exc

    @app.post("/api/runs/{run_id}/freeze")
    def freeze(run_id: str) -> dict[str, Any]:
        try:
            app.state.store.prepare_packet(run_id)
            return app.state.store.get_detail(run_id)
        except Exception as exc:
            raise _error(exc) from exc

    @app.post("/api/runs/{run_id}/source-reviews")
    def record_source_reviews(run_id: str, request: SourceReviewsRequest) -> dict[str, Any]:
        try:
            app.state.store.record_source_reviews(run_id, request.adjudications)
            return app.state.store.get_detail(run_id)
        except Exception as exc:
            raise _error(exc) from exc

    @app.post("/api/runs/{run_id}/signatures")
    def record_signatures(run_id: str, request: SignaturesRequest) -> dict[str, Any]:
        try:
            return app.state.store.record_signatures(run_id, request.signatures)
        except Exception as exc:
            raise _error(exc) from exc

    @app.post("/api/runs/{run_id}/alignments")
    def record_alignments(run_id: str, request: AlignmentsRequest) -> dict[str, Any]:
        try:
            return app.state.store.record_alignments(run_id, request.alignments)
        except Exception as exc:
            raise _error(exc) from exc

    @app.post("/api/runs/{run_id}/control-contract")
    def record_control_contract(run_id: str, request: ControlContractRequest) -> dict[str, Any]:
        try:
            return app.state.store.record_control_contract(run_id, request.control)
        except Exception as exc:
            raise _error(exc) from exc

    @app.get("/api/runs/{run_id}/convergence")
    def convergence(run_id: str) -> dict[str, Any]:
        try:
            return app.state.store.get_convergence_map(run_id).model_dump(mode="json", by_alias=True)
        except Exception as exc:
            raise _error(exc) from exc

    @app.get("/api/runs/{run_id}/report")
    def report(run_id: str) -> dict[str, Any]:
        try:
            payload = app.state.store.get_report(run_id)
            return payload if isinstance(payload, dict) else payload.model_dump(mode="json", by_alias=True)
        except Exception as exc:
            raise _error(exc) from exc

    @app.get("/api/runs/{run_id}/report.md", response_class=PlainTextResponse)
    def report_markdown(run_id: str) -> str:
        try:
            return app.state.store.get_report_markdown(run_id)
        except Exception as exc:
            raise _error(exc) from exc

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("services.local_api.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    run()
