import pytest

from packages.core.analysis import parse_dataset, screen_source_relevance
from packages.core.models import ClaimInput, Locator, SourceInput


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


def test_source_screen_is_source_specific_and_explicitly_lexical() -> None:
    sources = [
        SourceInput(
            id="src-direct",
            title="Four-wire resistance measurement",
            authors=["Researcher"],
            year=2025,
            url_or_doi="https://doi.org/10.1/direct",
            locator=Locator(section="Abstract"),
            untrusted_content="Contact resistance can distort a two-wire measurement.",
        ),
        SourceInput(
            id="src-limited",
            title="Optical microscopy methods",
            authors=["Researcher"],
            year=2025,
            url_or_doi="https://doi.org/10.1/limited",
            locator=Locator(section="Abstract"),
            untrusted_content="Image focus was assessed with a calibration target.",
        ),
    ]

    screen = screen_source_relevance(ClaimInput(claim="Two-wire resistance demonstrates a bulk conductivity transition."), sources)

    assert screen[0].verdict == "direct"
    assert screen[0].matched_terms == ["resistance", "two-wire"]
    assert screen[1].verdict == "limited"
    assert "not establish" in screen[0].reason
