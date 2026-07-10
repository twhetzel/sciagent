# Repository facet field capabilities

**Last updated:** 2026-07-09

Cross-repository inventory of **what you can filter on at search time**, **what comes back in API responses**, and **how records are normalized** for evidence and ranking. Use this when adding a source, debugging missed facets, or comparing SciAgent to NDE/CDT field names.

**Machine-readable registry:** `server/domain/repository_facet_capabilities.py`  
**Access in code:** `get_repository_spec("ImmPort").facet_capabilities`

---

## SciAgent canonical facet schema

All dataset pipeline adapters normalize facet-relevant metadata into shared keys on `DatasetCandidate.metadata_fields`. Evidence extraction in `domain/evidence_extraction.py` reads these names:

| Facet slot | Canonical field | Also used for evidence |
|------------|-----------------|------------------------|
| disease | `condition_or_disease` | `title`, `summary` |
| tissue | `biosample_type` | `title`, `summary`, `sample_titles` |
| assay | `assay_method` | `gdstype`, `platformtitle`, `ptechtype`, repo-specific assay fields |
| organism | `taxon` | `title`, `summary`, `platformtaxa`, `sample_titles` |

**Evidence tiers**

| Tier | Meaning |
|------|---------|
| **structured_cv** | Controlled vocabulary field; search filter and evidence use the same CV string |
| **structured** | Dedicated API field (not necessarily a lookup table) |
| **inferred** | Structured raw field mapped to a canonical assay/tissue label via helper (e.g. `gdstype`, `omicsdi_omics_type`, `airr_observed_assay`) |
| **narrative** | Title/summary/sample text only — no structured disease/tissue field |
| **mixed** | Structured response + weak or free-text search filter |

---

## Semantic types (SmartAPI / Biolink alignment)

