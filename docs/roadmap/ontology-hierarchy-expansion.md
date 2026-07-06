# Workplan: Ontology hierarchy expansion

**Status:** Planned (implement after next source integrations)  
**Last updated:** 2026-07-05

Orientation for the shared retrieval enhancement: expand grounded disease concepts using OLS hierarchy API calls. For NDE comparison metrics and paper framing, see [nde_benchmark.md](../evaluation/nde_benchmark.md).

---

## Problem

SciAgent search uses the **grounded preferred label** plus a small set of retrieval-safe synonyms. OLS **broad/related** synonyms support evidence matching but **not** repository retrieval (see README “Synonym tiers”).

Queries like `asthma` can miss narrower curated terms in NDE-backed metadata (e.g. **Mild Asthma** as a separate health-condition bucket). Vivli/NDE API checks:

| Query | Approx. Vivli hits |
|-------|-------------------|
| `healthCondition.name:"asthma"` | 348 |
| `healthCondition.name:"Mild Asthma"` | 11 (not included in 348) |
| `healthCondition` MONDO `0004979` | 348 |

Hierarchy-aware expansion improves recall without replacing strict strategies or exact-match ranking.

---

## Goals (MVP)

- After grounding a **disease** facet to a CURIE, fetch **immediate children** from OLS4.
- Add search strategy **`hierarchy_broad`** (after `broad_3`, before `text_broad` / `adhoc`).
- Expand repository queries with OR clauses over child labels (and CURIE/ID where metadata supports it).
- Keep **`primary_total_found`** from the strict strategy; hierarchy counts appear in strategy trace only.
- Cache OLS hierarchy responses per CURIE.

---

## Non-goals (this phase)

- Parent / ancestor expansion
- Tissue or assay hierarchy (phase 2)
- UI facet panel matching NDE sidebar
- LLM-generated hierarchy (OLS only for MVP)

---

## Architecture

### New module

`server/domain/ontology_hierarchy.py`

```text
fetch_ols_children(curie, *, max_terms=10) -> list[HierarchyTerm]
expand_mapping_for_retrieval(mapping, *, direction="children") -> list[str]
```

- Input: grounded `ConceptMapping` (`curie`, `ontology`, `iri`)
- Output: `[preferred_label, child_label, ...]` deduped and capped
- Cache: in-process LRU keyed by `(ontology, curie, direction)`

OLS4 endpoints:

- `GET /api/ontologies/{ontology}/terms/{encoded_iri}/children`
- Fallback: `hierarchicalDescendants?size=N` when children is empty

### Strategy integration

Extend `server/domain/facet_search_strategies.py`:

```python
STRATEGY_PRIORITY = {
    "strict": 0,
    "broad_1": 1,
    "broad_2": 2,
    "broad_3": 3,
    "hierarchy_broad": 4,
    "text_broad": 5,
    "adhoc": 6,
}
```

`hierarchy_broad` runs only when a disease mapping exists and OLS returns at least one child.

### Repository wiring

| Repository | Disease query | MVP change |
|------------|---------------|------------|
| **Vivli** | `healthCondition.name:"…"` | OR expanded labels; optional MONDO ID clause |
| **ImmPort** | `conditionOrDisease` CV | Expanded labels via `immport_vocab` |
| **GEO** | free-text AND groups | OR disease terms in `build_geo_search_term` |
| **Expression Atlas** | EBI Search | OR disease terms in facet query |

Suggested shared helper: `server/domain/facet_query_expansion.py` — per-adapter clause builders from one expanded term list.

### Ranking

No ranking changes required for MVP. Existing related-disease penalties in [dataset-ranking.md](../dataset-ranking.md) should keep hierarchy-only hits below strict matches — verify with golden queries.

### Trace

Extend strategy summaries:

```json
{
  "strategy": "hierarchy_broad",
  "search_term": "asthma",
  "expanded_terms": ["Mild Asthma", "allergic asthma"],
  "total_found": 359,
  "retrieved": 10,
  "new_ids": 3
}
```

---

## Implementation phases

### Phase 0 — Prerequisites

- [ ] Finish planned source integrations (Vivli done; OmicsDI / VDJServer as scoped)
- [ ] Golden-query harness reports per-repository hit counts

### Phase 1 — Core module (~4–8 hours)

- [ ] `ontology_hierarchy.py` with OLS children fetch + cache
- [ ] Unit tests with mocked OLS JSON (asthma → MONDO:0004979)
- [ ] `expand_disease_terms(concept_mappings)` utility

### Phase 2 — Vivli + ImmPort (~4–8 hours)

- [ ] `hierarchy_broad` in Vivli and ImmPort query builders
- [ ] Mocked HTTP tests; assert OR clause includes child terms
- [ ] Integration test: asthma query hits records only reachable via child label

### Phase 3 — GEO + Expression Atlas (~4–6 hours)

- [ ] Extend GEO / GXA multi-strategy builders
- [ ] Golden queries pass; hierarchy strategy visible in trace

---

## Acceptance criteria (MVP)

1. `hierarchy_broad` runs when disease is grounded and OLS returns children.
2. Vivli asthma query can retrieve records matchable only via child terms.
3. Strict strategy and `primary_total_found` unchanged.
4. Existing pytest suites pass; new hierarchy + adapter tests added.
5. Optional env kill-switch: `SCIAGENT_HIERARCHY_BROAD=false`.

---

## Risks

| Risk | Mitigation |
|------|------------|
| OLS latency | Per-CURIE cache; cap at 10 children; timeout → skip strategy |
| Over-broad recall | Children only; ranking penalizes related-only |
| Label vs NDE curation mismatch | MONDO ID clauses on NDE-backed repos where supported |

---

## Estimate

Phases 1–3 (MVP): **~1–2 days** focused work.

---

## Related docs

| Doc | Relevance |
|-----|-----------|
| [nde_benchmark.md](../evaluation/nde_benchmark.md) | Evaluation after MVP ships |
| [adding-a-source.md](../adding-a-source.md) | Adapter patterns |
| [dataset-ranking.md](../dataset-ranking.md) | Related-disease penalties |
| [evaluation/golden_queries.md](../evaluation/golden_queries.md) | Regression harness |
