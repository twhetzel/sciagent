"""Shared text_broad supplemental search helpers for facet-backed repositories."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from domain.dataset_search import ConceptMapping, InterpretedQuery
from domain.facet_search_strategies import build_facet_search_queries

TEXT_BROAD_STRATEGY = "text_broad"
FACET_STRATEGIES = frozenset({"strict", "broad_1", "broad_2", "broad_3"})


def supplemental_text_search_term(
    query: str,
    interpreted: InterpretedQuery | None,
    *,
    compact_adhoc_search_term: Callable[[str], str],
) -> str | None:
    """Compact free-text term for the supplemental text_broad strategy."""
    if query.strip():
        compact = compact_adhoc_search_term(query)
        if compact:
            return compact
    if interpreted:
        terms = [
            value
            for value in (
                interpreted.disease,
                interpreted.tissue,
                interpreted.assay,
            )
            if value
        ]
        if terms:
            return " ".join(terms)
    return None


def resolve_search_queries_with_text_broad(
    *,
    query: str,
    interpreted_query: InterpretedQuery | dict[str, Any] | None = None,
    concept_mappings: list[ConceptMapping] | None = None,
    include_text_broad: bool = True,
    compact_adhoc_search_term: Callable[[str], str],
) -> list[tuple[str, str]]:
    interpreted = None
    if interpreted_query is not None:
        interpreted = (
            InterpretedQuery.model_validate(interpreted_query)
            if isinstance(interpreted_query, dict)
            else interpreted_query
        )

    facet_queries = build_facet_search_queries(
        interpreted=interpreted,
        concept_mappings=concept_mappings,
    )
    if facet_queries:
        queries = list(facet_queries)
        if include_text_broad:
            text_term = supplemental_text_search_term(
                query,
                interpreted,
                compact_adhoc_search_term=compact_adhoc_search_term,
            )
            if text_term:
                queries.append((TEXT_BROAD_STRATEGY, text_term))
        return queries
    if query.strip():
        compact = compact_adhoc_search_term(query)
        return [("adhoc", compact or query.strip())]
    return []


def resolve_text_broad_total_found(
    strategy_totals: dict[str, int],
    *,
    include_text_broad: bool,
) -> int | None:
    if not include_text_broad:
        return None
    total = strategy_totals.get(TEXT_BROAD_STRATEGY)
    if total is None:
        return None
    return int(total)


def is_supplemental_strategy(strategy: str) -> bool:
    return strategy == TEXT_BROAD_STRATEGY


def strategy_count_summary(
    strategy: str,
    search_term: str,
    total_found: int,
) -> dict[str, str | int | bool]:
    return {
        "strategy": strategy,
        "search_term": search_term,
        "total_found": total_found,
        "retrieved": 0,
        "new_ids": 0,
        "supplemental": is_supplemental_strategy(strategy),
    }


def roll_up_facet_totals(
    strategy: str,
    total_found: int,
    *,
    max_facet_total_found: int,
    primary_total_found: int,
) -> tuple[int, int]:
    if strategy in FACET_STRATEGIES:
        max_facet_total_found = max(max_facet_total_found, total_found)
        if primary_total_found == 0:
            primary_total_found = total_found
    return max_facet_total_found, primary_total_found


def finalize_facet_total_found(
    max_facet_total_found: int,
    strategy_totals: dict[str, int],
) -> int:
    if max_facet_total_found > 0:
        return max_facet_total_found
    return max(
        (
            total
            for strategy, total in strategy_totals.items()
            if strategy != TEXT_BROAD_STRATEGY
        ),
        default=0,
    )
