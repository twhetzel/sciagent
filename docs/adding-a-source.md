# Adding a new data source

This guide is the recipe for integrating external repositories into SciAgent Studio. Follow it when adding sources like GEO, Expression Atlas, ImmPort, or future omics archives.

## Integration tiers

| Tier | When to use | User experience |
|------|-------------|-----------------|
| **Simple source** | Keyword lookup, single API call, no facet grounding | Chat + trace tool result (e.g. PubMed, MyGene) |
| **Dataset pipeline source** | Repository supports disease/tissue/assay discovery with metadata | **Dataset discovery UI** — ranked cards, facets, evidence, strategies, load-more (required when API paginates) |

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
  → 5. Annotate Evidence     (domain/dataset_annotation.py + evidence_extraction.py)
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

**Organism / species:** only set `InterpretedQuery.organism` when the user names an organism (e.g. `human`, `Homo sapiens`, `mouse`). Do **not** default to human for disease-only queries — repository adapters pass species filters only when `organism` is present (ImmPort, Expression Atlas, etc.).

**ImmPort supplemental text:** after facet strategies, append a `text_broad` strategy (`term` only, no facet params). Mark it `supplemental: true` in strategy summaries. Use facet-only max for `total_found` (NDE parity); do not combine `term` with facet filters in one request.

### Repository-aware evidence (required for CV-backed sources)

Facet **search** and facet **evidence** are separate steps. Search may filter by repository controlled vocabulary (e.g. ImmPort `assayMethod=Flow Cytometry`), but the query match summary / ranking only credit facets when returned metadata supports them.

For sources with structured facet fields, the adapter **must** copy them into `DatasetCandidate.metadata_fields` using the shared field names in `domain/evidence_extraction.py`:

| Slot | Metadata field | ImmPort API field |
|------|----------------|-------------------|
| disease | `condition_or_disease` | `conditionOrDisease` |
| tissue | `biosample_type` | `biosampleType` |
| assay | `assay_method` | `assayMethod` |

Also populate `title`, `summary`, and `taxon` via `collect_metadata_fields()`. For ImmPort, pass `assay_method` into `gdstype` as well so legacy GEO-style assay hints still apply where relevant.

`domain/evidence_extraction.py` matches grounded concepts against these structured fields (comma-separated CV values supported). Without this wiring, studies returned by strict facet search can incorrectly show **Absent** in the UI coverage table even when the repository facet filter matched.

When adding a new CV-backed repository:

