# Integrated dataset ranking (GEO + Expression Atlas)

How SciAgent scores and orders merged dataset discovery results after search, normalization, and evidence annotation.

This applies to the production web app and the [golden-query evaluation harness](evaluation/golden_queries.md). Both use the same pipeline step: `rank_results()` in `server/agent/dataset_discovery.py`.

## Overview

Ranking runs **after** candidates are annotated with evidence snippets. A candidate only receives credit for facets that are **supported by returned metadata** — requested facets without evidence do not inflate the score.

Integrated results from GEO and Expression Atlas are merged and de-duplicated first, then ranked as one list.

## Two scores

| Score | Role |
|-------|------|
| **`evidence_score`** | Relevance strength from facet coverage and quality adjustments |
| **`display_rank_score`** | **Sort key** shown as `Rank` in the UI and used for ordering |

```
display_rank_score = rank_tier × 10 + evidence_score
```

`rank_tier` encodes match quality and (for RNA-seq queries) assay support. It is intentionally larger than typical `evidence_score` values (~0–1.5) so tier differences dominate ordering.

**Important:** A high `evidence_score` does not guarantee a high list position. For example, an organoid study may score well on facets but sit in `ambiguous_or_mixed` tier (1.0) and rank below a lower-scoring `partial` result (tier ≥ 2.2).

## Pipeline (per candidate)

1. **Base score** — slot weights for evidence-backed facets + coverage bonus
2. **Match status** — `full`, `partial`, `ambiguous_or_mixed`, etc. (label only at this step)
3. **Quality adjustment** — disease specificity, tissue evidence type
4. **Assay rank adjustment** — RNA-seq bonuses/penalties; mismatch flag
5. **Evidence score** — `max(0, base + quality + assay)`
6. **Rank tier** — status tier + partial assay sub-tiers (RNA-seq queries)
7. **Display rank score** — final ordering value stored on `candidate.score`

Implementation: `server/domain/ranking.py` → `rank_annotated_candidates()`.

## Base score

Slot weights (`server/domain/ranking.py`):

| Slot | Weight |
|------|--------|
| disease | 0.30 |
| tissue | 0.25 |
| assay | 0.25 |
| organism | 0.10 |
| evidence_coverage | 0.10 (fraction of requested slots with evidence) |

```
base_score = Σ(slot weights for matched slots) + 0.10 × (covered_slots / requested_slots)
```

Maximum base score when all four facets match: **1.10**.

## Match status

Assigned in `server/domain/score_breakdown.py` → `determine_match_status()`. Status affects **`rank_tier`**, not the base score directly.

| Status | When |
|--------|------|
| `full` | All requested facets have evidence; no disqualifying warnings |
| `full_with_warnings` | All facets covered but metadata warnings, conflicts, or narrative-only organism |
| `partial` | One or more requested facets lack evidence |
| `ambiguous_or_mixed` | Animal model, mixed/multi-assay metadata, or organoid/ambiguous tissue |
| `model` | Mouse model of human disease (set during annotation) |

## Quality adjustment

Applied in `server/domain/facet_match_quality.py`. Bounded tweaks to `evidence_score` — does not change `match_status`.

**Disease** — prefer exact requested disease over related IBD-family terms (e.g. Crohn’s vs ulcerative colitis): roughly **+0.08** exact, **−0.12** related-only.

**Tissue** — prefer direct tissue over derived/ambiguous:

| Tissue evidence type | Adjustment |
|---------------------|------------|
| direct | +0.06 |
| ambiguous | −0.06 |
| derived_model (organoid) | −0.12 |
| absent | −0.06 |

## Assay rank adjustment (RNA-seq queries)

Applied in `server/domain/assay_ranking.py` when the requested assay is RNA-seq.

**Assay mismatch** (`assay_mismatch=true`) when observed assay is proteomics, microarray, LC-MS/MS, mixed/multi-assay, or accession is `E-PROT-*`. Mismatch records stay in results as related partials.

| Observed assay | Typical penalty |
|----------------|-----------------|
| proteomics | −0.32 (+ −0.20 extra if partial) |
| microarray | −0.26 (+ −0.20 extra if partial) |
| other non-RNA-seq | −0.18 to −0.20 |

**RNA-seq supported:** +0.08 with structured assay evidence, +0.05 when observed RNA-seq without full assay slot credit.

## Rank tier

Computed in `compute_rank_tier()` (`server/domain/assay_ranking.py`).

### All queries

| `rank_tier` | Match status |
|-------------|--------------|
| 4.0 | `full` |
| 3.0 | `full_with_warnings` |
| 1.0 | `ambiguous_or_mixed`, `model` |

### RNA-seq queries — partial sub-tiers

When `match_status=partial` and the query requests RNA-seq, tier depends on assay support:

| `rank_tier` | `partial_assay_subtype` | Meaning |
|-------------|-------------------------|---------|
| 2.8 | `partial_assay_supported` | Observed RNA-seq or assay slot matched in metadata |
| 2.5 | `partial_assay_unknown` | Partial match; assay not confirmed or unknown |
| 2.2 | `partial_assay_mismatch` | Proteomics, microarray, or other non-RNA-seq observed |

Non–RNA-seq queries use **`rank_tier=2.0`** for all partial results (no assay sub-tiers).

### Why tier beats evidence within partials

Example (UC RNA-seq query):

- E-PROT-40 (proteomics mismatch): tier **2.2**, evidence ~0.35 → display **~22.35**
- E-GEOD-83687 (RNA-seq supported partial): tier **2.8**, evidence ~0.32 → display **~28.32**

The 6-point tier gap ensures RNA-seq-supported partials rank above proteomics/microarray partials even when the latter have stronger disease/tissue evidence.

## Score breakdown (debug)

Each ranked candidate may include `score_breakdown` with:

| Field | Description |
|-------|-------------|
| `base_score` | Slot coverage score |
| `quality_adjustment` | Disease + tissue adjustments |
| `assay_rank_adjustment` | RNA-seq assay bonus/penalty |
| `evidence_score` | Sum of the above (floored at 0) |
| `rank_tier` | Tier used for ordering |
| `partial_assay_subtype` | Partial assay sub-tier (RNA-seq only) |
| `display_rank_score` | Final sort key |
| `match_tier_note` | Human-readable tier explanation |
| `assay_mismatch` / `assay_mismatch_note` | Assay mismatch flag and reason |
| Per-slot breakdowns | disease, tissue, assay, organism presence and matched terms |

Visible in:

- UI: **Score breakdown (debug)** panel on each dataset card
- Context export: markdown/JSON agent context (`server/domain/dataset_context_export.py`)

## Golden-query checks

The evaluation harness asserts:

1. Top 10 results are monotonically sorted by `display_rank_score`
2. For RNA-seq golden queries, no **assay-mismatch partial** ranks above an **RNA-seq-supported partial** in the top 10

See [golden_queries.md](evaluation/golden_queries.md) for running the harness.

## Source files

| Module | Responsibility |
|--------|----------------|
| `server/domain/ranking.py` | Orchestration, slot weights, `rank_annotated_candidates` |
| `server/domain/score_breakdown.py` | Match status, per-slot evidence audit |
| `server/domain/facet_match_quality.py` | Disease/tissue quality adjustments, `compute_display_rank_score` |
| `server/domain/assay_ranking.py` | Assay mismatch, partial sub-tiers, validation |
| `server/domain/dataset_annotation.py` | Evidence annotation (input to ranking) |

## Tests

```bash
cd server
uv run pytest tests/test_assay_ranking.py tests/test_ranking_facet_quality.py tests/test_score_breakdown.py -q
```
