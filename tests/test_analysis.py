import pytest

from packages.core.analysis import parse_dataset


def test_parse_dataset_returns_deterministic_summary_and_evidence() -> None:
    summary, evidence = parse_dataset(
        b"temperature_c,two_wire_resistance_ohm\n20,10\n30,8\n40,6\n"
    )

    assert summary.row_count == 3
    assert summary.change_ohm == -4
    assert summary.percent_change == -40
    assert evidence.id == "data-001:rows-2-4"
    assert evidence.locator.row_start == 2


@pytest.mark.parametrize(
    "raw",
    [
        b"temperature_c,resistance\n20,10\n",
        b"temperature_c,two_wire_resistance_ohm\n20,NaN\n",
        b"temperature_c,two_wire_resistance_ohm\n20,0\n30,1\n",
    ],
)
def test_parse_dataset_rejects_invalid_or_unsafe_values(raw: bytes) -> None:
    with pytest.raises(ValueError):
        parse_dataset(raw)
