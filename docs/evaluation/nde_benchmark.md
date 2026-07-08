# Workplan: NDE benchmarking

**Status:** Planned (after ontology hierarchy MVP)  
**Last updated:** 2026-07-06

Plan for comparing SciAgent dataset discovery against the [NIAID Data Ecosystem Discovery API](https://api.data.niaid.nih.gov/) (NDE). NDE is a manually curated, ontology-aligned index — useful as a **gold comparator** for retrieval quality and for paper claims.

Implementation of hierarchy expansion itself is in [ontology-hierarchy-expansion.md](../roadmap/ontology-hierarchy-expansion.md).

---

## Why benchmark against NDE

NDE exposes curated facets (e.g. **Health Condition**: Asthma, Mild Asthma, Allergic rhinitis) backed by MONDO and related ontologies. SciAgent can be evaluated on:

1. **Retrieval overlap** — do we find the same studies/datasets NDE lists for a query?
2. **Recall gains from hierarchy** — does `hierarchy_broad` close gaps (e.g. Mild Asthma under Asthma)?
3. **Value beyond NDE** — multi-repo merge, evidence ranking, agent trace, context export

### Documented count divergence (ProteomeXchange)

An initial spot check for **Alzheimer disease + ProteomeXchange** shows NDE returning **~604** hits vs SciAgent **~251** (`total_found`) / **~174** (`primary_total_found` with brain tissue). This is expected: NDE assigns `healthCondition` from PubMed-linked MONDO terms; SciAgent’s ProteomeXchange connector uses OmicsDI **repository-submitted** `disease:` facets. Only ~43% of sampled NDE hits matched OmicsDI’s Alzheimer’s disease CV in a July 2026 review.

**Worked example:** [PXD017788](https://data.niaid.nih.gov/resources?id=pxd017788) — see [SciAgent strengths (early findings)](#sciagent-strengths-early-findings) below and the [detailed case study](proteomexchange_golden_queries.md#case-study-pxd017788-sciagent-vs-nde) in `proteomexchange_golden_queries.md`.

Full breakdown, example accession mismatches, and label-sensitivity notes: [proteomexchange_golden_queries.md — Result counts vs NIAID Data Ecosystem](proteomexchange_golden_queries.md#result-counts-vs-niaid-data-ecosystem).

### SciAgent strengths (early findings)

Lower SciAgent hit counts vs NDE are not automatically a coverage gap. An Alzheimer + ProteomeXchange spot check (July 2026) showed NDE **~604** vs SciAgent **~251** / **~174** (strict with brain tissue). [PXD017788](https://data.niaid.nih.gov/resources?id=pxd017788) is a worked example of why SciAgent’s approach can be **more precise**, not less capable:

| Dimension | SciAgent | NDE |
|-----------|----------|-----|
| **Retrieval model** | Facet-first: OmicsDI `disease:"…"` uses **repository-submitted** CV | `healthCondition` often expanded from **linked PubMed** (`fromPMID: true`) |
| **PXD017788** | **Excluded** — submitter disease CV is `Disease Free` | **Included** in Alzheimer set via PMID-linked MONDO tag |
| **Contradictory metadata** | Record not surfaced when structured disease ≠ query | Lists Alzheimer (PMID), histidinemia (PMID), and Disease Free (curated) together, unresolved |
| **Tissue** | Structured tissue (Erythrocyte, Monocyte, Bone Marrow) evaluated against query; brain facet in strict strategy | Alzheimer filter ignores tissue |
| **Assay** | `omics_type` + PRIDE `technology_type` (Mass Spectrometry, Gel-based experiment) | Same source strings map to conflicting `measurementTechnique` terms (e.g. gel-based → unrelated OBI class) |

**Takeaways for the benchmark narrative:**

1. **Facet-first retrieval** — SciAgent requires submitter disease CV to match the grounded facet. PXD017788 is annotated Disease Free, so it never enters the 251-hit set. NDE includes it in the 604 via PMID-linked `healthCondition`, not submitter metadata.

2. **Metadata fidelity over contradictory tags** — NDE can attach multiple incompatible health conditions with no resolution. SciAgent avoids surfacing records whose structured disease field does not match the query.

3. **Multi-facet query alignment** — Tissue and assay facets participate in search and evidence. A mouse macrophage study with non-brain tissue should not rank for *Alzheimer brain proteomics* even when literature mentions Alzheimer elsewhere.

4. **Assay clarity** — SciAgent normalizes proteomics from repository omics type and technology fields; NDE ontology mapping can mis-disambiguate the same PRIDE labels.

5. **Precision vs PMID-expanded recall** — The 604 vs 251 gap reflects SciAgent **refusing to treat literature co-occurrence as disease annotation**. PXD017788 is a mouse BMDM erythrophagocytosis study — lower SciAgent counts can mean **better query relevance**, not worse coverage.

Use PXD017788 as a **regression reference** when scoring NDE-only IDs: not every NDE-only hit is a SciAgent gap worth closing. Distinguish **true recall gaps** (same submitter CV, missed by SciAgent) from **PMID-inflated NDE recall** (submitter CV contradicts the filter).

Detail, API field dumps, and assay mis-mapping table: [proteomexchange_golden_queries.md — Case study PXD017788](proteomexchange_golden_queries.md#case-study-pxd017788-sciagent-vs-nde).

---

## Product goals

- Reproducible benchmark command for fixed queries
- Baseline (pre-hierarchy) and post-hierarchy result tables
- README section summarizing SciAgent vs NDE with honest trade-offs

---

## Research goals (NCBO resource index paper)

Position SciAgent as a modern index stack vs legacy NCBO-style portals:

| Legacy NCBO / portal index | SciAgent / LLM-era analogue |
|----------------------------|----------------------------|
| Manual ontology annotation | Automated grounding (OLS, BioPortal, curated seeds) |
| Static synonym tables | Classified synonyms + hierarchy expansion |
| Single-repository search | Multi-strategy, multi-repository merge |
| Opaque relevance | Evidence snippets, score breakdown, agent trace |
| Human browse facets | Optional UI: suggested related concepts |

Paper claims must be **evidence-backed** from this benchmark — not aspirational.

---

## Scope

### In scope

- Automated comparison script (SciAgent pipeline vs NDE API)
- Fixed query set with documented expected facets
- Metrics: ID overlap@k, incremental recall from `hierarchy_broad`, false-broadening spot checks
- Stored baseline results under `docs/evaluation/results/` (markdown or JSON summaries)

### Out of scope (initially)

- Scraping NDE web UI (use API only)
- Full facet-by-facet parity with NDE sidebar
- Continuous CI against live NDE (rate limits; optional nightly job later)

---

## Query set (initial)

| Query | Primary facets | NDE facet to compare | Repositories |
|-------|----------------|----------------------|--------------|
| asthma clinical trial datasets | disease | Health Condition | Vivli |
| COVID-19 treatment trials | disease | Health Condition | Vivli |
| tuberculosis vaccine studies | disease | Health Condition | Vivli, ImmPort |
| ulcerative colitis RNA-seq colon | disease+tissue+assay | multi-facet | GEO, GXA, ImmPort |
| influenza PBMC flow cytometry | disease+tissue+assay | multi-facet | ImmPort |

Extend as sources and hierarchy expansion mature.

---

## Metrics

| Metric | Definition |
|--------|------------|
| **ID overlap@k** | Intersection of SciAgent top-k accessions (NCT, SDY, GSE, …) with NDE top-k IDs |
| **SciAgent-only** | IDs SciAgent returns that NDE does not (multi-repo or broader strategies) |
| **NDE-only** | IDs NDE returns that SciAgent misses (hierarchy / curation gaps) |
| **NDE-only classification** | Split NDE-only IDs into *submitter-CV match* vs *PMID-only tag* (PXD017788 = PMID-only) |
| **Strict vs hierarchy delta** | Incremental recall when `hierarchy_broad` enabled |
| **False broadening rate** | Manual spot check: unrelated disease in expanded hits |

---

## Implementation phases

### Phase 1 — Script stub (~4 hours)

- [ ] `server/scripts/compare_nde.py` (or pytest module)
- [ ] Input: natural-language query
- [ ] Output: SciAgent IDs, NDE IDs (`api.data.niaid.nih.gov/v1/query`), overlap report
- [ ] Document NDE catalog filter parity with Vivli adapter

### Phase 2 — Baseline run (~4 hours)

- [ ] Run 5 queries **before** hierarchy expansion
- [ ] Save summaries to `docs/evaluation/results/nde_baseline_YYYY-MM-DD.md`
- [ ] Note largest NDE-only gaps (e.g. Mild Asthma)

### Phase 3 — Post-hierarchy run (~4 hours)

- [ ] Re-run after [ontology-hierarchy-expansion](../roadmap/ontology-hierarchy-expansion.md) MVP
- [ ] Compare strict-only vs hierarchy-enabled
- [ ] Update README with summary table

### Phase 4 — Paper & narrative (~ongoing)

- [ ] Draft paper outline (NCBO index → SciAgent stack)
- [ ] Highlight SciAgent-only features in benchmark appendix
- [ ] Optional: related-conditions UI chips fed from OLS children

---

## NDE API notes

- Production: `https://api.data.niaid.nih.gov/v1/query`
- Vivli scope: `(includedInDataCatalog.name:"Vivli" OR includedInDataCatalog.name:"accessclinicaldata@NIAID")`
- Disease facet field: `healthCondition.name` (labels); `healthCondition.identifier` + `inDefinedTermSet:MONDO` (IDs)
- Compare API counts to NDE portal facets when validating (e.g. Asthma ≈ 348 on Vivli catalog)

---

## Acceptance criteria

1. One command reproduces overlap report for all queries in the initial set.
2. Baseline and post-hierarchy result files checked into `docs/evaluation/results/`.
3. README links to this doc and states limitations honestly.
4. Hierarchy MVP shows measurable recall improvement on at least one query (e.g. asthma child terms).

---

## Open questions

1. Benchmark NDE API only, or also spot-check portal facet counts manually?
2. Should benchmark run in CI or remain a manual release checklist?
3. Paper target venue and timeline — drives polish for Phase 4.

---

## Related docs

| Doc | Relevance |
|-----|-----------|
| [ontology-hierarchy-expansion.md](../roadmap/ontology-hierarchy-expansion.md) | Prerequisite enhancement |
| [golden_queries.md](golden_queries.md) | Existing regression harness |
| [immport_golden_queries.md](immport_golden_queries.md) | Immunology query fixtures |
| [proteomexchange_golden_queries.md](proteomexchange_golden_queries.md) | ProteomeXchange queries; PXD017788 case study detail |
| [vivli_golden_queries.md](vivli_golden_queries.md) | Vivli clinical trial query fixtures |
| [dataset-ranking.md](../dataset-ranking.md) | How related hits are scored |
| [project-status.md](../project-status.md) | Update when benchmark ships |
