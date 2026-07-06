# ImmPort golden queries

Developer-facing reference for representative **immunology** dataset-discovery queries against ImmPort. These complement the RNA-seq golden queries in [golden_queries.md](golden_queries.md), which focus on GEO and Expression Atlas.

ImmPort golden queries exercise multi-facet interpretation, ImmPort controlled vocabulary (disease, biosample type, assay method), the shared facet search strategies, supplemental `text_broad` free-text search, structured evidence extraction, and load-more pagination.

## Golden queries

1. Find public immunology datasets for asthma PBMC flow cytometry.
2. Find public datasets for influenza vaccine immune response.
3. Find public datasets for peanut allergy immune response.
4. Find public T cell datasets for tuberculosis.

## What each query exercises

| Query | Facets resolved | Primary regression focus |
|-------|-----------------|--------------------------|
| Asthma PBMC flow cytometry | disease + tissue + assay | Full strict → broad facet ladder plus `text_broad`; ImmPort CV for asthma, PBMC, Flow Cytometry; structured evidence on all three slots |
| Influenza vaccine immune response | disease only (`influenza`) | Disease-only facet search; `text_broad` carries vaccine / immune-response context not captured as facets |
| Peanut allergy immune response | disease only (`peanut allergy`) | Specific disease phrase resolution (peanut allergy over generic allergy); DOID grounding priority |
| T cell tuberculosis | disease + tissue | Disease + biosample type without assay; CL grounding for T cell; broad_1 vs broad_2 strategy mix |

## Expected interpretation and grounding

Current pipeline behavior (regex/phrase resolution + ontology grounding):

| Query | Interpreted facets | Grounded concepts |
|-------|-------------------|-------------------|
| Asthma PBMC flow cytometry | `disease=asthma`, `tissue=PBMC`, `assay=Flow Cytometry` | MONDO:0004979 (asthma), CL:2000001 (peripheral blood mononuclear cell), OBI:0000913 (Flow Cytometry) |
| Influenza vaccine immune response | `disease=influenza` | MONDO:0005812 (influenza) |
| Peanut allergy immune response | `disease=peanut allergy` | DOID:4378 (peanut allergy) |
| T cell tuberculosis | `disease=tuberculosis`, `tissue=T cell` | MONDO:0018076 (tuberculosis), CL:0000084 (T cell) |

Notes:

- **Organism** is not inferred from “immunology” or “public”; `species` is sent to ImmPort only when the user names an organism (e.g. “human”).
- **Influenza vaccine** and **immune response** are not separate facet slots today; supplemental `text_broad` search preserves that context in the free-text term.
- **Peanut allergy** must win over the shorter **allergy** match — see `test_peanut_allergy_query_prefers_specific_disease_over_generic_allergy`.

## ImmPort search strategies

Each query runs the shared facet strategies (`strict`, `broad_1`, `broad_2`, `broad_3`) plus ImmPort’s supplemental **`text_broad`** strategy (compact ad-hoc term with boilerplate stripped).

Expected search-term strings (facet strategies use ImmPort CV names; `text_broad` uses compact user phrasing):

| Query | strict | broad_1 | broad_2 | broad_3 | text_broad |
|-------|--------|---------|---------|---------|------------|
| Asthma PBMC flow cytometry | asthma Flow Cytometry PBMC | asthma Flow Cytometry | asthma PBMC | asthma | asthma PBMC flow cytometry |
| Influenza vaccine immune response | influenza | influenza | influenza | influenza | influenza vaccine immune response |
| Peanut allergy immune response | peanut allergy | peanut allergy | peanut allergy | peanut allergy | peanut allergy immune response |
| T cell tuberculosis | tuberculosis T cell | tuberculosis | tuberculosis T cell | tuberculosis | T cell tuberculosis |

Facet API calls use structured ImmPort parameters (`conditionOrDisease`, `biosampleType`, `assayMethod`). `text_broad` uses the `term` parameter only.

Implementation: `tools/immport_dataset_search.py` (`_resolve_search_queries`, `TEXT_BROAD_STRATEGY`).

## Pass/fail expectations (automated tests)

These queries are covered by unit and integration-style tests (mocked HTTP — no live ImmPort calls in CI):

| Query | Test files |
|-------|------------|
| Asthma PBMC flow cytometry | `tests/test_asthma_immport_query.py`, `tests/test_immport_evidence_extraction.py`, `tests/test_dataset_load_more.py` |
| Influenza vaccine immune response | — (interpretation only; add adapter tests when influenza-specific behavior is defined) |
| Peanut allergy immune response | `tests/test_facet_phrase_resolution.py`, `tests/test_ontology_grounding_priority.py` |
| T cell tuberculosis | `tests/test_facet_phrase_resolution.py` |

Shared ImmPort adapter coverage: `tests/test_immport_dataset_search.py`, `tests/test_immport_vocab.py`.

Run:

```bash
cd server
uv run pytest tests/test_asthma_immport_query.py tests/test_immport_evidence_extraction.py \
  tests/test_facet_phrase_resolution.py tests/test_immport_dataset_search.py tests/test_immport_vocab.py -q
```

## Running live against ImmPort

The main golden-query harness in [golden_queries.md](golden_queries.md) defaults to **GEO + Expression Atlas** only. To evaluate one ImmPort query through the same metrics pipeline, use the evaluation module directly with an explicit repository list:

```bash
cd server
uv run python -c "
from evaluation.golden_queries import evaluate_golden_query, format_report_text
report = evaluate_golden_query(
    'Find public immunology datasets for asthma PBMC flow cytometry.',
    repositories=['ImmPort'],
)
print(format_report_text(report))
"
```

Or run a single query in the UI / `POST /api/query` with other dataset sources excluded:

```bash
SCIAGENT_EXCLUDED_SOURCES=geo_dataset_search,expression_atlas,vivli
```

Ensure `immport` is **not** in `SCIAGENT_EXCLUDED_SOURCES`. Optional: `IMMPORT_MAX_RESULTS=10` (see `.env.example`).

## Related documentation

| Topic | Document |
|-------|----------|
| RNA-seq golden queries (GEO + GXA harness) | [golden_queries.md](golden_queries.md) |
| ImmPort adapter and wiring | [adding-a-source.md](../adding-a-source.md) |
| Ranking and evidence scoring | [dataset-ranking.md](../dataset-ranking.md) |
| Structured facet evidence | [adding-a-source.md](../adding-a-source.md#repository-aware-evidence-required-for-cv-backed-sources) |
