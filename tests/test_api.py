from pathlib import Path

from fastapi.testclient import TestClient

from packages.core.store import RunStore
from services.local_api.main import create_app


def test_fixture_can_be_prepared_through_local_api(tmp_path: Path) -> None:
    client = TestClient(create_app(RunStore(tmp_path / "runs")))

    created = client.post("/api/runs", json={"fixture_name": "four_wire_contact_control"})
    assert created.status_code == 200
    run_id = created.json()["run_id"]

    prepared = client.post(f"/api/runs/{run_id}/prepare")
    assert prepared.status_code == 200
    body = prepared.json()
    assert body["run"]["state"] == "PACKET_READY"
    assert body["packet"]["dataset"]["row_count"] == 8


def test_api_rejects_invalid_run_without_disclosing_path(tmp_path: Path) -> None:
    client = TestClient(create_app(RunStore(tmp_path / "runs")))

    response = client.get("/api/runs/../../etc")

    assert response.status_code == 404


def test_api_only_allows_configured_local_origin(tmp_path: Path) -> None:
    client = TestClient(create_app(RunStore(tmp_path / "runs")))

    response = client.get("/health", headers={"Origin": "http://malicious.example"})

    assert "access-control-allow-origin" not in response.headers
