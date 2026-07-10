"""Central registry for dataset pipeline repositories (search, normalize, load-more)."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from domain.dataset_search import DatasetSearchCursor, InterpretedQuery

GEO_REPOSITORY = "GEO"
GXA_REPOSITORY = "Expression Atlas"
IMMPORT_REPOSITORY = "ImmPort"
VIVLI_REPOSITORY = "Vivli"
OMICSDI_REPOSITORY = "OmicsDI"
PROTEOMEXCHANGE_REPOSITORY = "ProteomeXchange"
VDJSERVER_REPOSITORY = "VDJServer"
TEXT_BROAD_REPOSITORIES = frozenset(
    {
        IMMPORT_REPOSITORY,
        OMICSDI_REPOSITORY,
        PROTEOMEXCHANGE_REPOSITORY,
        VIVLI_REPOSITORY,
        VDJSERVER_REPOSITORY,
    }
)

PROTEOMEXCHANGE_INCOMPATIBLE_ASSAYS = frozenset(
    {
        "metabolomics",
        "rna-seq",
        "genomics",
        "flow cytometry",
    }
)

VDJSERVER_INCOMPATIBLE_ASSAYS = frozenset(
    {
        "metabolomics",
        "proteomics",
        "flow cytometry",
        "microarray",
        "genomics",
    }
)

VDJSERVER_COMPATIBLE_ASSAYS = frozenset(
    {
        "bcr",
        "tcr",
        "airr-seq",
        "immune repertoire",
        "immune repertoire sequencing",
        "repertoire sequencing",
        "b cell receptor",
        "t cell receptor",
    }
)

VDJSERVER_QUERY_PATTERN = re.compile(
    r"\b("
    r"immune repertoire|repertoire seq(?:uencing)?|airr[\s-]?seq|"
    r"bcr|tcr|vdj|antibody repertoire|b cell receptor|t cell receptor"
    r")\b",
    re.I,
)

FetchRecordsFn = Callable[..., dict[str, Any]]
FetchMoreFn = Callable[[DatasetSearchCursor], dict[str, Any]]
NormalizeFn = Callable[[list[dict[str, Any]]], list[Any]]
MaxResultsFn = Callable[[int | None], int]


@dataclass(frozen=True)
class DatasetRepositorySpec:
    """Handlers and metadata for one dataset pipeline repository."""

    repository: str
    tool_name: str
    source_display: str
    priority: int
    fetch_records: FetchRecordsFn
    normalize_records: NormalizeFn
    resolve_max_results: MaxResultsFn
    accession_prefixes: tuple[str, ...] = ()
    fetch_more_records: FetchMoreFn | None = None

    @property
    def supports_load_more(self) -> bool:
        return self.fetch_more_records is not None

    @property
    def facet_capabilities(self):
        """Per-slot search, response, and evidence capabilities for this repository."""
        from domain.repository_facet_capabilities import get_facet_capability

        return get_facet_capability(self.repository)


def _build_registry() -> dict[str, DatasetRepositorySpec]:
    from tools.expression_atlas import (
        fetch_gxa_repository_records,
        get_expression_atlas_max_results,
        normalize_gxa_records,
    )
    from tools.geo_dataset_search import (
        fetch_geo_repository_records,
        fetch_more_geo_repository_records,
        get_geo_max_results,
        normalize_geo_records,
    )
    from tools.immport_dataset_search import (
        fetch_immport_repository_records,
        fetch_more_immport_repository_records,
        get_immport_max_results,
        normalize_immport_records,
    )
    from tools.omicsdi_dataset_search import (
        fetch_more_omicsdi_repository_records,
        fetch_omicsdi_repository_records,
        get_omicsdi_max_results,
        normalize_omicsdi_records,
    )
    from tools.proteomexchange_dataset_search import (
        fetch_more_proteomexchange_repository_records,
        fetch_proteomexchange_repository_records,
        get_proteomexchange_max_results,
        normalize_proteomexchange_records,
    )
    from tools.vdjserver_dataset_search import (
        fetch_more_vdjserver_repository_records,
        fetch_vdjserver_repository_records,
        get_vdjserver_max_results,
        normalize_vdjserver_records,
    )
    from tools.vivli_dataset_search import (
        fetch_more_vivli_repository_records,
        fetch_vivli_repository_records,
        get_vivli_max_results,
        normalize_vivli_records,
    )

    return {
        GEO_REPOSITORY: DatasetRepositorySpec(
            repository=GEO_REPOSITORY,
            tool_name="geo_dataset_search",
            source_display="NCBI GEO",
            priority=0,
            accession_prefixes=("GSE",),
            fetch_records=fetch_geo_repository_records,
            fetch_more_records=fetch_more_geo_repository_records,
            normalize_records=normalize_geo_records,
            resolve_max_results=get_geo_max_results,
        ),
        GXA_REPOSITORY: DatasetRepositorySpec(
            repository=GXA_REPOSITORY,
            tool_name="expression_atlas",
            source_display="Expression Atlas",
            priority=1,
            accession_prefixes=("E-",),
            fetch_records=fetch_gxa_repository_records,
            fetch_more_records=None,
            normalize_records=normalize_gxa_records,
            resolve_max_results=get_expression_atlas_max_results,
        ),
        IMMPORT_REPOSITORY: DatasetRepositorySpec(
            repository=IMMPORT_REPOSITORY,
            tool_name="immport",
            source_display="ImmPort",
            priority=2,
            accession_prefixes=("SDY",),
            fetch_records=fetch_immport_repository_records,
            fetch_more_records=fetch_more_immport_repository_records,
            normalize_records=normalize_immport_records,
            resolve_max_results=get_immport_max_results,
        ),
        VIVLI_REPOSITORY: DatasetRepositorySpec(
            repository=VIVLI_REPOSITORY,
            tool_name="vivli",
            source_display="Vivli / AccessClinicalData@NIAID",
            priority=3,
            accession_prefixes=("NCT",),
            fetch_records=fetch_vivli_repository_records,
            fetch_more_records=fetch_more_vivli_repository_records,
            normalize_records=normalize_vivli_records,
            resolve_max_results=get_vivli_max_results,
        ),
        OMICSDI_REPOSITORY: DatasetRepositorySpec(
            repository=OMICSDI_REPOSITORY,
            tool_name="omicsdi",
            source_display="OmicsDI API",
            priority=4,
            accession_prefixes=("PXD", "MTBLS", "ST"),
            fetch_records=fetch_omicsdi_repository_records,
            fetch_more_records=fetch_more_omicsdi_repository_records,
            normalize_records=normalize_omicsdi_records,
            resolve_max_results=get_omicsdi_max_results,
        ),
        PROTEOMEXCHANGE_REPOSITORY: DatasetRepositorySpec(
            repository=PROTEOMEXCHANGE_REPOSITORY,
            tool_name="proteomexchange",
            source_display="ProteomeXchange / OmicsDI API",
            priority=5,
            accession_prefixes=("PXD",),
            fetch_records=fetch_proteomexchange_repository_records,
            fetch_more_records=fetch_more_proteomexchange_repository_records,
            normalize_records=normalize_proteomexchange_records,
            resolve_max_results=get_proteomexchange_max_results,
        ),
        VDJSERVER_REPOSITORY: DatasetRepositorySpec(
            repository=VDJSERVER_REPOSITORY,
            tool_name="vdjserver",
            source_display="VDJServer AIRR API",
            priority=6,
            accession_prefixes=("PRJNA", "PRJEB", "PRJDB"),
            fetch_records=fetch_vdjserver_repository_records,
            fetch_more_records=fetch_more_vdjserver_repository_records,
            normalize_records=normalize_vdjserver_records,
            resolve_max_results=get_vdjserver_max_results,
        ),
    }


@lru_cache
def get_dataset_repository_registry() -> dict[str, DatasetRepositorySpec]:
    return _build_registry()


def get_repository_spec(repository: str) -> DatasetRepositorySpec:
    try:
        return get_dataset_repository_registry()[repository]
    except KeyError as exc:
        raise ValueError(f"Unsupported dataset repository: {repository}") from exc


def supported_repositories() -> frozenset[str]:
    return frozenset(get_dataset_repository_registry())


def repository_priority_map() -> dict[str, int]:
    return {
        spec.repository: spec.priority
        for spec in get_dataset_repository_registry().values()
    }


def infer_record_repository(record: dict[str, Any]) -> str:
    tagged = record.get("_source_repository")
    if tagged in supported_repositories():
        return tagged
    accession = str(record.get("accession") or "").upper()
    for spec in sorted(
        get_dataset_repository_registry().values(),
        key=lambda item: item.priority,
    ):
        if any(accession.startswith(prefix.upper()) for prefix in spec.accession_prefixes):
            return spec.repository
    return GEO_REPOSITORY


def pick_load_more_cursor(search_results: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick the highest-priority repository cursor when multiple sources were searched."""
    priority = repository_priority_map()
    ordered = sorted(
        search_results,
        key=lambda result: priority.get(str(result.get("repository") or ""), 99),
    )
    for result in ordered:
        cursor = result.get("load_more_cursor")
        if cursor and result.get("has_more"):
            return cursor
    for result in ordered:
        cursor = result.get("load_more_cursor")
        if cursor:
            return cursor
    return None


