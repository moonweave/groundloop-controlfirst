from pathlib import Path

from services.mcp_server import main as mcp_main
from packages.core.store import RunStore


def test_update_run_is_atomic_when_a_later_field_is_invalid(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(mcp_main, "store", RunStore(tmp_path / "runs"))
    original_claim = "Does this resistance sweep establish a bulk transition?"
    created = mcp_main.create_run(
        claim=original_claim,
        methods="Two-terminal resistance was recorded during a temperature sweep.",
        dataset_csv="temperature_c,two_wire_resistance_ohm\n20,120\n30,100\n",
    )
    run_id = created["result"]["run"]["run_id"]

    failed = mcp_main.update_run(
        run_id,
        claim="A replacement claim that must not be partially saved.",
        methods="too short",
    )

    assert failed["ok"] is False
    detail = mcp_main.get_run(run_id)
    assert detail["result"]["draft"]["claim"]["claim"] == original_claim
