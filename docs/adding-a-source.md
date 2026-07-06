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

**Related docs:** [dataset-access-ui.md](dataset-access-ui.md) (controlled-access badges and manifest export), [dataset-ranking.md](dataset-ranking.md) (ranking and evidence scoring).

---

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

### Ontology grounding (OBO Foundry domains)

Facet slots map to **OBO Foundry registry domains** as the starting policy for which ontologies to search and accept. The single source of truth is `domain/ontology_providers/obo_foundry_policy.py`:

| Facet slot | OBO Foundry domain(s) | Primary ontologies |
|------------|----------------------|-------------------|
| disease | `health`, `phenotype` (HP fallback) | MONDO, DOID, EFO (+ HP fallback) |
| tissue / biosample | `anatomy and development` | UBERON, CL |
| assay | `investigations`, `biological systems` | OBI, GO |
| organism | `organisms` | NCBITaxon |
| phenotype | `phenotype` | HP |

Add a new ontology by appending an `OntologyBinding` with the correct `obo_foundry_domain` and `tier`. Derived tables (`FACET_ONTOLOGIES`, `SLOT_CURIE_PREFIXES`, primary/fallback tiers) are built from that registry. Non-Foundry ontologies (e.g. EFO) may be listed with `obo_foundry_domain=None` when repository metadata depends on them.

#### Adding facet terms (when users query concepts your repo supports)

Interpretation and grounding happen **before** repository search and are shared across all dataset sources. When a new repository exposes controlled vocabulary terms users will type in queries (e.g. ImmPort `lkSampleType` values like **T cell**, **PBMC**), wire them through this chain:

