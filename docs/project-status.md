# Project status

Orientation page for reviewers and new contributors. For setup, architecture, and deep dives, follow the links at the bottom — this page does not repeat those docs.

## Currently supported

**Integrated dataset discovery**

- **GEO**, **Expression Atlas**, **ImmPort**, **Vivli**, **OmicsDI**, **ProteomeXchange**, and **VDJServer** are integrated into one ranked result list (merge, de-duplication, shared UI).
- Natural-language queries are interpreted into **disease**, **tissue/anatomy**, **assay**, and **organism** facets.
- Facets are **ontology-grounded** with facet-aware provider priority (curated aliases, OLS, optional BioPortal/LLM).
- Clinical abbreviation handling works (e.g. **UC** → ulcerative colitis when context supports it).
- Repository hits are normalized into shared **dataset candidates** with evidence snippets and metadata warnings.
- **Integrated ranking** orders merged results using `evidence_score` plus `rank_tier`, including assay-aware partial sub-tiers for RNA-seq queries.
- **Context export** produces structured agent context from a dataset search payload.

**Evaluation**

- A **golden-query** regression harness exercises the full dataset-discovery pipeline (interpret through context export) against fixed RNA-seq queries (GEO + Expression Atlas).
- **ImmPort golden queries** cover representative immunology searches (asthma PBMC flow cytometry, influenza vaccine, peanut allergy, tuberculosis T cell).
- **OmicsDI golden queries** cover representative multi-omics searches (UC colon RNA-seq, asthma lung proteomics, Alzheimer brain proteomics, breast cancer proteomics).
- **ProteomeXchange golden queries** cover representative proteomics searches (Alzheimer brain, breast cancer, asthma lung).
- **Vivli golden queries** cover representative clinical trial searches (asthma trials, COVID-19 treatment trials, tuberculosis vaccine studies).
- **VDJServer golden queries** cover representative immune repertoire searches (COVID-19 BCR blood, ESCC lung TCR).

**Beyond dataset discovery**

- The standard agent path (gene, literature, ClinVar, structure, summarize tools) is documented in the README; it uses a separate trace path from dataset discovery.

## Not implemented yet

| Area | Status |
|------|--------|
| File / download **manifest discovery** | Backend access discovery for GEO and Expression Atlas; UI manifest export |
| **Ontology hierarchy expansion** | Planned shared retrieval enhancement (`hierarchy_broad` strategy); see workplan |
| **NDE benchmarking** | Planned comparator vs NIAID Data Ecosystem API; see workplan |
| **Local / private** data connectors | Not implemented |

## Where to read more

| Topic | Document |
|-------|----------|
| Setup, architecture, tool inventory, query examples, interpretation caveats | [README.md](../README.md) |
| Integrated ranking model (`evidence_score`, `rank_tier`, assay sub-tiers) | [docs/dataset-ranking.md](dataset-ranking.md) |
| Golden-query harness, metrics, and pass/fail checks | [docs/evaluation/golden_queries.md](evaluation/golden_queries.md) |
| ImmPort immunology golden queries | [docs/evaluation/immport_golden_queries.md](evaluation/immport_golden_queries.md) |
| OmicsDI multi-omics golden queries | [docs/evaluation/omicsdi_golden_queries.md](evaluation/omicsdi_golden_queries.md) |
| ProteomeXchange proteomics golden queries | [docs/evaluation/proteomexchange_golden_queries.md](evaluation/proteomexchange_golden_queries.md) |
| Vivli clinical trial golden queries | [docs/evaluation/vivli_golden_queries.md](evaluation/vivli_golden_queries.md) |
| VDJServer immune repertoire golden queries | [docs/evaluation/vdjserver_golden_queries.md](evaluation/vdjserver_golden_queries.md) |
| Adding a new repository to the dataset pipeline | [docs/adding-a-source.md](adding-a-source.md) |
| Dataset access UI (manifest, access details scaffolding) | [docs/dataset-access-ui.md](dataset-access-ui.md) |
| Ontology hierarchy expansion (planned) | [docs/roadmap/ontology-hierarchy-expansion.md](roadmap/ontology-hierarchy-expansion.md) |
| NDE benchmarking & paper evaluation (planned) | [docs/evaluation/nde_benchmark.md](evaluation/nde_benchmark.md) |
| ProteomeXchange vs NDE count comparison (documented) | [docs/evaluation/proteomexchange_golden_queries.md](evaluation/proteomexchange_golden_queries.md#result-counts-vs-niaid-data-ecosystem) |
| PXD017788 case study (SciAgent vs NDE) | [docs/evaluation/nde_benchmark.md](evaluation/nde_benchmark.md#sciagent-strengths-early-findings) · [detail](evaluation/proteomexchange_golden_queries.md#case-study-pxd017788-sciagent-vs-nde) |
