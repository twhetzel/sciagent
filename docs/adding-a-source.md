# Adding a new data source

This guide is the recipe for integrating external repositories into SciAgent Studio. Follow it when adding sources like GEO, Expression Atlas, or future omics archives.

## Integration tiers

| Tier | When to use | User experience |
|------|-------------|-----------------|
| **Simple source** | Keyword lookup, single API call, no facet grounding | Chat + trace tool result (e.g. PubMed, MyGene) |
| **Dataset pipeline source** | Repository supports disease/tissue/assay discovery with metadata | **Dataset discovery UI** — ranked cards, facets, evidence, strategies (required for omics archives) |

**Rule:** If users will ask *“Find public RNA-seq datasets for …”*, implement the **dataset pipeline tier**, not just a chat tool.

---

## Dataset pipeline architecture (required for omics repositories)

All dataset pipeline sources share the same seven steps and must emit a `dataset_search` payload for the frontend.

```
User query
  → 1. Interpret Query      (domain/query_interpretation.py)
  → 2. Ground Query          (domain/ontology_grounder.py)
  → 3. Search Repository     (per-source adapter in tools/)
  → 4. Normalize Records     (→ DatasetCandidate)
  → 5. Annotate Evidence     (domain/dataset_annotation.py)
  → 6. Rank Results          (domain/ranking.py)
  → 7. Respond               (dataset_search JSON + brief chat summary)
```

The UI (`DatasetResultsPanel`) activates when `POST /api/query` returns `dataset_search` (not null). Chat-only tool output will **not** use the ranked dataset panel.

### Shared multi-strategy search

All dataset pipeline sources must use the shared facet strategies in `domain/facet_search_strategies.py`:

```python
FACET_SEARCH_STRATEGIES = (
    ("strict", ("disease", "assay", "tissue")),
    ("broad_1", ("disease", "assay")),
    ("broad_2", ("disease", "tissue")),
    ("broad_3", ("disease",)),
)
```

Build queries with `build_facet_search_queries(interpreted=..., concept_mappings=...)`. Run strict first, deduplicate by accession, prefer strictest strategy (`STRATEGY_PRIORITY`).

Return per-strategy metadata:

```python
{
    "search_term": "<primary strategy query>",
    "search_strategies": [{"strategy", "search_term", "total_found", "retrieved", "new_ids"}, ...],
    "total_found": <max across strategies>,
    "primary_total_found": <strict strategy count>,
    "records": [...],
    "repository": "<NAME>",
    "source": "<display name>",
    "has_more": false,          # true when load-more is implemented
    "load_more_cursor": null,
}
```

---

## Checklist: dataset pipeline source

### 1. Tool / adapter module (`server/tools/<source>_dataset_search.py` or extend existing)

- [ ] `fetch_<repo>_repository_records(concept_mappings, max_results, query, interpreted_query, ...)`
- [ ] Multi-strategy search using `build_facet_search_queries`
- [ ] `normalize_<repo>_record()` → `DatasetCandidate` with correct `repository` field
- [ ] `collect_metadata_fields()` for evidence extraction (title, summary, taxon, assay hints)
- [ ] Env var for max results (e.g. `EXPRESSION_ATLAS_MAX_RESULTS`)
- [ ] Unit tests with mocked HTTP

### 2. Wire into `agent/dataset_discovery.py`

- [ ] Add repository constant (e.g. `GXA_REPOSITORY = "Expression Atlas"`)
- [ ] Add to `SUPPORTED_REPOSITORIES`
- [ ] Dispatch in `search_repository()`, `normalize_records()`, `resolve_max_results()`
- [ ] Integration test calling `run_dataset_discovery(query, repository=...)`

### 3. Orchestrator routing (`server/agent/orchestrator.py`)

- [ ] Add repository to `_resolve_dataset_repositories()` (searches all enabled repos)
- [ ] Dataset queries call `_run_dataset_discovery(query, repositories=...)`
- [ ] Wire `search_repositories()` + `merge_repository_search_results()` for multi-source dedupe
- [ ] Do **not** also route the same query through the simple tool path in `_plan()`

### 4. Registry + deployment config

- [ ] Register tool in `server/agent/registry.py` (for sidebar + exclusion)
- [ ] Add to `SOURCE_NAMES` in `server/sciagent_server/config.py`
- [ ] Document in `.env.example` and README tool inventory

### 5. Frontend (repository-aware labels)

- [ ] Use `datasetSearch.repository` instead of hardcoded "GEO" in:
  - `web/src/components/DatasetResultsPanel.jsx`
  - `web/src/components/DatasetActionBar.jsx`
  - `web/src/components/TracePanel.jsx` (optional)
- [ ] Load-more button only when `has_more` is true (GEO today; optional for new sources)

### 6. Optional: load-more

- [ ] Implement `fetch_more_<repo>_repository_records(cursor)` if the API supports paging
- [ ] Extend `DatasetSearchCursor` if needed
- [ ] Wire `POST /api/dataset-search/more` in `sciagent_server/main.py`

### 7. Documentation

- [ ] README example query
- [ ] This file — add row to reference implementations table below

---

## Checklist: simple source (non-dataset)

Use only when the source is **not** an omics dataset repository.

1. Implement `server/tools/<source>.py` with normalized `{results, total_found, source}` payload
2. Register in `registry.py` + `SOURCE_NAMES`
3. Add orchestrator keyword routing in `_plan()` and `_extract_tool_parameters()`
4. Add chat formatter in `_final_synthesis()`
5. Tests + README

---

## Reference implementations

| Source | Module | Pipeline | Load-more | Notes |
|--------|--------|----------|-----------|-------|
| GEO | `tools/geo_dataset_search.py` | `agent/dataset_discovery.py` | Yes | Grounded synonyms in search queries |
| Expression Atlas | `tools/expression_atlas.py` | `agent/dataset_discovery.py` | No (yet) | EBI Search + GXA JSON enrich |
| PubMed | `tools/pubmed.py` | — | — | Simple literature source |

---

## Repository resolution (orchestrator)

When a query matches `is_dataset_discovery_query()`:

1. Search **all enabled** dataset repositories (GEO and Expression Atlas when both are on)
2. Merge results with canonical de-duplication (`GSE12345` ↔ `E-GEOD-12345`; keep GXA-only studies like `E-MTAB-*`)
3. Prefer GEO metadata when the same study appears in both sources
4. Rank the merged candidate set once by evidence coverage

If only one repository is enabled, behavior is unchanged (single-source pipeline).

Extend `_resolve_dataset_repositories()` when adding new pipeline sources.

---

## Prompt template for AI-assisted integration

```
Add <SOURCE_NAME> as a SciAgent dataset pipeline source.

API docs: <URL>
Source ID: <registry_name>        # e.g. expression_atlas
Repository label: <UI name>       # e.g. Expression Atlas

Integration tier: dataset pipeline (required)

Auth: <none | API key env var>
Max results env: <VAR_NAME>=10

Trigger: dataset-discovery queries via is_dataset_discovery_query()

Follow docs/adding-a-source.md completely:
- Multi-strategy facet search (FACET_SEARCH_STRATEGIES)
- normalize → DatasetCandidate
- wire dataset_discovery.py + orchestrator routing
- dataset_search payload (not chat-only)
- repository-aware frontend labels
- tests for adapter + run_dataset_discovery
- README + .env.example
```

---

## Deployment notes

- `SCIAGENT_EXCLUDED_SOURCES` — block external databases (`geo_dataset_search`, `expression_atlas`, …)
- `SCIAGENT_EXCLUDED_TOOLS` — block agent steps (`summarize`)
- Restart server after `.env` changes
