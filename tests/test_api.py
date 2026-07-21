from pathlib import Path
from datetime import datetime, timedelta
import math

from fastapi.testclient import TestClient
import pytest

from packages.core.store import RunStore
from services.local_api.main import create_app


class FakeDiscovery:
    def search(self, research_question: str, max_results: int = 3):
        from packages.core.models import Locator, SourceInput

        assert research_question == "What explains this resistance change?"
        return [
            SourceInput(
                id="openalex-test-source",
                title="A retrieved source",
                authors=["Researcher"],
                year=2025,
                url_or_doi="https://doi.org/10.1/example",
                locator=Locator(section="OpenAlex indexed abstract"),
                untrusted_content="A retrieved abstract is still untrusted evidence.",
            )
        ]


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


def test_api_update_run_is_atomic_when_dataset_validation_fails(tmp_path: Path) -> None:
    client = TestClient(create_app(RunStore(tmp_path / "runs")))
    original_claim = "Does this resistance sweep establish a bulk transition?"
    created = client.post(
        "/api/runs",
        json={
            "claim": original_claim,
            "methods": "Two-terminal resistance was recorded during a temperature sweep.",
            "dataset_csv": "temperature_c,two_wire_resistance_ohm\n20,120\n30,100\n",
        },
    )
    run_id = created.json()["run"]["run_id"]

    failed = client.patch(
        f"/api/runs/{run_id}",
        json={
            "claim": "A replacement claim that must not be partially saved.",
            "dataset_csv": "not,a supported measurement",
        },
    )

    assert failed.status_code == 422
    detail = client.get(f"/api/runs/{run_id}").json()
    assert detail["draft"]["claim"]["claim"] == original_claim


def test_guided_fixture_opens_an_exported_report_without_mcp(tmp_path: Path) -> None:
    client = TestClient(create_app(RunStore(tmp_path / "runs")))

    created = client.post(
        "/api/runs", json={"fixture_name": "four_wire_contact_control_guided"}
    )

    assert created.status_code == 200
    assert created.json()["state"] == "EXPORTED"
    detail = client.get(f"/api/runs/{created.json()['run_id']}")
    assert detail.status_code == 200
    assert detail.json()["report"]["verdict"]["label"] == "MECHANISM_NOT_ESTABLISHED"
    assert detail.json()["report"]["dataset_provenance"] == "FIXTURE_DEMO"


def test_api_rejects_invalid_run_without_disclosing_path(tmp_path: Path) -> None:
    client = TestClient(create_app(RunStore(tmp_path / "runs")))

    response = client.get("/api/runs/../../etc")

    assert response.status_code == 404


def test_api_only_allows_configured_local_origin(tmp_path: Path) -> None:
    client = TestClient(create_app(RunStore(tmp_path / "runs")))

    response = client.get("/health", headers={"Origin": "http://malicious.example"})

    assert "access-control-allow-origin" not in response.headers


def test_api_gathers_allowlisted_references_into_a_draft_run(tmp_path: Path) -> None:
    client = TestClient(create_app(RunStore(tmp_path / "runs"), discovery=FakeDiscovery()))
    run_id = client.post("/api/runs", json={}).json()["run_id"]

    response = client.post(
        f"/api/runs/{run_id}/gather-references",
        json={"research_question": "What explains this resistance change?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["draft"]["claim"]["claim"] == "What explains this resistance change?"
    assert body["draft"]["sources"][0]["id"] == "openalex-test-source"
    assert body["draft"]["source_relevance"][0]["source_id"] == "openalex-test-source"


def test_api_can_audit_a_hioki_resistance_transient_without_creating_a_run(tmp_path: Path) -> None:
    client = TestClient(create_app(RunStore(tmp_path / "runs")))
    started_at = datetime(2026, 7, 15, 14, 4, 0)
    records = [
        "%s,%s,100,50,%.12g,NO,OFF,OFF,25,24"
        % (
            (started_at + timedelta(seconds=second)).date().isoformat(),
            (started_at + timedelta(seconds=second)).time().isoformat(),
            100 * math.sqrt(second + 1),
        )
        for second in range(12)
    ]
    raw = "\n".join(
        [
            "MODEL,SM7120",
            "DATE,TIME,Voltage[V],V moni[V],Measurement value[ohm],Comparator,Contact Check,V Check,Temperature[deg.],Humidity[%rh]",
            *records,
        ]
    )

    response = client.post(
        "/api/transient-audit",
        files={"file": ("trace.csv", raw, "text/csv")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis"]["decay_exponent"] == pytest.approx(0.5, abs=1e-6)
    assert payload["analysis"]["warnings"] == ["FIT_WINDOW_INCOMPLETE"]
    assert payload["evidence_ref"]["id"] == "transient-001:rows-3-14"
    assert list((tmp_path / "runs").glob("*")) == []
