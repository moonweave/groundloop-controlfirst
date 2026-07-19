from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import Locator, SourceInput


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
        query = _safe_search_terms(research_question)
        if len(query) < 10:
            raise ReferenceDiscoveryError("Enter a research question of at least 10 characters.")

        params = urlencode(
            {
                "search": query,
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

        sources = [source for item in payload.get("results", []) if (source := self._source(item))]
        if not sources:
            raise ReferenceDiscoveryError("No indexed abstracts were found for this question. Refine the research question and retry.")
        return sources[:max_results]

    @staticmethod
    def _source(item: dict[str, Any]) -> SourceInput | None:
        title = str(item.get("display_name") or "").strip()
        abstract = _restore_abstract(item.get("abstract_inverted_index"))
        year = item.get("publication_year")
        if not title or not abstract or not isinstance(year, int):
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
            locator=Locator(section="OpenAlex indexed abstract"),
            untrusted_content=abstract[:4000],
        )


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
        "a", "an", "and", "are", "can", "could", "does", "explain", "for", "from", "how", "in", "is", "it", "measurement", "of", "or", "should", "that", "the", "this", "to", "what", "which", "with",
    }
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", research_question.lower())
    meaningful = [token for token in tokens if len(token) > 2 and token not in stop_words]
    return " ".join(meaningful[:12]) or " ".join(research_question.replace("?", " ").replace("*", " ").split())
