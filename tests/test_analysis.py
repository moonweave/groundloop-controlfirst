import math
from datetime import datetime, timedelta

import pytest

from packages.core.analysis import (
    parse_dataset,
    parse_hioki_sm7120_transient,
    screen_source_relevance,
)
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


def test_source_screen_matches_simple_morphological_variants() -> None:
    source = SourceInput(
        id="src-trapping",
        title="Charge trapping in conducting polymers",
        authors=["Researcher"],
        year=2025,
        url_or_doi="https://doi.org/10.1/trapping",
        locator=Locator(section="Abstract"),
        untrusted_content="Charge transport is influenced by trapping states in the polymer.",
    )

    screen = screen_source_relevance(ClaimInput(claim="charge trap induced sulfur rich polymer"), [source])

    assert screen[0].verdict == "direct"
    assert screen[0].matched_terms == ["charge", "polymer", "trap"]


def test_hioki_transient_adapter_returns_a_bounded_log_log_diagnostic() -> None:
    started_at = datetime(2026, 7, 15, 14, 4, 0)
    rows = [
        "%s,%s,100,50,%.12g,NO,OFF,OFF,25,24"
        % (
            (started_at + timedelta(seconds=second)).date().isoformat(),
            (started_at + timedelta(seconds=second)).time().isoformat(),
            100 * math.sqrt(second + 1),
        )
        for second in range(101)
    ]
    raw = ("\n".join(
        [
            "MODEL,SM7120",
            "Mode,Resistance,",
            "DATE,TIME,Voltage[V],V moni[V],Measurement value[ohm],Comparator,Contact Check,V Check,Temperature[deg.],Humidity[%rh]",
            *rows,
        ]
    ) + "\n").encode()

    summary, evidence = parse_hioki_sm7120_transient(raw)

    assert summary.row_count == 101
    assert summary.fit_method == "ols_log_log"
    assert summary.fit_window_s == (10.0, 100.0)
    assert summary.decay_exponent == pytest.approx(0.5, abs=1e-6)
    assert summary.log_log_r2 == pytest.approx(1.0, abs=1e-9)
    assert summary.warnings == []
    assert evidence.id == "data-001:rows-4-104"


def test_hioki_transient_adapter_rejects_nonpositive_resistance() -> None:
    raw = (
        "DATE,TIME,Voltage[V],V moni[V],Measurement value[ohm],Comparator,Contact Check,V Check,Temperature[deg.],Humidity[%rh]\n"
        "2026-07-15,14:04:00,100,50,0,NO,OFF,OFF,25,24\n"
    ).encode()

    with pytest.raises(ValueError, match="positive finite resistance"):
        parse_hioki_sm7120_transient(raw)
