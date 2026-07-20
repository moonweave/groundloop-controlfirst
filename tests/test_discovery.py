import pytest
from xml.etree import ElementTree

from packages.core.discovery import ArxivReferenceDiscovery, DualIndexReferenceDiscovery, OpenAlexReferenceDiscovery, ReferenceDiscoveryError, _arxiv_focus_terms, _balanced_sources, _is_off_topic_domain, _rank_sources_for_claim, _restore_abstract, _safe_search_terms, _search_query_variants
from packages.core.models import Locator, SourceInput


def test_restores_openalex_inverted_abstract() -> None:
    assert _restore_abstract({"Evidence": [1], "First": [0], "matters.": [2]}) == "First Evidence matters."


def test_sanitises_openalex_wildcard_punctuation() -> None:
    assert _safe_search_terms("Does this control work? Maybe*") == "control work maybe"


def test_extracts_meaningful_search_terms_from_a_research_question() -> None:
    assert _safe_search_terms("What measurement control can distinguish contact resistance from a bulk conductivity change?") == "control distinguish contact resistance bulk conductivity change"


def test_arxiv_query_prefers_measurement_and_confound_terms_over_prose() -> None:
    assert _arxiv_focus_terms(
        "Does a two-wire resistance decrease demonstrate a bulk conductivity transition, or can contact resistance explain it?"
    ) == ["contact", "resistance"]


def test_arxiv_query_infers_contact_resistance_for_a_two_wire_claim() -> None:
    assert _arxiv_focus_terms(
        "The temperature-dependent two-wire resistance decrease demonstrates a bulk conductivity transition."
    ) == ["contact", "resistance"]


def test_rejects_thermal_nanofluid_result_for_an_electrical_two_wire_claim() -> None:
    claim = "The temperature-dependent two-wire resistance decrease demonstrates a bulk conductivity transition."
    assert _is_off_topic_domain(
        "Thermal interfacial resistance and nanolayer effect on the thermal conductivity of Al2O3-CO2 nanofluid",
        "Heat transfer in a nanofluid changes thermal resistance and thermal conductivity.",
        claim,
    )
    assert not _is_off_topic_domain(
        "Four-point probe measurements of electrical resistivity",
        "Voltage sensing separates contact resistance from the electrical measurement path.",
        claim,
    )


def test_broadens_an_over_specific_query_without_changing_the_retrieval_target() -> None:
    assert _search_query_variants("charge trapping can be induced at sulfurl rich polymer") == [
        "charge trapping induced sulfurl rich polymer",
        "charge trapping induced sulfurl rich",
        "charge trapping induced sulfurl",
        "charge trapping induced",
    ]


def test_rejects_adjacent_battery_results_when_the_claim_is_not_about_batteries() -> None:
    assert _is_off_topic_domain(
        "A sulfur host for lithium-sulfur batteries",
        "Lithium polysulfide cathode performance is improved.",
        "charge trap induced sulfur rich polymer",
    )
    assert not _is_off_topic_domain(
        "A sulfur host for lithium-sulfur batteries",
        "Lithium polysulfide cathode performance is improved.",
        "lithium sulfur battery polymer cathode",
    )


def test_discovers_only_entries_with_a_provenance_bearing_abstract() -> None:
    discovery = OpenAlexReferenceDiscovery()
    source = discovery._source(
        {
            "id": "https://openalex.org/W1",
            "doi": "https://doi.org/10.1/example",
            "display_name": "Measurement controls matter",
            "authorships": [{"author": {"display_name": "A. Researcher"}}],
            "publication_year": 2025,
            "abstract_inverted_index": {"Controls": [1], "matter.": [2], "Measurement": [0]},
        }
    )

    assert source is not None
    assert source.id.startswith("openalex-")
    assert source.url_or_doi == "https://doi.org/10.1/example"
    assert source.untrusted_content == "Measurement Controls matter."
    assert source.locator.section == "OpenAlex indexed abstract · retrieval query: "
    assert source.retrieval_provider == "openalex"
    assert source.publication_status == "indexed_abstract"


