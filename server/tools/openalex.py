"""
OpenAlex tool - fetch scholarly works from OpenAlex
"""

import os
from typing import Any, Dict, List

import requests


def fetch_openalex(query: str, max_results: int = 10) -> Dict[str, Any]:
    """
    Fetch scholarly works from OpenAlex based on a search query.

    Args:
        query: Search query string
        max_results: Maximum number of results to return

    Returns:
        Dictionary containing search results
    """
    try:
        params: Dict[str, Any] = {
            "search": query,
            "per_page": max_results,
        }
        email = os.getenv("OPENALEX_EMAIL", "")
        if email:
            params["mailto"] = email

        response = requests.get(
            "https://api.openalex.org/works",
            params=params,
            timeout=15,
            headers={"User-Agent": "SciAgentStudio/0.1 (mailto:" + email + ")" if email else "SciAgentStudio/0.1"},
        )
        response.raise_for_status()
        data = response.json()

        results_raw = data.get("results", [])
        if not results_raw:
            return {
                "query": query,
                "total_found": 0,
                "results": [],
                "message": "No works found for the given query",
                "source": "OpenAlex",
            }

        articles = []
        for work in results_raw:
            parsed = _parse_openalex_work(work)
            if parsed:
                articles.append(parsed)

        meta_total = data.get("meta", {}).get("count", len(articles))

        return {
            "query": query,
            "total_found": meta_total,
            "results": articles,
            "source": "OpenAlex",
        }

    except requests.exceptions.RequestException as e:
        return {"error": f"Network error: {str(e)}", "results": []}
    except Exception as e:
        return {"error": f"Error fetching OpenAlex data: {str(e)}", "results": []}


def _parse_openalex_work(work: Dict[str, Any]) -> Dict[str, Any] | None:
    """Parse a single OpenAlex work into normalized article dict."""
    try:
        openalex_id = work.get("id", "")
        short_id = openalex_id.rsplit("/", 1)[-1] if openalex_id else "unknown"

        authors: List[str] = []
        for authorship in work.get("authorships", []):
            author = authorship.get("author", {})
            name = author.get("display_name")
            if name:
                authors.append(name)

        journal = "Unknown journal"
        primary_location = work.get("primary_location") or {}
        source = primary_location.get("source") or {}
        if source.get("display_name"):
            journal = source["display_name"]

        doi = work.get("doi", "") or ""
        if doi.startswith("https://doi.org/"):
            doi = doi.replace("https://doi.org/", "")

        return {
            "pmid": short_id,
            "title": work.get("title") or work.get("display_name") or "No title",
            "authors": authors,
            "journal": journal,
            "year": str(work.get("publication_year") or "Unknown year"),
            "abstract": _reconstruct_abstract(work.get("abstract_inverted_index")),
            "doi": doi,
            "url": openalex_id or f"https://openalex.org/{short_id}",
        }
    except Exception:
        return None


def _reconstruct_abstract(inverted_index: Dict[str, List[int]] | None) -> str:
    """Reconstruct abstract text from OpenAlex inverted index."""
    if not inverted_index:
        return ""

    word_positions: List[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))

    if not word_positions:
        return ""

    word_positions.sort(key=lambda x: x[0])
    return " ".join(word for _, word in word_positions)


def search_openalex_advanced(query: str, publication_year: int | None = None) -> Dict[str, Any]:
    """Advanced OpenAlex search with optional publication year filter."""
    if publication_year:
        query = f"{query} publication_year:{publication_year}"
    return fetch_openalex(query)
