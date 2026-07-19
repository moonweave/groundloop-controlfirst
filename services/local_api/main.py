from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from packages.core.models import ClaimInput, SourceInput
from packages.core.store import RunStore


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateRunRequest(StrictRequest):
    fixture_name: str | None = Field(default=None, pattern=r"^four_wire_contact_control$")


class SourcesRequest(StrictRequest):
    sources: list[SourceInput] = Field(min_length=1, max_length=3)


class MethodsRequest(StrictRequest):
    methods: str = Field(min_length=20, max_length=20_000)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _store() -> RunStore:
    return RunStore(os.environ.get("GROUNDLOOP_DATA_DIR", str(_repo_root() / ".groundloop" / "runs")))


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail={"code": "RUN_NOT_FOUND", "message": "Run was not found.", "details": []})
    message = str(exc)
    code = "INVALID_STATE" if message.startswith("run must be") else "INPUT_LIMIT_EXCEEDED" if "limit" in message or "MiB" in message else "INVALID_INPUT"
    return HTTPException(status_code=422, detail={"code": code, "message": message, "details": []})


def create_app(store: RunStore | None = None) -> FastAPI:
    app = FastAPI(title="GroundLoop local API", docs_url=None, redoc_url=None)
    app.state.store = store or _store()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[os.environ.get("GROUNDLOOP_WEB_ORIGIN", "http://127.0.0.1:5173")],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT"],
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
                fixture = _repo_root() / "fixtures" / request.fixture_name
                return app.state.store.create_fixture_run(fixture).model_dump(mode="json")
            return app.state.store.create_run().model_dump(mode="json")
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

    @app.post("/api/runs/{run_id}/prepare")
    def prepare(run_id: str) -> dict[str, Any]:
        try:
            app.state.store.prepare_packet(run_id)
            return app.state.store.get_detail(run_id)
        except Exception as exc:
            raise _error(exc) from exc

    @app.get("/api/runs/{run_id}/report")
    def report(run_id: str) -> dict[str, Any]:
        try:
            return app.state.store.get_report(run_id).model_dump(mode="json")
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