def resolve_repository_for_load_more(
    cursor: DatasetSearchCursor,
    existing_candidates: list[Any],
) -> str:
    if cursor.repository:
        return cursor.repository
    if existing_candidates:
        return existing_candidates[0].repository
    raise ValueError("Cannot resolve repository for load-more (missing cursor.repository and candidates)")


def repository_supports_load_more(repository: str) -> bool:
    return get_repository_spec(repository).supports_load_more


def is_repository_tool_enabled(registry: Any, repository: str) -> bool:
    spec = get_repository_spec(repository)
    return registry.get_tool(spec.tool_name) is not None


def _query_requests_vdjserver(query: str) -> bool:
    return bool(VDJSERVER_QUERY_PATTERN.search(query))


def _vdjserver_repository_applicable(
    query: str,
    interpreted: InterpretedQuery | None,
) -> bool:
    if _query_requests_vdjserver(query):
        return True

    requested_assay = (interpreted.assay if interpreted else None) or ""
    normalized_assay = requested_assay.strip().lower()
    if normalized_assay in VDJSERVER_COMPATIBLE_ASSAYS:
        return True
    if normalized_assay in VDJSERVER_INCOMPATIBLE_ASSAYS:
        return False
    return False


def filter_repositories_for_interpreted_query(
    repositories: list[str],
    interpreted: InterpretedQuery | None,
    *,
    query: str = "",
) -> tuple[list[str], list[str]]:
    """
    Drop repositories that cannot satisfy the interpreted assay facet.

    ProteomeXchange is proteomics-only; metabolomics and other omics queries should
    use OmicsDI (or other indexes) instead of returning unrelated proteomics hits.
    VDJServer is immune-repertoire-only and is included when the query names repertoire
    concepts or compatible assay facets.
    """
    if not repositories:
        return [], []

    filtered = list(repositories)
    skipped: list[str] = []

    if PROTEOMEXCHANGE_REPOSITORY in filtered:
        requested_assay = (interpreted.assay if interpreted else None) or ""
        normalized_assay = requested_assay.strip().lower()
        if not normalized_assay and query.strip():
            query_lower = query.lower()
            if re.search(r"\bmetabolomics\b", query_lower):
                normalized_assay = "metabolomics"
            elif re.search(r"\brna[\s-]?seq(?:uencing)?\b", query_lower):
                normalized_assay = "rna-seq"
            elif re.search(r"\bgenomics\b", query_lower):
                normalized_assay = "genomics"

        if normalized_assay in PROTEOMEXCHANGE_INCOMPATIBLE_ASSAYS:
            filtered = [repo for repo in filtered if repo != PROTEOMEXCHANGE_REPOSITORY]
            skipped.append(PROTEOMEXCHANGE_REPOSITORY)

    if VDJSERVER_REPOSITORY in filtered and not _vdjserver_repository_applicable(
        query,
        interpreted,
    ):
        filtered = [repo for repo in filtered if repo != VDJSERVER_REPOSITORY]
        skipped.append(VDJSERVER_REPOSITORY)

    return filtered, skipped


