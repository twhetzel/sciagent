# Workplan: Dictionary-backed entity span detection

**Status:** Planned  
**Last updated:** 2026-07-09

Orientation for pre-search query interpretation: detect disease, tissue, assay, and organism entities from query text using a local ontology dictionary, so SciAgent does not require a manual seed for every ontology-covered term. For retrieval broadening after grounding, see [ontology-hierarchy-expansion.md](ontology-hierarchy-expansion.md).

---

## Problem

Dataset discovery already interprets queries **before** repository search (`interpret_query_pipeline` → `ground_query` → search). Today, entity detection is mostly:

1. Hand-maintained regex (`server/domain/query_interpretation.py`, `server/domain/tissue_anatomy.py`)
2. Curated seeds (`SEED_CONCEPTS` in `server/domain/ontology_providers/curated.py`)
3. Contiguous n-gram scan with a **6-attempt** OLS/BioPortal budget (`server/domain/facet_phrase_resolution.py`)

When detection fails, search degrades to partial facet strategies or **`adhoc`** free-text. The operational fix has been “add another seed,” which does not scale as repositories and golden queries grow.

Dynamic grounding already works for some terms without seeds (e.g. **peanut allergy**, **tuberculosis**, **Crohn's disease ileum**). The gap is **reliable span detection**, not the downstream grounding or search stack.

Current bottlenecks:

| Limitation | Effect |
|------------|--------|
| Small regex lists | Only a dozen or so diseases/assays recognized instantly |
| Contiguous n-grams only | “ileum biopsies from Crohn's patients” may never form a groundable phrase |
| `MAX_DYNAMIC_GROUNDING_ATTEMPTS = 6` | Long/noisy queries exhaust the OLS budget before the right phrase is tried |
| Tissue single-words need curated/anatomy | Unlisted tissue words won't resolve unless in `ANATOMY_TERMS` |
| One winner per slot | First grounded tissue wins; others in the query are ignored |
| LLM fallback is narrow | Runs only when disease/tissue/assay are all still missing |

---

## Goals (MVP)

- Detect entity **spans** in submitted query text using a **local ontology dictionary** (labels + exact/narrow synonyms from facet ontologies).
- Assign each span to a facet slot (`disease`, `tissue`, `assay`, `organism`) using existing ontology policy (`server/domain/ontology_providers/obo_foundry_policy.py`).
- Collapse spans into today's `InterpretedQuery` (one value per slot) so **search, grounding, evidence, and ranking stay unchanged**.
- Reduce seed additions to **disambiguation overrides** and repo-specific aliases — not the primary term catalog.
- Add regression tests for terms **not** in `SEED_CONCEPTS` or `ANATOMY_TERMS`.

---

## Non-goals (this phase)

- As-you-type autocomplete UI or `/api/interpret` streaming endpoint
- Full-sentence semantic parsing / multi-clause decomposition
- NER model deployment (SciSpacy, GLiNER, etc.) — defer unless dictionary coverage is insufficient
- Replacing `repository_vocab/*.py` mappings (still needed for API filters)
- Removing all seeds (abbreviation safety and ambiguous terms still need curated overrides)
- Entity detection in dataset **metadata** (titles/summaries) — separate follow-on

---

## Architecture

### Pipeline (after)

```text
User query (submit)
  │
  ├─ 1. Regex pass                    [existing: query_interpretation.py]
  ├─ 2. Abbreviation pass             [existing: facet_abbreviation_resolution.py]
  ├─ 3. Dictionary span detection     [NEW: entity_span_detection.py]
  ├─ 4. Phrase n-gram pass            [existing: facet_phrase_resolution.py — thinned role]
  ├─ 5. LLM interpret fallback        [existing: llm_query_interpretation.py — broader triggers]
  │
  ├─ → InterpretedQuery
  ├─ → OntologyGrounder.ground_interpreted_query   [unchanged]
  └─ → Repository search                           [unchanged]
```

Dictionary detection runs **before** n-gram brute force so most terms never consume the dynamic OLS budget.

### New data model

Add to `server/domain/dataset_search.py` (or a sibling module):

```python
class EntityMention(BaseModel):
    """One detected biomedical entity span in query text."""

    start: int
    end: int
    surface_form: str          # text as typed
    slot: str                  # disease | tissue | assay | organism
    normalized_form: str       # normalized for lookup
    detection_source: str      # dictionary | regex | abbrev | ngram | llm
    dictionary_curie: str | None = None   # pre-linked CURIE from index (optional)
    confidence: float = 1.0
```

`InterpretedQuery` stays as-is (backward compatible). Optionally attach mentions to trace/debug payload later; not required for MVP search.

### New module: `server/domain/entity_span_detection.py`

| Function | Purpose |
|----------|---------|
| `detect_entity_spans(query, interpreted_partial)` | Longest-match scan; return non-overlapping mentions |
| `mentions_to_interpreted_query(mentions, existing)` | Merge into `InterpretedQuery`, respecting slot fill order |
| `resolve_span_overlaps(mentions)` | Longest span wins; tie-break by slot priority |

Slot assignment rules (reuse existing policy):

- CURIE prefix → slot via `SLOT_CURIE_PREFIXES` / `OntologyBinding` registry
- Context rules from `facet_phrase_resolution.py` (`is_breast_tissue_query`, disease vs tissue word guards)
- Acronym rules from `synonym_classification.py` (`BLOCKED_SHORT_ACRONYMS`, `has_acronym_context`)

Wire into `interpret_dataset_query`:

```python
def interpret_dataset_query(query: str) -> InterpretedQuery:
    interpreted = _regex_pass(query)
    interpreted = resolve_abbreviated_facets(query, interpreted)
    interpreted = resolve_dictionary_facets(query, interpreted)   # NEW
    interpreted = resolve_phrase_facets(query, interpreted)
    return interpreted
```

### New module: `server/domain/ontology_dictionary.py`

In-memory index built offline:

```python
@dataclass(frozen=True)
class DictionaryEntry:
    normalized_term: str
    label: str
    curie: str
    ontology: str
    slot: str
    match_type: str   # label | exact_synonym
```

Lookup API:

```python
def find_spans(normalized_query: str) -> list[DictionaryEntryMatch]:
    """Return all longest non-overlapping dictionary matches with char offsets."""
```

Implementation: **Aho-Corasick** or sorted-token longest-match over normalized query text. Reuse `_normalize_text` from `synonym_classification.py` and `normalize_query_for_phrases` from `facet_query_normalization.py`.

### Index build: `server/scripts/build_ontology_dictionary.py`

**Sources (offline, version-pinned):**

| Slot | Ontologies | Source |
|------|------------|--------|
| disease | MONDO, DOID, EFO (+ HP fallback labels) | OBO JSON / OLS dump |
| tissue | UBERON, CL | OBO JSON |
| assay | OBI, GO (investigation terms), NCIT where needed | OBO JSON |
| organism | NCBITaxon (human + common model organisms for MVP) | subset |

**Include in index:**

- Preferred labels
- Exact / narrow synonyms (`hasExactSynonym`, `hasNarrowSynonym`)
- Curated seeds (merged as highest-priority entries)

**Exclude from index:**

- OLS broad/related synonyms (same tier rule as retrieval — evidence only today)
- Very short terms (< 3 chars) except known safe abbreviations handled by abbreviation pass
- Generic phrases already in `GENERIC_PHRASES`

**Output:** `server/domain/data/ontology_dictionary.json` (or `.msgpack` if large). Commit a built artifact for CI, or build in CI from pinned OBO releases.

### Changes to existing modules

| File | Change |
|------|--------|
| `query_interpretation.py` | Insert dictionary pass after abbrev, before phrase resolution |
| `facet_phrase_resolution.py` | Skip n-grams already covered by dictionary; reduce OLS reliance |
| `facet_abbreviation_resolution.py` | Replace global attempt cap with per-slot budget |
| `llm_query_interpretation.py` | Broaden `should_run_llm_interpret`: run when **any** of disease/tissue/assay missing |
| `ontology_providers/curated.py` | Document seeds as overrides; merge into dictionary at build time |
| `docs/adding-a-source.md` | Update “add seed” step → “add vocab mapping; seed only if ambiguous” |
| `README.md` | Update interpretation section |

**No changes** to: `OntologyGrounder`, `facet_search_strategies.py`, repository adapters, ranking, evidence extraction.

### Optional: grounder short-circuit (Phase 2b)

When dictionary provides `(slot, curie, label)`:

- Add a `DictionaryProvider` as first provider in `OntologyGrounder`
- Confidence: `curated_exact`-equivalent for dictionary label hits
- Reduces OLS calls at ground time

---

## Implementation phases

### Phase 0 — Baseline & fixtures (~4–6 hours)

- [ ] Audit golden-query failures where interpretation missed an entity and a seed was added afterward
- [ ] Create `server/tests/fixtures/entity_detection_cases.json` with ~20 cases (non-seeded terms, inverted phrasing, hyphenated disease, parenthetical abbrevs, peanut allergy vs allergy, T cell + tuberculosis)
- [ ] Document current pass/fail per case

**Exit criteria:** Reproducible fixture list; baseline documented.

### Phase 1 — Quick wins in existing pipeline (~2–3 days)

Ship independently before the dictionary lands:

- [ ] Replace global `MAX_DYNAMIC_GROUNDING_ATTEMPTS = 6` with per-slot budget (e.g. `MAX_DYNAMIC_ATTEMPTS_PER_SLOT = 4`)
- [ ] Allow dynamic single-word tissue grounding when OLS returns primary-tier UBERON/CL match ≥ 0.85
- [ ] Broaden LLM fallback: `should_run_llm_interpret` true when **any** of disease/tissue/assay empty
- [ ] Skip redundant n-grams when regex/abbrev already filled a slot
- [ ] Integration tests for 5+ non-seeded terms (lupus, peanut allergy, etc.) — live or VCR-recorded OLS

**Exit criteria:** Golden queries still pass; new non-seeded integration tests pass; fewer adhoc fallbacks on fixture list.

### Phase 2 — Ontology dictionary + span detector (~1–2 weeks)

- [ ] `build_ontology_dictionary.py` — parse OBO releases, assign slots, merge curated seeds, emit artifact
- [ ] `ontology_dictionary.py` — load artifact, longest-match span finder
- [ ] `entity_span_detection.py` — overlap resolution, slot-context filters, `mentions_to_interpreted_query`
- [ ] Wire `resolve_dictionary_facets` into `interpret_dataset_query`
- [ ] Unit + fixture tests; all existing `test_facet_*.py` pass

**Exit criteria:** Fixture list ≥ 90% pass without new seeds; no regression on UC/Berkeley acronym safety.

### Phase 2b — Grounder short-circuit (~2–3 days, optional)

- [ ] `DictionaryProvider` in `OntologyGrounder` for pre-linked CURIEs
- [ ] Assert reduced OLS calls in tests

### Phase 3 — LLM structured fallback (~3–5 days)

- [ ] Run LLM when dictionary + n-gram left any core slot empty and unmatched content tokens remain
- [ ] Keep `_validate_llm_slot` — no ungrounded LLM output reaches search

**Exit criteria:** Fixture list ≥ 95% pass; residual misses documented.

### Phase 4 — Documentation & seed policy (~1 day)

- [ ] Update `docs/adding-a-source.md` — vocab mapping primary; seed only if ambiguous
- [ ] Update README “Query interpretation” section
- [ ] Add `docs/evaluation/entity_detection_cases.md` listing fixture queries

---

## Test strategy

### Unit tests

| File | Coverage |
|------|----------|
| `test_ontology_dictionary.py` | Index load, longest-match, overlap, normalization |
| `test_entity_span_detection.py` | Span → slot, breast cancer vs breast tissue, blocked acronyms |
| `test_entity_detection_fixtures.py` | Parametrize over `entity_detection_cases.json` |

### Integration tests

- End-to-end: `interpret_dataset_query` → `ground_interpreted_query` → `build_facet_search_queries`
- Assert ≥ 4 strategies when disease + tissue + assay resolved
- Assert no adhoc-only query plan for fixture cases

### Regression

- Run all golden-query harnesses (GEO, ImmPort, OmicsDI, PX, Vivli, VDJServer)
- `pytest server/tests/test_facet_*.py server/tests/test_llm_query_interpretation.py`

### Negative tests (must not break)

- `UC` without clinical context → no disease
- `UC Berkeley` → no disease
- Generic “allergy” must lose to “peanut allergy” when both present

---

## Seed migration policy

After Phase 2, seeds fall into three tiers:

| Tier | Purpose | Example | Action |
|------|---------|---------|--------|
| **Override** | Disambiguation, repo aliases | `RNA-seq` assay normalization, `UC` synonyms | Keep in curated; merge into dictionary |
| **Accelerators** | Common terms already in MONDO/UBERON | asthma, colon | Optional; dictionary covers them |
| **Anatomy regex** | Pattern variants (`colonic`, `PBMCs`) | `tissue_anatomy.py` | Keep regex for detection; dictionary holds CURIE |

Do not delete seeds immediately — stop **requiring** new ones for ontology-covered terms.

---

## Acceptance criteria (MVP)

1. Dictionary span detection runs before phrase n-gram pass in `interpret_dataset_query`.
2. Fixture cases (≥ 20) pass at ≥ 90% without adding new seeds.
3. All existing facet and golden-query tests pass.
4. Queries that previously fell to adhoc-only (no facets) decrease on the fixture set.
5. Abbreviation safety tests (`UC` context) unchanged.
6. Optional env kill-switch: `SCIAGENT_DICTIONARY_DETECT=false` (falls back to current behavior).

---

## Success metrics

| Metric | Target |
|--------|--------|
| Fixture cases passing without seed | ≥ 90% (Phase 2), ≥ 95% (Phase 3) |
| Golden-query interpretation regressions | 0 |
| Queries falling to adhoc-only (no facets) | ↓ 50%+ on fixture set |
| Manual seed additions per new repository | ↓ to vocab-only for most CV terms |
| Interpret + ground latency (p95, submit time) | < 2s with dictionary; OLS only on cache miss |

---

## Risks

| Risk | Mitigation |
|------|------------|
| Dictionary false positives (generic words matching MONDO labels) | Min length, stopword filter, `GENERIC_PHRASES`, require primary-tier ontology |
| Index size / startup time | Slot-sharded indexes; lazy load; msgpack compression |
| Overlap ambiguity (breast, cancer) | Keep context rules; longest match + slot guards |
| Stale ontology versions | Pin OBO releases; rebuild script in CI; version stamp in artifact |
| Duplicate work with hierarchy expansion | Separate concerns: detection vs retrieval broadening |
| LLM cost/latency | Dictionary first; LLM only on residual misses |

---

## Open decisions

1. **Artifact in repo vs CI-built?** Committing a built dictionary simplifies local dev; CI rebuild verifies freshness.
2. **NCBITaxon scope:** human-only for MVP, or include mouse/rat/zebrafish?
3. **NCIT assay terms:** include in dictionary (immune repertoire already uses NCIT seeds) or stay OBI/GO-only?
4. **Trace payload:** expose `EntityMention[]` in dataset discovery trace for UI debugging in v1 or v2?

---

## Suggested file tree (new)

```text
server/
  domain/
    entity_span_detection.py      # NEW
    ontology_dictionary.py        # NEW
    data/
      ontology_dictionary.json    # NEW (built artifact)
  scripts/
    build_ontology_dictionary.py  # NEW
  tests/
    test_ontology_dictionary.py   # NEW
    test_entity_span_detection.py # NEW
    test_entity_detection_fixtures.py  # NEW
    fixtures/
      entity_detection_cases.json # NEW
docs/
  roadmap/
    entity-span-detection.md      # this document
  evaluation/
    entity_detection_cases.md     # NEW (Phase 4)
```

---

## Estimate

| Phase | Effort |
|-------|--------|
| Phase 0 (fixtures) | ~4–6 hours |
| Phase 1 (quick wins) | ~2–3 days |
| Phase 2 (dictionary + detector) | ~1–2 weeks |
| Phase 2b (grounder short-circuit) | ~2–3 days (optional) |
| Phase 3 (LLM fallback) | ~3–5 days |
| Phase 4 (docs) | ~1 day |

Phase 1 can ship independently and should reduce “add a seed” pressure immediately. Phase 2 is the structural fix.

---

## Related docs

| Doc | Relevance |
|-----|-----------|
| [ontology-hierarchy-expansion.md](ontology-hierarchy-expansion.md) | Retrieval broadening **after** grounding (complementary) |
| [adding-a-source.md](../adding-a-source.md) | Repository vocab + seed policy updates |
| [README.md](../../README.md) | Query interpretation caveats |
| [evaluation/golden_queries.md](../evaluation/golden_queries.md) | Regression harness |
| [dataset-ranking.md](../dataset-ranking.md) | Unchanged by this workplan |
