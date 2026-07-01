"""
Europe PMC tool - fetch scientific articles from Europe PMC
"""

from typing import Any, Dict, List

import requests


def fetch_europepmc(query: str, max_results: int = 10) -> Dict[str, Any]:
    """
    Fetch articles from Europe PMC based on a search query.

    Args:
        query: Search query string
        max_results: Maximum number of results to return

    Returns:
        Dictionary containing search results
    """
    try:
        params = {
            "query": query,
            "format": "json",
            "pageSize": max_results,
            "resultType": "core",
        }

        response = requests.get(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            params=params,
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()

        result_list = data.get("resultList", {}).get("result", [])
        if not result_list:
            return {
                "query": query,
                "total_found": 0,
                "results": [],
                "message": "No articles found for the given query",
                "source": "Europe PMC",
            }

        articles = []
        for item in result_list:
            parsed = _parse_europepmc_article(item)
            if parsed:
                articles.append(parsed)

        hit_count = data.get("hitCount", len(articles))

        return {
            "query": query,
            "total_found": hit_count,
            "results": articles,
            "source": "Europe PMC",
        }

    except requests.exceptions.RequestException as e:
        return {"error": f"Network error: {str(e)}", "results": []}
    except Exception as e:
        return {"error": f"Error fetching Europe PMC data: {str(e)}", "results": []}


def _parse_europepmc_article(item: Dict[str, Any]) -> Dict[str, Any] | None:
    """Parse a single Europe PMC result into normalized article dict."""
    try:
        pmid = str(item.get("pmid") or item.get("pmcid") or item.get("id") or "unknown")

        authors: List[str] = []
        author_string = item.get("authorString", "")
        if author_string:
            authors = [a.strip() for a in author_string.split(",") if a.strip()]

        doi = item.get("doi", "") or ""

        if item.get("pmid"):
            url = f"https://europepmc.org/article/MED/{item['pmid']}"
        elif item.get("pmcid"):
            url = f"https://europepmc.org/article/PMC/{item['pmcid']}"
        else:
            url = "https://europepmc.org/"

        return {
            "pmid": pmid,
            "title": item.get("title") or "No title",
            "authors": authors,
            "journal": item.get("journalTitle") or item.get("journalInfo", {}).get("journal", {}).get("title") or "Unknown journal",
            "year": str(item.get("pubYear") or "Unknown year"),
            "abstract": item.get("abstractText") or "",
            "doi": doi,
            "url": url,
        }
    except Exception:
        return None


def search_europepmc_advanced(query: str, open_access: bool = False) -> Dict[str, Any]:
    """Advanced Europe PMC search with optional open access filter."""
    advanced_query = query
    if open_access:
        advanced_query = f"{query} OPEN_ACCESS:Y"
    return fetch_europepmc(advanced_query)