1. Map API facet params using `domain/repository_vocab/<repo>_vocab.py` (search time).
2. Copy the same resolved values into the metadata field names above (annotation time).
3. Add tests that annotation marks disease/tissue/assay **supported** from structured fields alone (no keyword in title/summary required).

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
    "has_more": false,
    "load_more_cursor": null,   # required when has_more is true — see Load-more below
}
```

---

## Central registry (required wiring step)

**All dataset pipeline repositories are registered in one place:**

`server/domain/dataset_repository_registry.py`

This registry drives:

- Initial search dispatch (`search_repository`)
- Record normalization
- Max-result env resolution
- **Load-more routing** (`POST /api/dataset-search/more`) — no per-source edits in `main.py`
- Multi-repository cursor selection (highest-priority repo with pagination)
- Tool enablement checks via `tool_name` + `SCIAGENT_EXCLUDED_SOURCES`

When you add a source, **add one `DatasetRepositorySpec` entry**. The pipeline, API endpoint, and UI load-more button work automatically once the adapter implements pagination correctly.

```python
MY_REPO: DatasetRepositorySpec(
    repository="My Repository",          # DatasetCandidate.repository label
    tool_name="my_repo",                 # registry.py tool name / exclusion id
    source_display="My Repository API",  # dataset_search.source default
    priority=3,                          # merge + cursor precedence (lower = higher)
    accession_prefixes=("MR-",),         # multi-repo normalize / dedupe hints
    fetch_records=fetch_my_repo_repository_records,
    fetch_more_records=fetch_more_my_repo_repository_records,  # None if API cannot page
    normalize_records=normalize_my_repo_records,
    resolve_max_results=get_my_repo_max_results,
)
```

Also add the tool name to `SOURCE_NAMES` in `server/sciagent_server/config.py` and register the sidebar tool in `server/agent/registry.py`.

---

## Load-more (required when the API paginates)

The **Load more** button appears when **both** `has_more` and `load_more_cursor` are present. Setting `has_more: true` without a cursor produces a dead button — avoid that.

### Adapter contract

Implement in `server/tools/<source>_dataset_search.py`:

1. **`fetch_<repo>_repository_records(...)`** — first batch
   - Count all strategies (`pageSize=0` or equivalent)
   - Retrieve first batch up to `max_results`
   - Track `strategy_offsets`, `strategy_totals`, `seen_accessions` (and `seen_ids` if the API uses opaque IDs)
   - Build a `DatasetSearchCursor` with `repository="<label>"` and `has_more` from remaining strategy pages
   - Return `load_more_cursor: cursor.model_dump()` whenever `has_more` is true

2. **`fetch_more_<repo>_repository_records(cursor: DatasetSearchCursor)`** — next batch
   - Resume from cursor offsets / seen sets
   - Return new `records`, updated `load_more_cursor`, and `has_more`
   - Same shape as GEO / ImmPort (`source`, `repository`, optional `error`)

Use **`domain/dataset_search.py` → `DatasetSearchCursor`** for cursor fields. Set **`repository`** on the cursor so load-more routing works even if the client sends an empty candidate list.

### Reference pagination patterns

| Source | Paging mechanism | Cursor fields |
|--------|------------------|---------------|
| GEO | NCBI `retstart` / `retmax` per strategy | `strategy_offsets`, `strategy_totals`, `seen_ids`, `seen_accessions` |
| ImmPort | `fromRecord` + `pageSize` per strategy | `strategy_offsets` (1-based next row), `strategy_totals`, `seen_accessions` |

If your API cannot paginate (single-shot result set), set `fetch_more_records=None` in the registry, `has_more: false`, and `load_more_cursor: null`.

### Multi-repository searches

When GEO + ImmPort (or others) run together, **one cursor** is returned — from the **highest-priority** registered repo that still has pages (`pick_load_more_cursor`). Load-more continues that repository’s batch until exhausted; it does not interleave sources in one click.

---

## Checklist: dataset pipeline source

### 1. Tool / adapter module (`server/tools/<source>_dataset_search.py` or extend existing)

- [ ] `fetch_<repo>_repository_records(concept_mappings, max_results, query, interpreted_query, ...)`
- [ ] Multi-strategy search using `build_facet_search_queries`
- [ ] **`fetch_more_<repo>_repository_records(cursor)`** when the API paginates
- [ ] Cursor builder sets `repository`, `strategy_offsets`, `strategy_totals`, `seen_accessions`, `has_more`
- [ ] `normalize_<repo>_record()` → `DatasetCandidate` with correct `repository` field
- [ ] `collect_metadata_fields()` for evidence extraction (title, summary, taxon, assay hints)
- [ ] **Repository-aware evidence:** copy structured facet values into `metadata_fields` (`condition_or_disease`, `biosample_type`, `assay_method` when applicable) — see [Repository-aware evidence](#repository-aware-evidence-required-for-cv-backed-sources)
- [ ] Tests that structured facet fields alone produce supported facet evidence (not title/summary keywords only)
- [ ] Env var for max results (e.g. `MY_REPO_MAX_RESULTS`)
- [ ] Unit tests with mocked HTTP (initial search **and** load-more)

### 2. Register in `domain/dataset_repository_registry.py`

- [ ] Add `DatasetRepositorySpec` with `tool_name`, handlers, `priority`, `accession_prefixes`
- [ ] Set `fetch_more_records` when paginated; leave `None` otherwise

### 3. Wire into orchestrator (`server/agent/orchestrator.py`)

- [ ] Add repository to `_resolve_dataset_repositories()` (searches all enabled repos)
- [ ] Dataset queries call `_run_dataset_discovery(query, repositories=...)`
- [ ] Do **not** also route the same query through the simple tool path in `_plan()`

No changes needed in `agent/dataset_discovery.py` dispatch if the registry entry is complete.

### 4. Registry + deployment config

- [ ] Register chat/sidebar tool in `server/agent/registry.py`
- [ ] Add to `SOURCE_NAMES` in `server/sciagent_server/config.py`
- [ ] Document in `.env.example` and README tool inventory

### 5. Frontend (repository-aware labels)

- [ ] Use `datasetSearch.repository` instead of hardcoded "GEO" in:
  - `web/src/components/DatasetResultsPanel.jsx`
  - `web/src/components/DatasetActionBar.jsx`
  - `web/src/components/TracePanel.jsx` (optional)
- [ ] Load-more needs no source-specific UI code — `DatasetActionBar` checks `has_more && load_more_cursor`

### 6. Optional: repository vocabulary (Option C)

- [ ] If the API uses controlled vocabularies, add `domain/repository_vocab/<repo>_vocab.py` and map facets before search

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

| Source | Module | Registry | Load-more | Notes |
|--------|--------|----------|-----------|-------|
| GEO | `tools/geo_dataset_search.py` | Yes | Yes | NCBI `retstart` per strategy |
| Expression Atlas | `tools/expression_atlas.py` | Yes | No (single-shot) | EBI Search + GXA JSON enrich |
| ImmPort | `tools/immport_dataset_search.py` | Yes | Yes | Shared Data API `fromRecord`; structured facet evidence via `assay_method`, `biosample_type`, `condition_or_disease` |
| PubMed | `tools/pubmed.py` | — | — | Simple literature source |

---

## Repository resolution (orchestrator)

When a query matches `is_dataset_discovery_query()`:

1. Search **all enabled** dataset repositories (GEO, Expression Atlas, ImmPort when all are on)
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
Source ID: <registry_name>        # e.g. omicsdi
Repository label: <UI name>       # e.g. OmicsDI
API paginates: <yes | no>         # if yes, implement load-more on day one

Integration tier: dataset pipeline (required)

Auth: <none | API key env var>
Max results env: <VAR_NAME>=10

Trigger: dataset-discovery queries via is_dataset_discovery_query()

Follow docs/adding-a-source.md completely:
- Multi-strategy facet search (FACET_SEARCH_STRATEGIES)
- normalize → DatasetCandidate
- repository-aware evidence (structured facet fields in metadata_fields)
- fetch_more + DatasetSearchCursor when API paginates
- Register DatasetRepositorySpec in domain/dataset_repository_registry.py
- orchestrator routing (_resolve_dataset_repositories)
- dataset_search payload (not chat-only)
- repository-aware frontend labels
- tests for adapter + run_dataset_discovery + load-more
- README + .env.example
```

---

## Deployment notes

- `SCIAGENT_EXCLUDED_SOURCES` — block external databases (`geo_dataset_search`, `expression_atlas`, `immport`, …). Load-more for a repository is disabled when its `tool_name` is excluded.
- `SCIAGENT_EXCLUDED_TOOLS` — block agent steps (`summarize`)
- Restart server after `.env` changes