def resolve_enabled_dataset_repositories(registry: Any) -> list[str]:
    """Return repository labels whose pipeline tools are registered, in merge priority order."""
    enabled = [
        spec
        for spec in sorted(
            get_dataset_repository_registry().values(),
            key=lambda item: item.priority,
        )
        if registry.get_tool(spec.tool_name) is not None
    ]
    return [spec.repository for spec in enabled]


def any_load_more_enabled(registry: Any) -> bool:
    return any(
        spec.supports_load_more and registry.get_tool(spec.tool_name) is not None
        for spec in get_dataset_repository_registry().values()
    )


def fetch_repository_records(
    repository: str,
    concept_mappings,
    max_results: int | None = None,
    *,
    query: str = "",
    interpreted_query: InterpretedQuery | None = None,
    species: str | None = None,
    include_text_broad: bool = True,
) -> dict[str, Any]:
    spec = get_repository_spec(repository)
    interpreted = None
    if interpreted_query is not None:
        interpreted = (
            InterpretedQuery.model_validate(interpreted_query)
            if isinstance(interpreted_query, dict)
            else interpreted_query
        )
    if repository == GXA_REPOSITORY:
        return spec.fetch_records(
            concept_mappings,
            max_results=max_results,
            query=query,
            interpreted_query=interpreted,
            species=species,
        )
    if repository in TEXT_BROAD_REPOSITORIES:
        return spec.fetch_records(
            concept_mappings,
            max_results=max_results,
            query=query,
            interpreted_query=interpreted,
            include_text_broad=include_text_broad,
        )
    return spec.fetch_records(
        concept_mappings,
        max_results=max_results,
        query=query,
        interpreted_query=(
            interpreted.model_dump() if interpreted is not None else None
        ),
    )


def fetch_more_repository_records(
    repository: str,
    cursor: DatasetSearchCursor,
) -> dict[str, Any]:
    spec = get_repository_spec(repository)
    if spec.fetch_more_records is None:
        raise RuntimeError(f"Load-more is not implemented for {repository}")
    return spec.fetch_more_records(cursor)
