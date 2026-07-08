# OmicsDI golden queries

Developer-facing reference for representative **multi-omics** dataset-discovery queries against OmicsDI. These complement the RNA-seq golden queries in [golden_queries.md](golden_queries.md) (GEO + Expression Atlas) and the immunology queries in [immport_golden_queries.md](immport_golden_queries.md).

OmicsDI golden queries exercise multi-facet interpretation, OmicsDI controlled vocabulary (`disease`, `tissue`, `omics_type`, `technology_type`, `TAXONOMY`), query-level omics-type inference when the assay facet is absent, the shared facet search strategies, structured evidence from dataset detail metadata, and load-more pagination.

## Golden queries

1. Find public RNA-seq datasets for ulcerative colitis colon tissue.
2. Find public proteomics datasets for asthma lung tissue.
3. Find public proteomics datasets for Alzheimer's disease brain tissue.
4. Find public proteomics datasets for breast cancer breast tissue.
5. Find public metabolomics datasets for inflammatory bowel disease serum.
6. Find public proteomics datasets for tuberculosis macrophages.

## What each query exercises

| Query | Facets resolved | Primary regression focus |
|-------|-----------------|--------------------------|
| UC colon RNA-seq | disease + tissue + assay | Full strict → broad facet ladder; OmicsDI `Transcriptomics` mapping from RNA-seq; colon + ulcerative colitis CV |
| Asthma lung proteomics | disease + tissue; assay inferred from query | Disease + tissue facets plus omics-type inference from “proteomics” in the query string |
| Alzheimer brain proteomics | disease + tissue; assay inferred from query | Multi-word disease phrase (`Alzheimer disease`); brain tissue; proteomics inference |
| Breast cancer proteomics | disease + tissue + assay | Disease + `breast tissue` via anatomy regex; full strict → broad facet ladder |
| IBD serum metabolomics | disease + tissue + assay | Multi-word disease; serum via anatomy regex; metabolomics assay grounding |

## Expected interpretation and grounding

Current pipeline behavior (regex/phrase resolution + ontology grounding):

| Query | Interpreted facets | Grounded concepts (representative) |
|-------|-------------------|----------------------------------|
| UC colon RNA-seq | `disease=ulcerative colitis`, `tissue=colon`, `assay=RNA-seq` | MONDO:0005101 (ulcerative colitis), UBERON:0001155 (colon); assay maps to OmicsDI `Transcriptomics` |
| Asthma lung proteomics | `disease=asthma`, `tissue=lung`, `assay=proteomics` | MONDO:0004979 (asthma), UBERON:0002048 (lung), OBI:0003781 (proteomics) |
| Alzheimer brain proteomics | `disease=Alzheimer disease`, `tissue=brain`, `assay=proteomics` | MONDO:0004975 (Alzheimer disease), UBERON:0000955 (brain), OBI:0003781 (proteomics) |
| Breast cancer proteomics | `disease=breast cancer`, `tissue=breast`, `assay=proteomics` | MONDO:0007254 (breast cancer), UBERON:0000310 (breast), OBI:0003781 (proteomics) |
| IBD serum metabolomics | `disease=inflammatory bowel disease`, `tissue=serum`, `assay=metabolomics` | MONDO:0005265 (inflammatory bowel disease), UBERON:0001977 (serum), OBI:0003782 (metabolomics) |

Notes:

- **Organism** is not inferred from “public”; `TAXONOMY:"9606"` is added only when the user names an organism (e.g. `human`).
- **Proteomics / metabolomics** in the query text populate the `assay` facet via regex and map to OmicsDI `omics_type` filters. RNA-seq and flow cytometry use the same pattern.
- **Assay evidence:** OmicsDI metadata uses `Transcriptomics` / `Proteomics` / etc.; `domain/omicsdi_assay.py` normalizes these to observed assays (`RNA-seq`, `proteomics`, …) so the query match summary marks assay **Supported** instead of **Absent**.
- **Breast cancer breast tissue** resolves disease and tissue: `breast tissue` matches via `domain/tissue_anatomy.py`; `breast` inside `breast cancer` is excluded by negative lookahead.
- **Serum** matches via `domain/tissue_anatomy.py` and maps to OmicsDI `tissue:"Serum"`.

## OmicsDI search strategies

Each query runs the shared facet strategies (`strict`, `broad_1`, `broad_2`, `broad_3`). When no facets resolve, an **`adhoc`** compact free-text strategy runs.

Expected OmicsDI query strings (facet strategies use OmicsDI field syntax):