| Step | File | What to add |
|------|------|-------------|
| 1. Ontology policy | `domain/ontology_providers/obo_foundry_policy.py` | `OntologyBinding` if the concept needs a new ontology prefix (e.g. CL for cell types) |
| 2. Query interpretation | `domain/tissue_anatomy.py` or `domain/ontology_providers/curated.py` | Regex pattern + curated seed (canonical label, CURIE, synonyms) so phrase/regex resolution fills the facet slot |
| 3. Repository search | `domain/repository_vocab/<repo>_vocab.py` | Map grounded label → API controlled vocabulary name (static override and/or lookup table resolver) |
| 4. Evidence | Adapter `normalize_*` | Copy the same CV strings into `metadata_fields` — see [Repository-aware evidence](#repository-aware-evidence-required-for-cv-backed-sources) |
| 5. Tests | See [Test templates](#test-templates) | Interpretation + grounding + vocab + structured evidence (not title keywords alone) |

**Example (T cell on ImmPort):** CL binding in `obo_foundry_policy.py` → regex in `tissue_anatomy.py` → `("tissue", "t cell"): "T cell"` in `immport_vocab.py` → `biosample_type` on normalized records → `test_facet_phrase_resolution.py` + `test_immport_evidence_extraction.py`.

Run `pytest tests/test_obo_foundry_policy.py tests/test_facet_phrase_resolution.py` after ontology changes.

#### ImmPort-only: supplemental and fallback text search

These behaviors are implemented in `tools/immport_dataset_search.py` today; other repositories should adopt only when their API has an equivalent free-text mode.

| Strategy | When it runs | User control |
|----------|--------------|--------------|
| **`text_broad`** | After facet strategies, when at least one facet was resolved | UI checkbox **Include text_broad free-text supplement** (`include_text_broad`; default from `SCIAGENT_IMMPORT_TEXT_BROAD`) |
| **`adhoc`** | When **no** facets were resolved — last-resort compact free-text (`term` only) | Runs regardless of checkbox (today); facet strategies are skipped |

ImmPort `text_broad` rules:

- Append after `strict` → `broad_3`; mark `supplemental: true` in strategy summaries.
- Use `term` only — do **not** combine with facet params in one request (NDE/CDT parity).
- Set `total_found` / `primary_total_found` from facet strategies only; return **`text_broad_total_found`** separately so the UI can show dual counts (e.g. 312 facet · 1,328 text_broad).

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

## Wiring map (all touchpoints)

Adding a dataset pipeline source touches **several registries**. The adapter module alone is not enough.

| # | File | Purpose | Required? |
|---|------|---------|-----------|
| 1 | `server/tools/<source>_dataset_search.py` | Search, normalize, pagination, `dataset_search` payload shape | **Yes** |
| 2 | `server/domain/dataset_repository_registry.py` | Pipeline dispatch, load-more routing, merge priority | **Yes** |
| 3 | `server/agent/registry.py` | Register tool so the agent can invoke the source | **Yes** |
| 4 | `server/sciagent_server/config.py` → `SOURCE_NAMES` | Enable/disable via `SCIAGENT_EXCLUDED_SOURCES` | **Yes** |
| 5 | `server/domain/source_registry.py` | **`GET /api/config`** source list (display name, access profile, implemented flag) | **Yes** for UI visibility |
| 6 | `server/agent/orchestrator.py` | Multi-source dataset discovery uses enabled repos from the dataset registry automatically | **No manual edit** — ensure `tool_name` matches `registry.py` |
| 7 | `domain/repository_vocab/<repo>_vocab.py` | CV mapping for facet search params | When API uses controlled vocab |
| 8 | `domain/tissue_anatomy.py` / `curated.py` / `obo_foundry_policy.py` | New query terms users will type | When repo introduces new facet labels |
| 9 | `.env.example`, `README.md`, this doc | Env vars, example query, reference table row | **Yes** |

**Orchestrator:** `_resolve_dataset_repositories()` reads `dataset_repository_registry.py` and returns every repository whose `tool_name` is registered (respecting `SCIAGENT_EXCLUDED_SOURCES`), in merge **priority** order. No hardcoded repo list in the orchestrator.

**What you usually do *not* edit:** `agent/orchestrator.py` repository list, `agent/dataset_discovery.py` dispatch (reads dataset registry), `main.py` load-more endpoint (routes via registry), dataset UI load-more button (generic).

---

## Central registry (dataset pipeline dispatch)

**All dataset pipeline repositories are registered in:**

`server/domain/dataset_repository_registry.py`

This registry drives:

- Initial search dispatch (`search_repository`)
- Record normalization
- Max-result env resolution
- **Load-more routing** (`POST /api/dataset-search/more`) — no per-source edits in `main.py`
- Multi-repository cursor selection (highest-priority repo with pagination)
- Tool enablement checks via `tool_name` + `SCIAGENT_EXCLUDED_SOURCES`

When you add a source, **add one `DatasetRepositorySpec` entry** plus the other rows in the [wiring map](#wiring-map-all-touchpoints) above.

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

### UI / API config entry (`source_registry.py`)

Add a `SourceRegistryEntry` in `server/domain/source_registry.py` so **`GET /api/config`** exposes the source to the frontend (Resources panel, access profile, enabled state):

```python
MY_REPO_SOURCE_ID: SourceRegistryEntry(
    id="my_repo",                        # matches tool_name / exclusion id
    display_name="My Repository",
    source_type="dataset_repository",
    domain="immunology",               # human-readable grouping for UI
    access_profile="open_or_registered", # see dataset-access-ui.md
    implemented=True,
    tool_name="my_repo",
    repository_label="My Repository",    # must match DatasetRepositorySpec.repository
    source_label="My Repository API",
),
```

Set `implemented=False` for planned stubs (see VDJServer entry). Controlled-access flows are documented in [dataset-access-ui.md](dataset-access-ui.md).

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

Use this with the [wiring map](#wiring-map-all-touchpoints). Check off every row before opening a PR.

### 1. Tool / adapter module (`server/tools/<source>_dataset_search.py` or extend existing)

- [ ] `fetch_<repo>_repository_records(concept_mappings, max_results, query, interpreted_query, ...)`
- [ ] Multi-strategy search using `build_facet_search_queries`
- [ ] **`fetch_more_<repo>_repository_records(cursor)`** when the API paginates
- [ ] Cursor builder sets `repository`, `strategy_offsets`, `strategy_totals`, `seen_accessions`, `has_more`
- [ ] `normalize_<repo>_record()` → `DatasetCandidate` with correct `repository` field
- [ ] `collect_metadata_fields()` for evidence extraction (title, summary, taxon, assay hints)
- [ ] **Repository-aware evidence:** copy structured facet values into `metadata_fields` (`condition_or_disease`, `biosample_type`, `assay_method` when applicable) — see [Repository-aware evidence](#repository-aware-evidence-required-for-cv-backed-sources)
- [ ] If source has controlled access metadata, wire access fields for [dataset-access-ui.md](dataset-access-ui.md)
- [ ] Env var for max results (e.g. `MY_REPO_MAX_RESULTS`)
- [ ] Unit tests with mocked HTTP — see [Test templates](#test-templates)

### 2. Register in `domain/dataset_repository_registry.py`

- [ ] Add `DatasetRepositorySpec` with `tool_name`, handlers, `priority`, `accession_prefixes`
- [ ] Set `fetch_more_records` when paginated; leave `None` otherwise

### 3. Agent tool + deployment config

- [ ] Register chat/sidebar tool in `server/agent/registry.py`
- [ ] Add to `SOURCE_NAMES` in `server/sciagent_server/config.py`
- [ ] Add `SourceRegistryEntry` in `server/domain/source_registry.py` (`implemented=True`, matching `repository_label`)
- [ ] Document in `.env.example` and README tool inventory

### 4. Orchestrator routing

- [ ] Confirm `tool_name` in `DatasetRepositorySpec` matches the name registered in `registry.py` (orchestrator auto-includes enabled repos)
- [ ] Confirm dataset queries use `_run_dataset_discovery()` only — **do not** also route the same query through the simple tool path in `_plan()`

`agent/dataset_discovery.py` dispatch reads the dataset registry; no changes there if step 2 is complete.

### 5. Facet terms and vocabulary (when the repo uses CV facets)

- [ ] `domain/repository_vocab/<repo>_vocab.py` — search-time facet param mapping
- [ ] Curated aliases / anatomy patterns if users query terms not in OLS — see [Adding facet terms](#adding-facet-terms-when-users-query-concepts-your-repo-supports)
- [ ] Tests: vocab resolver + interpretation for at least one representative query

### 6. Frontend (repository-aware labels)

- [ ] Use `datasetSearch.repository` instead of hardcoded "GEO" in result panels / action bar
- [ ] Load-more needs no source-specific UI code — `DatasetActionBar` checks `has_more && load_more_cursor`
- [ ] No frontend change required for `/api/config` if `source_registry.py` entry is correct

### 7. Documentation

- [ ] README example query
- [ ] This file — add row to [Reference implementations](#reference-implementations) table
- [ ] [dataset-access-ui.md](dataset-access-ui.md) if access discovery applies

---

## Checklist: simple source (non-dataset)

Use only when the source is **not** an omics dataset repository.

1. Implement `server/tools/<source>.py` with normalized `{results, total_found, source}` payload
2. Register in `registry.py` + `SOURCE_NAMES`
3. Add orchestrator keyword routing in `_plan()` and `_extract_tool_parameters()`
4. Add chat formatter in `_final_synthesis()`
5. Tests + README

---

## Test templates

Copy patterns from existing tests rather than starting from scratch.

| Concern | ImmPort examples | GEO / shared examples |
|---------|------------------|------------------------|
| Adapter HTTP + strategies | `tests/test_immport_dataset_search.py` | `tests/test_geo_search_strategies.py` |
| End-to-end query + search params | `tests/test_asthma_immport_query.py` | — |
| Repository vocab resolver | `tests/test_immport_vocab.py` | — |
| Structured facet evidence | `tests/test_immport_evidence_extraction.py` | `tests/test_ranking_facet_quality.py` |
| Load-more cursor | `tests/test_dataset_load_more.py` | `tests/test_dataset_load_more.py` |
| Interpretation + grounding | `tests/test_facet_phrase_resolution.py` | `tests/test_tissue_anatomy.py` |
| Ontology policy | `tests/test_obo_foundry_policy.py` | `tests/test_ontology_grounding_priority.py` |
| Multi-repo merge | — | `tests/test_multi_repository_dataset_discovery.py` |

**Minimum bar for a new CV-backed repository:**

1. Mocked adapter test — strategies, params, pagination (initial + load-more if applicable).
2. Vocab test — grounded label maps to API facet value.
3. Evidence test — `metadata_fields` with structured CV alone yields **Supported** in annotation (no title keyword required).
4. One integration-style test — representative user query through `interpret_dataset_query` + adapter search param builder.

Run: `pytest tests/test_<your_repo>_*.py tests/test_facet_phrase_resolution.py -q`

---

## Reference implementations

| Source | Module | Registry | Load-more | Tests | Notes |
|--------|--------|----------|-----------|-------|-------|
| GEO | `tools/geo_dataset_search.py` | Yes | Yes | `test_geo_search_strategies.py`, `test_geo_max_results.py` | NCBI `retstart` per strategy |
| Expression Atlas | `tools/expression_atlas.py` | Yes | No (single-shot) | `test_gxa_dataset_discovery.py` | EBI Search + GXA JSON enrich |
| ImmPort | `tools/immport_dataset_search.py` | Yes | Yes | `test_immport_*.py`, `test_asthma_immport_query.py` | `text_broad` / `adhoc`; structured evidence fields |
| Vivli | `tools/vivli_dataset_search.py` | Yes | Yes | `test_vivli_*.py`, `test_asthma_vivli_query.py` | NIAID Discovery API; Vivli + AccessClinicalData@NIAID catalogs; NCT accessions |
| OmicsDI | `tools/omicsdi_dataset_search.py` | Yes | Yes | `test_omicsdi_*.py`, `test_breast_cancer_omicsdi_query.py` | OmicsDI REST API; disease/tissue/omics_type facets; detail enrichment |
| PubMed | `tools/pubmed.py` | — | — | — | Simple literature source |

---

## Repository resolution (orchestrator)

When a query matches `is_dataset_discovery_query()`:

1. Search **all enabled** dataset repositories (GEO, Expression Atlas, ImmPort when all are on)
2. Merge results with canonical de-duplication (`GSE12345` ↔ `E-GEOD-12345`; keep GXA-only studies like `E-MTAB-*`)
3. Prefer GEO metadata when the same study appears in both sources
4. Rank the merged candidate set once by evidence coverage

If only one repository is enabled, behavior is unchanged (single-source pipeline).

Enabled repositories are resolved from `dataset_repository_registry.py` via `resolve_enabled_dataset_repositories()` (see [Wiring map](#wiring-map-all-touchpoints)).

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
- Wiring map: adapter, dataset_repository_registry, registry.py, SOURCE_NAMES, source_registry
- Multi-strategy facet search (FACET_SEARCH_STRATEGIES)
- Facet terms: obo_foundry_policy + curated/tissue_anatomy + repository_vocab when needed
- normalize → DatasetCandidate + repository-aware evidence (structured metadata_fields)
- fetch_more + DatasetSearchCursor when API paginates
- dataset_search payload (not chat-only); text_broad only if API supports ImmPort-style supplemental search
- Tests: adapter + vocab + structured evidence + representative query (see Test templates section)
- README + .env.example + row in Reference implementations table
- dataset-access-ui.md if controlled access applies
```

---

## Deployment notes

- `SCIAGENT_EXCLUDED_SOURCES` — block external databases (`geo_dataset_search`, `expression_atlas`, `immport`, …). Load-more for a repository is disabled when its `tool_name` is excluded.
- `SCIAGENT_EXCLUDED_TOOLS` — block agent steps (`summarize`)
- Restart server after `.env` changes
