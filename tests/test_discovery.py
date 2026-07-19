from packages.core.discovery import OpenAlexReferenceDiscovery, _restore_abstract, _safe_search_terms


def test_restores_openalex_inverted_abstract() -> None:
    assert _restore_abstract({"Evidence": [1], "First": [0], "matters.": [2]}) == "First Evidence matters."


def test_sanitises_openalex_wildcard_punctuation() -> None:
    assert _safe_search_terms("Does this control work? Maybe*") == "control work maybe"


def test_extracts_meaningful_search_terms_from_a_research_question() -> None:
    assert _safe_search_terms("What measurement control can distinguish contact resistance from a bulk conductivity change?") == "control distinguish contact resistance bulk conductivity change"


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
