# Project status

Orientation page for reviewers and new contributors. For setup, architecture, and deep dives, follow the links at the bottom — this page does not repeat those docs.

## Currently supported

**Integrated dataset discovery**

- **GEO** and **Expression Atlas** are integrated into one ranked result list (merge, de-duplication, shared UI).
- Natural-language queries are interpreted into **disease**, **tissue/anatomy**, **assay**, and **organism** facets.
- Facets are **ontology-grounded** with facet-aware provider priority (curated aliases, OLS, optional BioPortal/LLM).
- Clinical abbreviation handling works (e.g. **UC** → ulcerative colitis when context supports it).
- Repository hits are normalized into shared **dataset candidates** with evidence snippets and metadata warnings.
- **Integrated ranking** orders merged results using `evidence_score` plus `rank_tier`, including assay-aware partial sub-tiers for RNA-seq queries.
- **Context export** produces structured agent context from a dataset search payload.

**Evaluation**

- A **golden-query** regression harness exercises the full dataset-discovery pipeline (interpret through context export) against fixed queries.

**Beyond dataset discovery**

- The standard agent path (gene, literature, ClinVar, structure, summarize tools) is documented in the README; it uses a separate trace path from dataset discovery.

## Not implemented yet

| Area | Status |
|------|--------|
| File / download **manifest discovery** | Not implemented |
| **BioStudies** / **ArrayExpress** | Not implemented |
| **Local / private** data connectors | Not implemented |

## Where to read more

| Topic | Document |
|-------|----------|
| Setup, architecture, tool inventory, query examples, interpretation caveats | [README.md](../README.md) |
| Integrated ranking model (`evidence_score`, `rank_tier`, assay sub-tiers) | [docs/dataset-ranking.md](dataset-ranking.md) |
| Golden-query harness, metrics, and pass/fail checks | [docs/evaluation/golden_queries.md](evaluation/golden_queries.md) |
| Adding a new repository to the dataset pipeline | [docs/adding-a-source.md](adding-a-source.md) |