def test_marks_arxiv_candidates_as_preprints() -> None:
    entry = ElementTree.fromstring(
        """<entry xmlns=\"http://www.w3.org/2005/Atom\" xmlns:arxiv=\"http://arxiv.org/schemas/atom\">
        <id>http://arxiv.org/abs/2607.00001</id><published>2026-07-20T00:00:00Z</published>
        <title>Four-point measurements separate contact resistance</title>
        <summary>Four-point resistance measurements distinguish contact contributions from bulk conductivity.</summary>
        <author><name>A. Researcher</name></author><arxiv:primary_category term=\"cond-mat.mtrl-sci\" />
        </entry>"""
    )

    source = ArxivReferenceDiscovery._source(
        entry,
        {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"},
        "Does four-point resistance separate contact contributions from bulk conductivity?",
    )

    assert source is not None
    assert source.id.startswith("arxiv-")
    assert source.retrieval_provider == "arxiv"
    assert source.publication_status == "preprint"
    assert source.locator.section == "arXiv preprint abstract · category: cond-mat.mtrl-sci"


def test_keeps_ranked_candidates_ahead_of_provider_diversity() -> None:
    openalex = SourceInput(
        id="openalex-direct", title="Four-point resistance measurement", authors=["Researcher"], year=2025,
        url_or_doi="https://doi.org/10.1/openalex", locator=Locator(section="Abstract"),
        untrusted_content="Four-point resistance separates contact resistance from bulk conductivity.",
    )
    second_openalex = SourceInput(
        id="openalex-direct-2", title="Four-wire voltage sensing", authors=["Researcher"], year=2024,
        url_or_doi="https://doi.org/10.1/openalex-2", locator=Locator(section="Abstract"),
        untrusted_content="Four-wire sensing excludes lead resistance from a bulk resistivity measurement.",
    )
    arxiv_contextual = SourceInput(
        id="arxiv-contextual", title="Preprint on material conductivity", authors=["Researcher"], year=2026,
        url_or_doi="https://arxiv.org/abs/2607.00001", locator=Locator(section="Abstract"),
        untrusted_content="A material conductivity trend is discussed without a contact-resistance control.",
        retrieval_provider="arxiv", publication_status="preprint",
    )

    selected = _balanced_sources([openalex, second_openalex, arxiv_contextual], 2)

    assert [source.id for source in selected] == ["openalex-direct", "openalex-direct-2"]


def test_dual_index_survives_one_index_being_unavailable() -> None:
    source = SourceInput(
        id="arxiv-direct", title="Four-point resistance control", authors=["Researcher"], year=2026,
        url_or_doi="https://arxiv.org/abs/2607.00001", locator=Locator(section="Abstract"),
        untrusted_content="Four-point resistance distinguishes contact contributions from bulk conductivity.",
        retrieval_provider="arxiv", publication_status="preprint",
    )

    class UnavailableIndex:
        def search(self, research_question: str, max_results: int = 3) -> list[SourceInput]:
            raise ReferenceDiscoveryError("index unavailable")

    class AvailableIndex:
        def search(self, research_question: str, max_results: int = 3) -> list[SourceInput]:
            return [source]

    discovery = DualIndexReferenceDiscovery(openalex=UnavailableIndex(), arxiv=AvailableIndex())

    assert discovery.search("Does four-point resistance separate contact contributions from bulk conductivity?") == [source]


def test_ranks_direct_candidates_before_context_only_results() -> None:
    contextual = SourceInput(
        id="contextual",
        title="Polymer photocatalysis",
        authors=["Researcher"],
        year=2025,
        url_or_doi="https://doi.org/10.1/contextual",
        locator=Locator(section="Abstract"),
        untrusted_content="Polymer materials are used for visible-light photocatalysis.",
    )
    direct = SourceInput(
        id="direct",
        title="Charge trapping in conducting polymers",
        authors=["Researcher"],
        year=2025,
        url_or_doi="https://doi.org/10.1/direct",
        locator=Locator(section="Abstract"),
        untrusted_content="Charge traps influence transport in the polymer.",
    )

    ranked = _rank_sources_for_claim(
        "charge trap induced sulfur rich polymer", [contextual, direct]
    )

    assert [source.id for source in ranked] == ["direct", "contextual"]


def test_keeps_limited_candidates_for_exploration_but_ranks_them_last() -> None:
    direct = SourceInput(
        id="direct",
        title="Charge trapping in conducting polymers",
        authors=["Researcher"],
        year=2025,
        url_or_doi="https://doi.org/10.1/direct",
        locator=Locator(section="Abstract"),
        untrusted_content="Charge traps influence transport in the polymer.",
    )
    limited = SourceInput(
        id="limited",
        title="Microscopy of disordered thin films",
        authors=["Researcher"],
        year=2025,
        url_or_doi="https://doi.org/10.1/limited",
        locator=Locator(section="Abstract"),
        untrusted_content="Microscopy resolved local film morphology.",
    )

    ranked = _rank_sources_for_claim(
        "charge trap induced sulfur rich polymer", [limited, direct]
    )

    assert [source.id for source in ranked] == ["direct", "limited"]


def test_discovery_rejects_candidates_without_a_direct_measurement_match(monkeypatch: pytest.MonkeyPatch) -> None:
    discovery = OpenAlexReferenceDiscovery()
    contextual = SourceInput(
        id="contextual",
        title="Antibiotic resistance in a cave microbiome",
        authors=["Researcher"],
        year=2025,
        url_or_doi="https://doi.org/10.1/contextual",
        locator=Locator(section="Abstract"),
        untrusted_content="Resistance was observed in bacterial isolates.",
    )
    monkeypatch.setattr(
        OpenAlexReferenceDiscovery,
        "_search_query",
        lambda self, query, max_results, research_question: [contextual],
    )

    with pytest.raises(ReferenceDiscoveryError, match="measurement-relevant"):
        discovery.search("Does this two-wire resistance change establish a bulk transition?")


def test_discovery_uses_one_semantic_measurement_brief(monkeypatch: pytest.MonkeyPatch) -> None:
    discovery = OpenAlexReferenceDiscovery()
    direct = SourceInput(
        id="direct",
        title="Two-wire and four-point resistance measurement of conducting films",
        authors=["Researcher"],
        year=2025,
        url_or_doi="https://doi.org/10.1/direct",
        locator=Locator(section="Abstract"),
        untrusted_content="Two-wire resistance measurements can be compared with four-point measurements to evaluate a bulk transition.",
    )
    queries: list[str] = []

    def fake_search(self: OpenAlexReferenceDiscovery, query: str, max_results: int, research_question: str) -> list[SourceInput]:
        queries.append(query)
        return [direct]

    monkeypatch.setattr(OpenAlexReferenceDiscovery, "_search_query", fake_search)

    assert discovery.search("Does this two-wire resistance change establish a bulk transition?") == [direct]
    assert len(queries) == 1
    assert "Experimental measurement question" in queries[0]
    assert "contact or lead contributions" in queries[0]
