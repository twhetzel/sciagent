# ProteomeXchange golden queries

Developer-facing reference for representative **proteomics** dataset-discovery queries against ProteomeXchange. These complement the multi-omics queries in [omicsdi_golden_queries.md](omicsdi_golden_queries.md) and the RNA-seq golden queries in [golden_queries.md](golden_queries.md).

ProteomeXchange golden queries exercise multi-facet interpretation, OmicsDI REST field syntax scoped to ProteomeXchange member repositories (PRIDE, MassIVE, jPOST, PeptideAtlas, PanoramaPublic, iProX, NODE), proteomics-only filtering, the shared facet search strategies, structured evidence from dataset detail metadata, and load-more pagination.

## Golden queries

1. Find public proteomics datasets for Alzheimer's disease brain tissue.
2. Find public proteomics datasets for breast cancer breast tissue.
3. Find public proteomics datasets for asthma lung tissue.

## What each query exercises

| Query | Facets resolved | Primary regression focus |
|-------|-----------------|--------------------------|
| Alzheimer brain proteomics | disease + tissue; assay inferred from query | Multi-word disease phrase (`Alzheimer disease`); brain tissue; proteomics inference; repository scope |
| Breast cancer proteomics | disease + tissue; assay inferred from query | Disease + `breast tissue` anatomy pattern (avoids matching `breast` inside `breast cancer`); proteomics inference |
| Asthma lung proteomics | disease + tissue; assay inferred from query | Disease + tissue facets plus omics-type inference from “proteomics” in the query string |

## Expected interpretation and grounding

Current pipeline behavior (regex/phrase resolution + ontology grounding):

| Query | Interpreted facets | Grounded concepts (representative) |
|-------|-------------------|----------------------------------|
| Alzheimer brain proteomics | `disease=Alzheimer disease`, `tissue=brain`, `assay` inferred | MONDO:0004975 (Alzheimer disease), UBERON:0000955 (brain) |
| Breast cancer proteomics | `disease=breast cancer`, `tissue=breast`, `assay` inferred | MONDO:0007254 (breast cancer), UBERON:0000310 (breast) |
| Asthma lung proteomics | `disease=asthma`, `tissue=lung`, `assay` inferred | MONDO:0004979 (asthma), UBERON:0002048 (lung) |

Notes:

- **Organism** is not inferred from “public”; `TAXONOMY:"9606"` is added only when the user names an organism (e.g. `human`).
- **Proteomics** in the query text maps to `omics_type:"Proteomics"` when the assay facet slot is empty (`tools/proteomexchange_dataset_search.py` → `_infer_assay_from_query`). The adapter always applies a proteomics filter because ProteomeXchange is proteomics-only.
- **Assay evidence:** OmicsDI metadata uses `Proteomics`; `domain/omicsdi_assay.py` normalizes these to observed assays (`proteomics`) so the query match summary marks assay **Supported** instead of **Absent**.
- **Breast cancer breast tissue** resolves both disease and tissue: regex matches `breast tissue` (or `breast` not followed by `cancer`); `breast` inside `breast cancer` is skipped via negative lookahead in `domain/tissue_anatomy.py`.
- Dataset URLs resolve to [ProteomeCentral](https://proteomecentral.proteomexchange.org/) (`PXD*` accessions).
- **Metabolomics / RNA-seq / genomics queries** should use [OmicsDI](../evaluation/omicsdi_golden_queries.md), not ProteomeXchange. SciAgent skips ProteomeXchange when the interpreted assay is incompatible, so metabolomics queries do not return unrelated proteomics hits with absent assay evidence.

## ProteomeXchange search strategies

Each query runs the shared facet strategies (`strict`, `broad_1`, `broad_2`, `broad_3`). When no facets resolve, an **`adhoc`** compact free-text strategy runs.

All strategies are wrapped with a ProteomeXchange repository scope:

```
(repository:pride OR repository:MassIVE OR repository:jPOST OR repository:PeptideAtlas OR repository:PanoramaPublic OR repository:iProX OR repository:NODE)
```

Expected query strings (facet portion uses OmicsDI field syntax):

| Query | strict | broad_1 | broad_2 | broad_3 |
|-------|--------|---------|---------|---------|
| Alzheimer brain proteomics | `disease:"Alzheimer's disease" AND omics_type:"Proteomics" AND tissue:"Brain"` | `disease:"Alzheimer's disease" AND omics_type:"Proteomics"` | `disease:"Alzheimer's disease" AND tissue:"Brain"` | `disease:"Alzheimer's disease"` |
| Breast cancer proteomics | `disease:"Breast cancer" AND omics_type:"Proteomics" AND tissue:"Breast"` | `disease:"Breast cancer" AND omics_type:"Proteomics"` | `disease:"Breast cancer" AND tissue:"Breast"` | `disease:"Breast cancer"` |
| Asthma lung proteomics | `disease:"asthma" AND omics_type:"Proteomics" AND tissue:"Lung"` | `disease:"asthma" AND omics_type:"Proteomics"` | `disease:"asthma" AND tissue:"Lung"` | `disease:"asthma"` |

Implementation: `tools/proteomexchange_dataset_search.py` (`_build_proteomexchange_api_query`, `build_facet_search_queries`).

## Result counts vs NIAID Data Ecosystem

SciAgent’s ProteomeXchange connector searches via the **OmicsDI REST API** with structured facet filters. The [NIAID Data Ecosystem](https://data.niaid.nih.gov/) (NDE) indexes the same underlying PXD datasets but uses a **different disease model**. Do not expect hit counts to match NDE when comparing facet-backed SciAgent searches.

### Example: Alzheimer disease (July 2026 spot check)

| Source | Query / filter | Count | What it means |
|--------|----------------|------:|---------------|
| [NDE web UI](https://data.niaid.nih.gov/search?q=Alzheimer%27s+disease&use_ai_search=false&filters=%28includedInDataCatalog.name%3A%28%22ProteomeXchange%22%29%29+AND+%28healthCondition.name.raw%3A%28%22Alzheimer+disease%22%29%29) | `includedInDataCatalog.name:"ProteomeXchange"` + `healthCondition.name.raw:"Alzheimer disease"` | **604** | NIAID Discovery API; catalog + condition filter only (no tissue) |
| SciAgent `total_found` | Golden query: *Alzheimer brain proteomics*; max across strategies (`broad_1` / `broad_3`) | **251** | OmicsDI: PX member repos + `disease:"Alzheimer's disease"` + `omics_type:"Proteomics"` |
| SciAgent `primary_total_found` | Same query; **strict** strategy (disease + proteomics + brain tissue) | **174** | OmicsDI adds `tissue:"Brain"` |
| OmicsDI (live) | PX scope + `disease:"Alzheimer's disease"` (no proteomics filter) | **252** | Proteomics filter removes only ~1 hit — not the main gap |
| OmicsDI (live) | PX scope + free-text `Alzheimer` | **294** | Keyword recall; still below NDE |

SciAgent reports **`total_found`** as the maximum count across facet strategies and **`primary_total_found`** as the strict-strategy count. For the Alzheimer golden query, `total_found` (251) reflects disease-wide proteomics hits; `primary_total_found` (174) reflects the tighter disease + brain match.

### Why NDE returns more hits

The gap (~604 vs ~251) is **not** caused by repository scope or the proteomics filter. Sampled NIAID ProteomeXchange hits are present in OmicsDI; the difference is **how disease is assigned**:

| | NIAID (NDE) | SciAgent (OmicsDI facets) |
|--|-------------|---------------------------|
| **API** | NIAID Discovery API (`api.data.niaid.nih.gov/v1/query`) | OmicsDI REST (`omicsdi.org/ws/dataset/search`) |
| **Disease field** | `healthCondition.name` (schema.org `HealthCondition`) | OmicsDI `disease:"…"` controlled vocabulary |
| **Evidence source** | Often **PubMed-linked** (`fromPMID: true`) — MONDO terms inferred from associated literature | **Repository-submitted** disease annotations on the dataset record |
| **Recall vs precision** | Higher recall: tags datasets when Alzheimer appears in linked papers, even if submitters used another primary disease label | Higher precision: only datasets whose structured metadata carries the Alzheimer’s disease CV term |

In a sample of 30 top NIAID Alzheimer + ProteomeXchange hits, only **13 (43%)** also matched OmicsDI `disease:"Alzheimer's disease"`. Typical mismatches:

| Accession | NIAID `healthCondition` includes | OmicsDI structured `disease` |
|-----------|-----------------------------------|------------------------------|
| PXD032402 | Alzheimer disease (from PMID) | Gerstmann-Straussler-Scheinker syndrome |
| PXD017788 | Alzheimer disease (from PMID) | Disease Free |
| PXD013710 | Alzheimer disease (from PMID) | Parkinson's Disease |
| PXD000437 | Alzheimer disease (from PMID) | *(empty)* |
| PXD013869 | Alzheimer disease (from PMID) | *(empty)* |

Many extra NDE hits are weak matches for facet-driven discovery (e.g. mouse macrophage or unrelated-tissue studies tagged via publication co-occurrence). SciAgent’s lower count aligns with **submitter-curated CV evidence**, which also powers the ranked dataset panel’s disease **Supported / Absent** column.

### Case study: PXD017788 (SciAgent vs NDE)

[NDE resource page](https://data.niaid.nih.gov/resources?id=pxd017788) · [ProteomeCentral](https://proteomecentral.proteomexchange.org/cgi/GetDataset?ID=PXD017788) · [PRIDE/OmicsDI](https://www.omicsdi.org/dataset/pride/PXD017788)

**Study:** *Mouse BMDMs and Erythrophagocytosis LCMSMS* — mouse bone marrow–derived macrophages (BMDMs) and erythrophagocytosis of IgG-coated RBCs. Keywords: Mouse, BMDMs, LCMSMS, RBCs. This is a **mouse macrophage physiology** study, not human Alzheimer brain proteomics.

#### NDE metadata (July 2026 API review)

NDE includes PXD017788 in the [Alzheimer + ProteomeXchange search set (604 hits)](https://data.niaid.nih.gov/search?q=Alzheimer%27s+disease&use_ai_search=false&filters=%28includedInDataCatalog.name%3A%28%22ProteomeXchange%22%29%29+AND+%28healthCondition.name.raw%3A%28%22Alzheimer+disease%22%29%29) because `healthCondition` lists **three** conditions simultaneously:

| `healthCondition.name` | Source | Notes |
|------------------------|--------|-------|
| **Alzheimer disease** | `fromPMID: true` (MONDO:0004975) | Inferred from linked publication text — not submitter disease annotation |
| **histidinemia** | `fromPMID: true` (MONDO:0009345) | Same PMID-expansion path; unrelated to the study design |
| **Disease Free** | `isCurated: true` (NCIT:C173158) | Matches repository submitter label (`disease-free`) |

A user filtering NDE by Alzheimer disease will see this dataset even though the **curated submitter label is “Disease Free”** and the title/description describe mouse erythrophagocytosis. NDE surfaces contradictory disease tags without resolving which label is authoritative.

**Assay / measurement technique disambiguation failures** on the same record:

| PRIDE / submitter label | NDE `measurementTechnique.name` | Ontology | Problem |
|-------------------------|----------------------------------|----------|---------|
| `Not available` | `DELETE` | *(empty)* | Placeholder mapped to a sentinel “DELETE” term |
| `Mass Spectrometry` | `mass spectrometry` (MMO) + `mass spectrometry assay` (OBI) | MMO, OBI | Acceptable duplicate mapping |
| `Gel-based experiment` | `gel electrophoresis` (MMO) | MMO | Reasonable |
| `Gel-based experiment` | **`epitope protection experiment based on survival`** (OBI) | OBI | **Mis-disambiguation** — gel-based proteomics mapped to an unrelated OBI assay class |

The same source string (`Gel-based experiment`) maps to both a sensible technique (gel electrophoresis) and a biologically unrelated OBI term. NDE does not pick a single canonical assay for display or filtering.

#### SciAgent behavior for the same record

For query *Find public proteomics datasets for Alzheimer's disease brain tissue* (July 2026 live check):

| Dimension | SciAgent | NDE |
|-----------|----------|-----|
| **Retrieval** | **Not returned** — OmicsDI facet search `disease:"Alzheimer's disease" AND PXD017788` → count **0** | **Included** in Alzheimer + ProteomeXchange result set |
| **Structured disease** (submitter CV) | `Disease Free` | Also lists Disease Free, but Alzheimer (PMID) overrides discoverability |
| **Structured tissue** | `Erythrocyte`, `Monocyte`, `Bone Marrow` — **not brain** | Not used for the Alzheimer filter |
| **Assay** | `Proteomics` (from `omics_type`); technology `Mass Spectrometry`, `Gel-based experiment` | Conflicting / mis-mapped `measurementTechnique` terms (see above) |
| **Organism** | *Mus musculus* (mouse) | Present in description; not part of Alzheimer filter |

**Why SciAgent does better here:** facet search respects **repository-submitted disease CV**, so this study never enters the Alzheimer candidate pool. Tissue and assay evidence come from the same structured OmicsDI fields used for ranking and the query-match summary. The study is simply not relevant to an Alzheimer brain proteomics query — it does not appear in SciAgent results for this query.

#### Takeaway

PXD017788 is a concrete example where **NDE recall inflates Alzheimer counts with PMID-linked tags** that contradict submitter disease labels, while **SciAgent’s facet-first retrieval avoids surfacing the record**. It also illustrates why NDE `measurementTechnique` normalization needs disambiguation review. Use this accession as a regression reference when implementing NDE benchmark overlap metrics ([nde_benchmark.md — SciAgent strengths](nde_benchmark.md#sciagent-strengths-early-findings)).

### Label sensitivity (OmicsDI)

OmicsDI disease facet matching is **label-sensitive**. The apostrophe form matters:

- `disease:"Alzheimer's disease"` → ~251–252 hits (correct mapping from grounded `Alzheimer disease`)
- `disease:"Alzheimer disease"` (no apostrophe) → **1** hit

The adapter maps grounded labels through `domain/repository_vocab/proteomexchange_vocab.py` (reusing OmicsDI CV aliases).

### When to use which count

- **SciAgent UI / API counts** — use for regression tests and user-facing discovery; reflects structured facet search and evidence alignment.
- **NDE counts** — use as an **external recall benchmark** (see [nde_benchmark.md](nde_benchmark.md)); expect NDE ≥ SciAgent for the same disease label.
- **Strict vs broad in SciAgent** — when the user names tissue (e.g. brain), treat **`primary_total_found` (strict)** as the facet-faithful total; **`total_found` (max)** includes broader disease-only strategies.

Closing the NDE gap would require either a supplemental free-text strategy (OmicsDI keyword ~294 for Alzheimer) or a separate NIAID Discovery connector — not a fix to repository scope alone.

## Pass/fail expectations (automated tests)

These queries are covered by unit and integration-style tests (mocked HTTP — no live ProteomeXchange calls in CI):

| Query | Test files |
|-------|------------|
| Alzheimer brain proteomics | `tests/test_proteomexchange_golden_queries.py`, `tests/test_proteomexchange_vocab.py` |
| Breast cancer proteomics | `tests/test_proteomexchange_golden_queries.py`, `tests/test_proteomexchange_evidence_extraction.py` |
| Asthma lung proteomics | `tests/test_proteomexchange_golden_queries.py`, `tests/test_proteomexchange_dataset_search.py` |

Shared ProteomeXchange adapter coverage: `tests/test_proteomexchange_dataset_search.py`, `tests/test_proteomexchange_vocab.py`.

Run:

```bash
cd server
uv run pytest tests/test_proteomexchange_golden_queries.py tests/test_proteomexchange_evidence_extraction.py \
  tests/test_proteomexchange_dataset_search.py tests/test_proteomexchange_vocab.py -q
```

## Running live against ProteomeXchange

To evaluate one ProteomeXchange query through the golden-query metrics pipeline:

```bash
cd server
uv run python -c "
from evaluation.golden_queries import evaluate_golden_query, format_report_text
report = evaluate_golden_query(
    \"Find public proteomics datasets for Alzheimer's disease brain tissue.\",
    repositories=['ProteomeXchange'],
)
print(format_report_text(report))
"
```

Or run a single query in the UI / `POST /api/query` with other dataset sources excluded:

```bash
SCIAGENT_EXCLUDED_SOURCES=geo_dataset_search,expression_atlas,immport,vivli,omicsdi
```

Ensure `proteomexchange` is **not** in `SCIAGENT_EXCLUDED_SOURCES`. Optional: `PROTEOMEXCHANGE_MAX_RESULTS=10` (see `.env.example`).

## Related documentation

| Topic | Document |
|-------|----------|
| Multi-omics golden queries (OmicsDI) | [omicsdi_golden_queries.md](omicsdi_golden_queries.md) |
| RNA-seq golden queries (GEO + GXA harness) | [golden_queries.md](golden_queries.md) |
| ProteomeXchange adapter and wiring | [adding-a-source.md](../adding-a-source.md) |
| Ranking and evidence scoring | [dataset-ranking.md](../dataset-ranking.md) |
| Structured facet evidence | [adding-a-source.md](../adding-a-source.md#repository-aware-evidence-required-for-cv-backed-sources) |
| NDE count comparison (ProteomeXchange vs OmicsDI) | [proteomexchange_golden_queries.md](proteomexchange_golden_queries.md#result-counts-vs-niaid-data-ecosystem) |