SciAgent facet slots map to [Biolink Model](https://w3id.org/biolink/vocab/) semantic types and [identifiers.org](https://identifiers.org/) value namespaces, following the [SmartAPI](https://smart-api.info/) OpenAPI extension pattern (`x-parameterType`, `x-valueType`, `x-responseValueType`).

Dataset repository adapters (GEO, ImmPort, OmicsDI, …) are **not** fully catalogued in the SmartAPI registry today. **`repository_facet_capabilities.py` is SciAgent's aggregated source of truth** for those services; semantic URIs make the inventory compatible with SmartAPI and BioThings Explorer tooling.

| SciAgent slot | Biolink semantic type | Accepted identifier namespaces |
|---------------|----------------------|--------------------------------|
| disease | `biolink:Disease` | MONDO, DOID, EFO |
| tissue | `biolink:AnatomicalEntity` | UBERON, CL (cell types) |
| assay | `biolink:Assay` | OBI, GO, NCIT |
| organism | `biolink:OrganismTaxon` | NCBI Taxonomy |

Defined in code as `FACET_SLOT_SEMANTICS` in `server/domain/repository_facet_capabilities.py`. Each `FacetSlotCapability` inherits these defaults and can override per repository if needed.

**SmartAPI-style exports from code:**

```python
cap = get_facet_capability("ImmPort").slot_capability("disease")
cap.resolved_semantic_type_uri()       # https://w3id.org/biolink/vocab/Disease
cap.resolved_value_type_uris()         # (http://identifiers.org/mondo, ...)
cap.smartapi_parameter_annotation()    # x-parameterType + x-valueType for search filters
cap.smartapi_response_value_types()    # x-path + x-valueType per structured raw field
```

Narrative-only slots (e.g. GEO disease/tissue) omit `x-responseValueType` entries because responses lack structured facet fields.

## Summary comparison

| Repository | disease filter | tissue filter | assay filter | organism filter | text_broad | Vocab module |
|------------|---------------|---------------|--------------|-----------------|------------|--------------|
| **GEO** | free-text `term` | free-text | free-text | ✗ | ✗ | — |
| **Expression Atlas** | free-text `query` | free-text | free-text | post-filter `species` | ✗ | — |
| **ImmPort** | `conditionOrDisease` | `biosampleType` | `assayMethod` | `species` | ✓ | `immport_vocab` |
| **Vivli** | `healthCondition.name` | `sample.sampleType.name` | quoted free-text | post-filter | ✓ | `vivli_vocab` |
| **OmicsDI** | `disease:"…"` | `tissue:"…"` | `omics_type` / `technology_type` | `TAXONOMY:"…"` | ✓ | `omicsdi_vocab` |
| **ProteomeXchange** | same as OmicsDI | same | `omics_type:"Proteomics"` + tech | `TAXONOMY:"…"` | ✓ | `proteomexchange_vocab` |
| **VDJServer** | diagnosis label `contains` | tissue label `contains` | locus `=` or title `contains` | `subject.species.id` | ✓ | `vdjserver_vocab` |

Shared search strategies (all repos): `strict` → `broad_1` → `broad_2` → `broad_3` → optional `text_broad` → `adhoc`. See `domain/facet_search_strategies.py`.

---

## GEO

| | disease | tissue | assay | organism |
|---|---------|--------|-------|----------|
| **API filterable** | ✓ (free-text) | ✓ (free-text) | ✓ (free-text) | ✗ |
| **Search param** | NCBI `term` (AND-joined grounded synonyms) | same | same | — |
| **Raw response** | `title`, `summary` | `samples[].title` | `gdstype`, `platformtitle`, `ptechtype` | `taxon`, `platformtaxa` |
| **Normalized fields** | `title`, `summary` | `title`, `summary`, `sample_titles` | `gdstype`, `platformtitle`, `ptechtype` | `taxon`, `platformtaxa`, `sample_titles` |
| **Evidence tier** | narrative | narrative | inferred (`GDS_TYPE_ASSAY_HINTS`) | structured |

**Notes:** No structured facet API. `gdstype` is the primary assay signal. Adapter: `tools/geo_dataset_search.py`.

---

## Expression Atlas

| | disease | tissue | assay | organism |
|---|---------|--------|-------|----------|
| **API filterable** | ✓ (free-text) | ✓ (free-text) | ✓ (free-text) | post-filter only |
| **Search param** | EBI Search `query` | same | same | `species` on fetch (not in facet query string) |
| **Raw response** | `description` | — | `experimenttype`, `assaytype`, `type` | `species` |
| **Normalized fields** | `title`, `summary` | `title`, `summary` | `gxa_experiment_type`, `gxa_observed_assay`, `gdstype` | `taxon` |
| **Evidence tier** | narrative | narrative | inferred (`gxa_assay.py`) | structured |

**Notes:** Assay inferred from experiment type. Adapter: `tools/expression_atlas.py`.

---

## ImmPort

| | disease | tissue | assay | organism |
|---|---------|--------|-------|----------|
| **API filterable** | ✓ | ✓ | ✓ | ✓ |
| **Search param** | `conditionOrDisease` | `biosampleType` | `assayMethod` | `species` |
| **Raw response** | `condition_or_disease` | `biosample_type` | `assay_method` | `species` |
| **Normalized fields** | `condition_or_disease` | `biosample_type` | `assay_method`, `gdstype` | `taxon` |
| **Evidence tier** | structured_cv | structured_cv | structured_cv | structured |

**Notes:** Reference CV-backed source. `text_broad` uses free-text `term` without facet params. Vocab: lookup tables `lkDisease`, `lkSampleType`, `lkExpMeasurementTech`. Adapter: `tools/immport_dataset_search.py`.

---

## Vivli

| | disease | tissue | assay | organism |
|---|---------|--------|-------|----------|
| **API filterable** | ✓ | ✓ | ✓ (weak) | post-filter |
| **Search param** | `healthCondition.name:"…"` | `sample.sampleType.name:"…"` OR quoted fallback | quoted free-text | `_species_matches` (defaults human) |
| **Raw response** | `healthCondition[].name` | `sample.sampleType.name` | `measurementTechnique[].name` | `species` |
| **Normalized fields** | `condition_or_disease` | `biosample_type` | `assay_method`, `gdstype` | `taxon` |
| **Evidence tier** | structured | structured | mixed | structured |

**Notes:** Clinical trial catalog (NCT accessions). Queries scoped to Vivli / accessclinicaldata@NIAID. Assay search is the weakest facet. Adapter: `tools/vivli_dataset_search.py`.

---

## OmicsDI

| | disease | tissue | assay | organism |
|---|---------|--------|-------|----------|
| **API filterable** | ✓ | ✓ | ✓ | ✓ |
| **Search param** | `disease:"…"` | `tissue:"…"` | `omics_type:"…"` or `technology_type:"…"` | `TAXONOMY:"{ncbi_id}"` |
| **Raw response** | `additional.disease[]` (detail) | `additional.tissue[]` (detail) | `omicsType[]`, `technology_type[]` | `organisms[].name` |
| **Normalized fields** | `condition_or_disease` | `biosample_type` | `omicsdi_omics_type`, `omicsdi_observed_assay`, `assay_method` | `taxon` |
| **Evidence tier** | structured_cv | structured_cv | inferred | structured |

**Notes:** Detail fetch enriches disease/tissue when search hits lack structured fields. `omics_type` is primary assay facet at search time. Adapter: `tools/omicsdi_dataset_search.py`.

---

## ProteomeXchange

Same facet shape as OmicsDI with additional constraints:

- Search scoped to PX member repositories (`repository:pride OR repository:MassIVE …`)
- Always includes `omics_type:"Proteomics"` unless a more specific assay clause applies
- Proteomics-only pipeline; metabolomics/RNA-seq queries skip this repo via `filter_repositories_for_interpreted_query`

Vocab: `proteomexchange_vocab.py` (wraps OmicsDI mapping). Adapter: `tools/proteomexchange_dataset_search.py`.

---

## VDJServer

| | disease | tissue | assay | organism |
|---|---------|--------|-------|----------|
| **API filterable** | ✓ | ✓ | ✓ | ✓ |
| **Search param** | `subject.diagnosis.disease_diagnosis.label` contains | `sample.tissue.label` contains | `pcr_target_locus` = or `study.study_title` contains | `subject.species.id` = |
| **Raw response** | `subject.diagnosis[].disease_diagnosis.label` | `sample[].tissue.label` | `pcr_target_locus`, `sequencing_platform` | `subject.species.id` |
| **Normalized fields** | `condition_or_disease` | `biosample_type` | `assay_method`, `airr_observed_assay`, `gdstype` | `taxon` |
| **Evidence tier** | structured | structured | inferred (`airr_assay.py`) | structured |

**Notes:** Immune-repertoire-only. BCR → `IGH`, TCR → `TRB`. `text_broad` uses `study.study_title` contains. Adapter: `tools/vdjserver_dataset_search.py`.

---

## When adding a new repository

This step is **required** for every dataset pipeline source. Follow the full recipe in [adding-a-source.md](adding-a-source.md) — section **Facet capability registry (required for dataset pipeline sources)**.

1. Implement search + normalize in `tools/<repo>_dataset_search.py`.
2. Register in `dataset_repository_registry.py`.
3. Add **`RepositoryFacetCapability`** entry in `repository_facet_capabilities.py` (this doc’s code source of truth).
4. **Update this document** — add a per-repo section and a row in the summary comparison table above.
5. If CV-backed: add `repository_vocab/<repo>_vocab.py` and wire normalized fields per the canonical schema table.
6. Add tests in `test_<repo>_evidence_extraction.py`; run `pytest tests/test_repository_facet_capabilities.py`.

---

## Related docs

| Doc | Relevance |
|-----|-----------|
| [adding-a-source.md](adding-a-source.md) | Integration recipe |
| [dataset-ranking.md](dataset-ranking.md) | How evidence tiers affect scoring |
| [evaluation/nde_benchmark.md](evaluation/nde_benchmark.md) | NDE field name comparison |
| [SmartAPI registry](https://smart-api.info/) | External aggregated API metadata (entity-centric APIs; dataset repos not fully covered) |
| [roadmap/entity-span-detection.md](roadmap/entity-span-detection.md) | Shared query interpretation (pre-search) |
