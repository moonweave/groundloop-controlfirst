from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from .analysis import screen_source_relevance
from .models import ClaimInput, Locator, SourceInput


class ReferenceDiscoveryError(RuntimeError):
    """A safe, user-facing error for the allowlisted literature lookup."""


class ReferenceDiscovery(Protocol):
    def search(self, research_question: str, max_results: int = 3) -> list[SourceInput]: ...


@dataclass(frozen=True)
class OpenAlexReferenceDiscovery:
    """Search one allowlisted academic index; callers never control a URL."""

    endpoint: str = "https://api.openalex.org/works"
    timeout_seconds: float = 8.0

    def search(self, research_question: str, max_results: int = 3) -> list[SourceInput]:
        if len(research_question.strip()) < 10:
            raise ReferenceDiscoveryError("Enter a research question of at least 10 characters.")

        query = _semantic_measurement_brief(research_question)
        sources = self._search_query(query, max_results, research_question)
        score = _relevance_score(research_question, sources)
        if score[0] > 0:
            return sources[:max_results]
        if sources:
            raise ReferenceDiscoveryError(
                "No measurement-relevant sources were found for this question. Refine the question or ask Codex to plan a more specific literature search."
            )
        raise ReferenceDiscoveryError("No indexed abstracts were found for this question. Refine the research question and retry.")

    def _search_query(
        self, query: str, max_results: int, research_question: str
    ) -> list[SourceInput]:
        params = urlencode(
            {
                "search.semantic": query,
                "per-page": min(max(max_results * 3, 3), 10),
                "select": "id,doi,display_name,authorships,publication_year,abstract_inverted_index",
            }
        )
        request = Request(
            f"{self.endpoint}?{params}",
            headers={"Accept": "application/json", "User-Agent": "GroundLoop-ControlFirst/0.1"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 - endpoint is constant and allowlisted.
                if response.status != 200:
                    raise ReferenceDiscoveryError("The literature index is unavailable. Try again shortly.")
                payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        except ReferenceDiscoveryError:
            raise
        except Exception as exc:  # Network details and source content must not reach the UI/logs.
            raise ReferenceDiscoveryError("Could not reach the literature index. Check your connection and retry.") from exc

        sources = [source for item in payload.get("results", []) if (source := self._source(item, query))]
        return _rank_sources_for_claim(research_question, sources)

    @staticmethod
    def _source(item: dict[str, Any], retrieval_query: str = "") -> SourceInput | None:
        title = str(item.get("display_name") or "").strip()
        abstract = _restore_abstract(item.get("abstract_inverted_index"))
        year = item.get("publication_year")
        if (
            not title
            or not abstract
            or not isinstance(year, int)
            or _is_off_topic_domain(title, abstract, retrieval_query)
        ):
            return None

        authors = [str(entry.get("author", {}).get("display_name") or "").strip() for entry in item.get("authorships", [])]
        authors = [author for author in authors if author][:20] or ["Unknown author"]
        url_or_doi = str(item.get("doi") or item.get("id") or "").strip()
        if not url_or_doi:
            return None
        stable_id = hashlib.sha256(url_or_doi.encode("utf-8")).hexdigest()[:16]
        return SourceInput(
            id=f"openalex-{stable_id}",
            title=title[:300],
            authors=authors,
            year=year,
            url_or_doi=url_or_doi[:500],
            locator=Locator(section=f"OpenAlex indexed abstract · retrieval query: {retrieval_query}"[:500]),
            untrusted_content=abstract[:4000],
            retrieval_provider="openalex",
            publication_status="indexed_abstract",
        )


@dataclass(frozen=True)
class ArxivReferenceDiscovery:
    """Search the allowlisted arXiv Atom endpoint for clearly labelled preprints."""

    endpoint: str = "https://export.arxiv.org/api/query"
    timeout_seconds: float = 8.0

    def search(self, research_question: str, max_results: int = 3) -> list[SourceInput]:
        if len(research_question.strip()) < 10:
            raise ReferenceDiscoveryError("Enter a research question of at least 10 characters.")
        terms = _arxiv_focus_terms(research_question)
        if not terms:
            raise ReferenceDiscoveryError("No arXiv search terms were available for this question.")
        query = " AND ".join(f"all:{term}" for term in terms)
        params = urlencode(
            {
                "search_query": query,
                "start": 0,
                "max_results": min(max(max_results * 2, 3), 10),
                "sortBy": "relevance",
                "sortOrder": "descending",
            }
        )
        request = Request(
            f"{self.endpoint}?{params}",
            headers={"Accept": "application/atom+xml", "User-Agent": "GroundLoop-ControlFirst/0.1"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310 - endpoint is constant and allowlisted.
                if response.status != 200:
                    raise ReferenceDiscoveryError("The arXiv index is unavailable. Try again shortly.")
                root = ElementTree.fromstring(response.read())
        except ReferenceDiscoveryError:
            raise
        except Exception as exc:  # Network and XML details must not reach the UI/logs.
            raise ReferenceDiscoveryError("Could not reach the arXiv index. Check your connection and retry.") from exc

        namespace = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
        sources = [
            source
            for entry in root.findall("atom:entry", namespace)
            if (source := self._source(entry, namespace, research_question))
        ]
        ranked = _rank_sources_for_claim(research_question, sources)
        score = _relevance_score(research_question, ranked)
        if score[0] > 0:
            return ranked[:max_results]
        if ranked:
            raise ReferenceDiscoveryError(
                "No measurement-relevant arXiv preprints were found for this question. Refine the question or continue with indexed literature."
            )
        raise ReferenceDiscoveryError("No arXiv preprint abstracts were found for this question.")

    @staticmethod
    def _source(
        entry: ElementTree.Element,
        namespace: dict[str, str],
        research_question: str,
    ) -> SourceInput | None:
        def text(name: str) -> str:
            return " ".join((entry.findtext(name, default="", namespaces=namespace) or "").split())

        title = text("atom:title")
        abstract = text("atom:summary")
        published = text("atom:published")
        abs_url = text("atom:id").replace("http://", "https://", 1)
        if not title or not abstract or not published or not abs_url or _is_off_topic_domain(title, abstract, research_question):
            return None
        try:
            year = int(published[:4])
        except ValueError:
            return None
        authors = [
            " ".join((author.findtext("atom:name", default="", namespaces=namespace) or "").split())
            for author in entry.findall("atom:author", namespace)
        ]
        authors = [author for author in authors if author][:20] or ["Unknown author"]
        category = entry.find("arxiv:primary_category", namespace)
        category_name = category.get("term") if category is not None else "unclassified"
        stable_id = hashlib.sha256(abs_url.encode("utf-8")).hexdigest()[:16]
        return SourceInput(
            id=f"arxiv-{stable_id}",
            title=title[:300],
            authors=authors,
            year=year,
            url_or_doi=abs_url[:500],
            locator=Locator(section=f"arXiv preprint abstract · category: {category_name}"),
            untrusted_content=abstract[:4000],
            retrieval_provider="arxiv",
            publication_status="preprint",
        )


@dataclass(frozen=True)
class DualIndexReferenceDiscovery:
    """Retrieve a small, balanced candidate set from indexed literature and arXiv."""

    openalex: ReferenceDiscovery = field(default_factory=OpenAlexReferenceDiscovery)
    arxiv: ReferenceDiscovery = field(default_factory=ArxivReferenceDiscovery)

    def search(self, research_question: str, max_results: int = 3) -> list[SourceInput]:
        successful: list[SourceInput] = []
        errors: list[ReferenceDiscoveryError] = []
        for discovery in (self.openalex, self.arxiv):
            try:
                successful.extend(discovery.search(research_question, max_results=max_results))
            except ReferenceDiscoveryError as exc:
                errors.append(exc)
        if not successful:
            if errors:
                raise errors[0]
            raise ReferenceDiscoveryError("No literature candidates were found for this question.")
        deduplicated = _deduplicate_sources(successful)
        ranked = _rank_sources_for_claim(research_question, deduplicated)
        score = _relevance_score(research_question, ranked)
        if score[0] == 0:
            raise ReferenceDiscoveryError(
                "No measurement-relevant sources were found for this question. Refine the question or ask Codex to plan a more specific literature search."
            )
        return _balanced_sources(ranked, max_results)


def _restore_abstract(inverted_index: Any) -> str:
    if not isinstance(inverted_index, dict):
        return ""
    positions: list[tuple[int, str]] = []
    for token, indexes in inverted_index.items():
        if not isinstance(token, str) or not isinstance(indexes, list):
            continue
        for index in indexes:
            if isinstance(index, int) and index >= 0:
                positions.append((index, token))
    return " ".join(token for _, token in sorted(positions))


def _safe_search_terms(research_question: str) -> str:
    """OpenAlex treats wildcard punctuation specially in stemmed `search` queries."""
    stop_words = {
        "a", "an", "and", "are", "at", "be", "can", "could", "does", "explain", "for", "from", "how", "in", "is", "it", "measurement", "of", "or", "should", "that", "the", "this", "to", "what", "which", "with",
    }
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", research_question.lower())
    meaningful = [token for token in tokens if len(token) > 2 and token not in stop_words]
    return " ".join(meaningful[:12]) or " ".join(research_question.replace("?", " ").replace("*", " ").split())


def _arxiv_focus_terms(research_question: str) -> list[str]:
    """Use the claim's measurement/confound nouns, not its whole prose sentence."""
    terms = _safe_search_terms(research_question).split()
    if _requires_electrical_transport_focus(research_question) and "contact" not in terms:
        # A two-wire claim is not made specific by searching its conclusion
        # ("conductivity"). Search the unresolved measurement boundary instead.
        return ["contact", "resistance"]
    diagnostic_priority = (
        "contact", "contacts", "lead", "leads", "resistance", "conductivity",
        "probe", "four-wire", "two-wire", "thermal", "temperature", "current",
        "voltage", "transport", "artifact", "artifacts",
    )
    focused = [term for term in diagnostic_priority if term in terms]
    return (focused or terms)[:2]


def _semantic_measurement_brief(research_question: str) -> str:
    return (
        f"Experimental measurement question: {research_question.strip()} "
        "Find foundational experimental measurement literature relevant to the measurement method, "
        "measurement artifacts, and discriminating controls. Prefer sources explaining probe configuration, "
        "contact or lead contributions, and how to distinguish a claimed material mechanism from a measurement-path artifact."
    )


def _search_query_variants(research_question: str) -> list[str]:
    """Broaden an over-specific search without accepting user-controlled retrieval targets."""
    primary = _safe_search_terms(research_question)
    terms = primary.split()
    if len(terms) < 4:
        return [primary] if primary else []

    variants = [" ".join(terms[:size]) for size in range(len(terms), 2, -1)]
    return list(dict.fromkeys(variants))


def _rank_sources_for_claim(
    research_question: str, sources: list[SourceInput]
) -> list[SourceInput]:
    screens = {
        item.source_id: item.verdict
        for item in screen_source_relevance(ClaimInput(claim=research_question), sources)
    }
    return sorted(
        sources,
        key=lambda source: {"direct": 0, "contextual": 1, "limited": 2}[screens[source.id]],
    )


def _relevance_score(
    research_question: str, sources: list[SourceInput]
) -> tuple[int, int]:
    screens = screen_source_relevance(ClaimInput(claim=research_question), sources)
    direct = sum(item.verdict == "direct" for item in screens)
    contextual = sum(item.verdict == "contextual" for item in screens)
    return direct, contextual


def _is_off_topic_domain(title: str, abstract: str, retrieval_query: str) -> bool:
    """Reject a high-volume adjacent domain when the user did not ask for it."""
    source_terms = set(re.findall(r"[a-z0-9]+", f"{title} {abstract}".lower()))
    query_terms = set(re.findall(r"[a-z0-9]+", retrieval_query.lower()))
    battery_markers = {"battery", "batteries", "lithium", "polysulfide", "polysulfides", "cathode", "anode"}
    if bool(source_terms & battery_markers) and not bool(query_terms & battery_markers):
        return True

    if _requires_electrical_transport_focus(retrieval_query):
        electrical_markers = {
            "electrical", "four", "point", "two", "wire", "probe", "resistivity",
            "voltage", "current", "ohm", "contact", "lead", "ammeter", "voltmeter",
            "semiconductor",
        }
        thermal_adjacent_markers = {
            "thermal", "heat", "nanofluid", "nanofluids", "cooling", "heating", "fluid",
        }
        has_electrical_measurement_anchor = bool(source_terms & electrical_markers)
        requests_thermal_domain = bool(query_terms & {"thermal", "heat", "nanofluid", "cooling", "heating"})
        if not has_electrical_measurement_anchor:
            return True
        if bool(source_terms & thermal_adjacent_markers) and not requests_thermal_domain:
            return True
    return False


def _requires_electrical_transport_focus(research_question: str) -> bool:
    terms = set(re.findall(r"[a-z0-9]+", research_question.lower()))
    has_wiring_context = "wire" in terms and bool({"two", "four"} & terms)
    has_probe_context = "probe" in terms and "point" in terms
    return (has_wiring_context or has_probe_context) and bool(
        {"resistance", "resistivity", "conductivity", "voltage", "current"} & terms
    )


def _deduplicate_sources(sources: list[SourceInput]) -> list[SourceInput]:
    """Keep the first bounded record for each stable link or normalized title."""
    seen: set[str] = set()
    unique: list[SourceInput] = []
    for source in sources:
        key = re.sub(r"[^a-z0-9]+", "", source.url_or_doi.lower())
        title_key = re.sub(r"[^a-z0-9]+", "", source.title.lower())
        if key in seen or title_key in seen:
            continue
        seen.update({key, title_key})
        unique.append(source)
    return unique


def _balanced_sources(sources: list[SourceInput], max_results: int) -> list[SourceInput]:
    """Keep relevance order; provider diversity must never promote a weaker candidate."""
    if max_results < 1:
        return []
    return sources[:max_results]
