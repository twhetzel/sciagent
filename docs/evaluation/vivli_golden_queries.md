# Vivli golden queries

Developer-facing reference for representative **clinical trial** dataset-discovery queries against Vivli and AccessClinicalData@NIAID via the [NIAID Data Ecosystem Discovery API](https://api.data.niaid.nih.gov/). These complement the RNA-seq golden queries in [golden_queries.md](golden_queries.md), the immunology queries in [immport_golden_queries.md](immport_golden_queries.md), and the NDE benchmark plan in [nde_benchmark.md](nde_benchmark.md).

Vivli golden queries exercise disease-focused interpretation, NIAID `healthCondition.name` facet search, Vivli / AccessClinicalData catalog scoping, structured evidence from trial metadata (`healthCondition`, `measurementTechnique`), controlled-access discovery, and load-more pagination.

## Golden queries

1. Find clinical trial datasets for asthma.
2. Find COVID-19 treatment trial datasets.
3. Find tuberculosis vaccine studies.

## What each query exercises

| Query | Facets resolved | Primary regression focus |
|-------|-----------------|--------------------------|
| Asthma clinical trials | `disease=asthma`; `assay=clinical trial` (phrase) | Catalog scope + `healthCondition.name:"asthma"`; NCT accessions; structured disease evidence |
| COVID-19 treatment trials | Partial (`disease` phrase resolution) | COVID-19 alias via `vivli_vocab`; treatment wording not yet a separate facet |
| Tuberculosis vaccine studies | `disease=tuberculosis` | Disease-only facet ladder; vaccine context in free text / adhoc strategy |

## Expected interpretation and grounding

Current pipeline behavior (regex/phrase resolution + ontology grounding):

| Query | Interpreted facets | Grounded concepts (representative) |
|-------|-------------------|-----------------------------------|
| Asthma clinical trials | `disease=asthma`, `assay=clinical trial` | MONDO:0004979 (asthma); assay phrase from query text |
| COVID-19 treatment trials | `disease` (see notes) | `vivli_vocab` maps `covid-19` → `COVID-19` when phrase resolves |
| Tuberculosis vaccine studies | `disease=tuberculosis` | MONDO:0018076 (tuberculosis) |

Notes:

- **Clinical trial** is not a curated OBI assay seed today; it is extracted as a query phrase and may appear in Vivli `measurementTechnique` metadata (e.g. `Randomized Clinical Trial`).
- **Organism** defaults to human in normalized Vivli records when species is absent; facet search does not filter by species unless the user names an organism.
- **COVID-19 treatment trials** — phrase resolution may not yet isolate `COVID-19` as disease (known gap: `treatment` can be mis-parsed). Prefer `Find clinical trial datasets for COVID-19` until disease regex/phrase coverage improves.
- **Vaccine** is not a separate facet slot; vaccine context is carried in adhoc / broad free-text search terms when facets are sparse.

## Vivli search strategies

Each query runs the shared facet strategies (`strict`, `broad_1`, `broad_2`, `broad_3`). All strategies prepend the catalog scope:

```
(includedInDataCatalog.name:"Vivli" OR includedInDataCatalog.name:"accessclinicaldata@NIAID")
```

Expected NIAID Discovery API query fragments:

| Query | strict (representative) | broad_3 |
|-------|-------------------------|---------|
| Asthma clinical trials | `… AND healthCondition.name:"asthma" AND "clinical trial"` | `… AND healthCondition.name:"asthma"` |
| Tuberculosis vaccine studies | `… AND healthCondition.name:"tuberculosis"` | same |

Implementation: `tools/vivli_dataset_search.py` (`_build_vivli_api_query`, `VIVLI_CATALOG_SCOPE`).

## Pass/fail expectations (automated tests)

| Query | Test files |
|-------|------------|
| Asthma clinical trials | `tests/test_asthma_vivli_query.py`, `tests/test_vivli_dataset_search.py`, `tests/test_vivli_evidence_extraction.py` |
| Shared Vivli adapter | `tests/test_vivli_vocab.py`, `tests/test_vivli_dataset_search.py` |

Run:

```bash
cd server
uv run pytest tests/test_asthma_vivli_query.py tests/test_vivli_evidence_extraction.py \
  tests/test_vivli_dataset_search.py tests/test_vivli_vocab.py -q
```

## Running live against Vivli

To evaluate one Vivli query through the golden-query metrics pipeline:

```bash
cd server
uv run python -c "
from evaluation.golden_queries import evaluate_golden_query, format_report_text
report = evaluate_golden_query(
    'Find clinical trial datasets for asthma',
    repositories=['Vivli'],
)
print(format_report_text(report))
"
```

Or run in the UI / `POST /api/query` with other dataset sources excluded:

```bash
SCIAGENT_EXCLUDED_SOURCES=geo_dataset_search,expression_atlas,immport,omicsdi,proteomexchange
```

Ensure `vivli` is **not** in `SCIAGENT_EXCLUDED_SOURCES`. Optional: `VIVLI_MAX_RESULTS=10` (see `.env.example`).

## Related documentation

| Topic | Document |
|-------|----------|
| RNA-seq golden queries (GEO + GXA harness) | [golden_queries.md](golden_queries.md) |
| ImmPort immunology golden queries | [immport_golden_queries.md](immport_golden_queries.md) |
| NDE benchmark (Vivli comparison queries) | [nde_benchmark.md](nde_benchmark.md) |
| Controlled-access UI | [dataset-access-ui.md](../dataset-access-ui.md) |
| Vivli adapter and wiring | [adding-a-source.md](../adding-a-source.md) |