| Query | strict | broad_1 | broad_2 | broad_3 |
|-------|--------|---------|---------|---------|
| UC colon RNA-seq | `disease:"ulcerative colitis" AND omics_type:"Transcriptomics" AND tissue:"Colon"` | `disease:"ulcerative colitis" AND omics_type:"Transcriptomics"` | `disease:"ulcerative colitis" AND tissue:"Colon"` | `disease:"ulcerative colitis"` |
| Asthma lung proteomics | `disease:"asthma" AND omics_type:"Proteomics" AND tissue:"Lung"` | `disease:"asthma" AND omics_type:"Proteomics"` | `disease:"asthma" AND tissue:"Lung"` | `disease:"asthma"` |
| Alzheimer brain proteomics | `disease:"Alzheimer's disease" AND omics_type:"Proteomics" AND tissue:"Brain"` | `disease:"Alzheimer's disease" AND omics_type:"Proteomics"` | `disease:"Alzheimer's disease" AND tissue:"Brain"` | `disease:"Alzheimer's disease"` |
| Breast cancer proteomics | `disease:"Breast cancer" AND omics_type:"Proteomics" AND tissue:"Breast"` | `disease:"Breast cancer" AND omics_type:"Proteomics"` | `disease:"Breast cancer" AND tissue:"Breast"` | `disease:"Breast cancer"` |
| IBD serum metabolomics | `disease:"inflammatory bowel disease" AND omics_type:"Metabolomics" AND tissue:"Serum"` | `disease:"inflammatory bowel disease" AND omics_type:"Metabolomics"` | `disease:"inflammatory bowel disease" AND tissue:"Serum"` | `disease:"inflammatory bowel disease"` |

Implementation: `tools/omicsdi_dataset_search.py` (`_build_omicsdi_api_query`, `build_facet_search_queries`).

## Pass/fail expectations (automated tests)

These queries are covered by unit and integration-style tests (mocked HTTP — no live OmicsDI calls in CI):

| Query | Test files |
|-------|------------|
| UC colon RNA-seq | `tests/test_omicsdi_vocab.py`, `tests/test_omicsdi_assay.py`, `tests/test_omicsdi_evidence_extraction.py` |
| Asthma lung proteomics | `tests/test_omicsdi_dataset_search.py` (multi-strategy builder) |
| Alzheimer brain proteomics | `tests/test_omicsdi_vocab.py` (Alzheimer alias) |
| Breast cancer proteomics | `tests/test_breast_cancer_omicsdi_query.py`, `tests/test_omicsdi_evidence_extraction.py`, `tests/test_omicsdi_dataset_search.py` |
| IBD serum metabolomics | `tests/test_ibd_metabolomics_omicsdi_query.py`, `tests/test_omicsdi_vocab.py`, `tests/test_tissue_anatomy.py` |

Shared OmicsDI adapter coverage: `tests/test_omicsdi_dataset_search.py`, `tests/test_omicsdi_vocab.py`.

Run:

```bash
cd server
uv run pytest tests/test_breast_cancer_omicsdi_query.py tests/test_ibd_metabolomics_omicsdi_query.py \
  tests/test_omicsdi_evidence_extraction.py tests/test_omicsdi_dataset_search.py \
  tests/test_omicsdi_vocab.py tests/test_tissue_anatomy.py -q
```

## Running live against OmicsDI

The main golden-query harness in [golden_queries.md](golden_queries.md) defaults to **GEO + Expression Atlas**. To evaluate one OmicsDI query through the same metrics pipeline:

```bash
cd server
uv run python -c "
from evaluation.golden_queries import evaluate_golden_query, format_report_text
report = evaluate_golden_query(
    'Find public RNA-seq datasets for ulcerative colitis colon tissue.',
    repositories=['OmicsDI'],
)
print(format_report_text(report))
"
```

Or run a single query in the UI / `POST /api/query` with other dataset sources excluded:

```bash
SCIAGENT_EXCLUDED_SOURCES=geo_dataset_search,expression_atlas,immport,vivli
```

Ensure `omicsdi` is **not** in `SCIAGENT_EXCLUDED_SOURCES`. Optional: `OMICSDI_MAX_RESULTS=10` (see `.env.example`).

## Related documentation

| Topic | Document |
|-------|----------|
| RNA-seq golden queries (GEO + GXA harness) | [golden_queries.md](golden_queries.md) |
| ImmPort immunology golden queries | [immport_golden_queries.md](immport_golden_queries.md) |
| OmicsDI adapter and wiring | [adding-a-source.md](../adding-a-source.md) |
| Ranking and evidence scoring | [dataset-ranking.md](../dataset-ranking.md) |
| Structured facet evidence | [adding-a-source.md](../adding-a-source.md#repository-aware-evidence-required-for-cv-backed-sources) |
