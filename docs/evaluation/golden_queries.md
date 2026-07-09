# Golden-query dataset discovery evaluation

Developer-facing harness for regression-checking the dataset discovery pipeline against a fixed set of natural-language queries. This is **not** exposed in the UI or API.

## What it measures

For each query, the harness runs the full pipeline (interpret → ground → search → normalize → annotate → rank → context export) against **enabled** dataset sources and records:

| Field | Description |
|-------|-------------|
| `interpreted_facets` | Disease, tissue, assay, and organism slots from regex/phrase resolution |
| `grounded_concepts` | Ontology mappings (CURIE, label, match type, provider, confidence) |
| `enabled_sources` | Repositories searched (`GEO`, `Expression Atlas`) based on `SCIAGENT_EXCLUDED_SOURCES` |
| `per_source_hit_counts` | Repository `total_found` before merge/deduplication |
| `top_10` | Top 10 integrated ranked results (see scoring fields below) |
| `top_10_source_distribution` | Count of top-10 hits per repository |
| `match_statuses` | Distribution of match statuses in the top 10 (`full`, `partial`, etc.) |
| `warnings_count` / `conflicts_count` | Metadata warnings and evidence conflicts in the top 10 |
| `context_export_ok` | Whether `export_dataset_search_agent_context` succeeds |
| `assay_ranking_violations` | Human-readable list when assay-mismatch partials rank above RNA-seq-supported partials |
| `assay_ranking_ok` | `true` when `assay_ranking_violations` is empty (RNA-seq queries only) |

Each `top_10` entry includes:

| Subfield | Description |
|----------|-------------|
| `display_rank_score` | **Sort key** — what ordering uses |
| `evidence_score` | Facet coverage + quality + assay adjustments (relevance strength) |
| `rank_tier` | Numeric tier used in `display_rank_score = rank_tier × 10 + evidence_score` |
| `partial_assay_subtype` | For RNA-seq partials: `partial_assay_supported`, `partial_assay_unknown`, or `partial_assay_mismatch` |
| `match_status` | `full`, `full_with_warnings`, `partial`, `ambiguous_or_mixed`, or `model` |
| `assay_mismatch` | `true` when requested assay ≠ observed assay (e.g. proteomics/microarray for an RNA-seq query) |

## Integrated ranking (GEO + Expression Atlas)

Results are sorted by **`display_rank_score`**, not `evidence_score` alone:

```
display_rank_score = rank_tier × 10 + evidence_score
```

For **RNA-seq queries**, partial matches use assay-aware sub-tiers so proteomics/microarray records stay visible but rank below RNA-seq-supported partials:

| `rank_tier` | Meaning |
|-------------|---------|
| 4.0 | `full` |
| 3.0 | `full_with_warnings` |
| 2.8 | `partial` + assay supported (`partial_assay_supported`) |
| 2.5 | `partial` + assay unknown (`partial_assay_unknown`) |
| 2.2 | `partial` + assay mismatch (`partial_assay_mismatch`) — e.g. E-PROT, microarray |
| 1.0 | `ambiguous_or_mixed` or `model` |

Assay mismatch records are **not removed**; they appear as related partial results with lower rank tier.

Full scoring model: [dataset-ranking.md](../dataset-ranking.md) (base score, evidence_score, rank tiers, assay sub-tiers, match status).

### Golden-query pass/fail checks

For RNA-seq golden queries, the harness fails if any **assay-mismatch partial** (tier 2.2) ranks above an **RNA-seq-supported partial** (tier 2.8) in the top 10. Examples that must pass:

- UC query: E-GEOD-83687 (RNA-seq partial) above E-PROT-40 (proteomics mismatch)
- Alzheimer’s query: GSE331058 (RNA-seq partial) above E-PROT-39 (proteomics mismatch)

Implementation: `domain/assay_ranking.py` → `validate_rna_seq_assay_ranking()`.

Score breakdown details (base score, quality adjustment, assay rank adjustment, rank tier note) appear in context export and the UI score breakdown panel.

## Initial golden queries

1. Find public RNA-seq datasets for ulcerative colitis colon tissue.
2. Find public RNA-seq datasets for UC colon tissue.
3. Find public RNA-seq datasets for Crohn's disease ileum tissue.
4. Find public RNA-seq datasets for Alzheimer's disease brain tissue.

These cover spelled-out disease names, abbreviations (UC), alternate tissues, and a neurodegenerative query.

## Running the harness

From the repository root (loads `.env` and uses the project virtualenv via `uv`):

```bash
./scripts/run_golden_queries.sh
```

Or from `server/`:

```bash
cd server
uv run python scripts/run_golden_queries.py
```

Do **not** use bare `python scripts/run_golden_queries.py` — system Python does not have project dependencies such as `python-dotenv`.

Human-readable summary (default):

```bash
./scripts/run_golden_queries.sh
```

Full JSON report:

```bash
./scripts/run_golden_queries.sh --json
```

Single query:

```bash
./scripts/run_golden_queries.sh --query "Find public RNA-seq datasets for UC colon tissue."
```

Override retrieval limit (default is 10 for the harness, independent of `GEO_MAX_RESULTS`):

```bash
./scripts/run_golden_queries.sh --max-results 25
```

Increase pause between queries if you still see NCBI 429 errors:

```bash
./scripts/run_golden_queries.sh --pause-between-queries 5
```

Exit code is `1` when any query fails:

- No enabled sources
- Context export error (`context_export_ok` is false)
- Assay ranking violation (`assay_ranking_ok` is false on RNA-seq queries)

## NCBI rate limits

The harness runs four queries back-to-back, each hitting GEO with multiple search strategies. NCBI may return **HTTP 429** if:

- `NCBI_EMAIL` is not set (strongly recommended; `PUBMED_EMAIL` is accepted as a fallback)
- `GEO_MAX_RESULTS` is high and you override `--max-results` accordingly
- You have recently run other GEO/PubMed queries against the same IP

Mitigations:

1. Set `NCBI_EMAIL` in `.env` (required by NCBI policy). `PUBMED_EMAIL` is still accepted as a fallback.
2. Optionally set `NCBI_API_KEY` for a higher rate limit ([NCBI account settings](https://www.ncbi.nlm.nih.gov/account/settings/)).
3. Use the harness default `--max-results 10` (does not inherit `GEO_MAX_RESULTS=50`).
4. Increase `--pause-between-queries` (default 2 seconds).

GEO requests retry automatically on 429 with exponential backoff.

### Production web app vs this harness

| | Golden-query harness | Deployed web app |
|---|---------------------|------------------|
| **NCBI config** | `.env` or shell env (`NCBI_EMAIL`, `NCBI_API_KEY`) | Platform env vars on Render/Docker (same names) |
| **Rate limiting** | `--pause-between-queries` between the 4 batch queries | Per-request throttling in `geo_dataset_search` + 429 retry |
| **Pause needed?** | Sometimes, when running all golden queries locally | No — one user query at a time |

Increasing `--pause-between-queries` only affects `run_golden_queries.py` / `run_golden_queries.sh`. It is not an app setting and is not read by the FastAPI server. For production, set `NCBI_API_KEY` on the backend host instead.

## Pytest integration

Unit tests mock repository search and run in CI without network access:

```bash
cd server
uv run pytest tests/test_golden_queries.py tests/test_assay_ranking.py -k "not live"
```

Relevant test files:

| Test file | What it covers |
|-----------|----------------|
| `tests/test_golden_queries.py` | Harness shape, monotonic `display_rank_score`, `assay_ranking_ok` |
| `tests/test_assay_ranking.py` | Assay mismatch detection, partial sub-tiers, E-PROT vs RNA-seq ordering |
| `tests/test_ranking_facet_quality.py` | Facet quality adjustments and rank tier ordering |

Live evaluation against real GEO / Expression Atlas APIs (requires network and enabled sources):

```bash
SCIAGENT_RUN_GOLDEN_QUERIES=1 pytest tests/test_golden_queries.py -k live
```

## Source enablement

The harness respects the same blocklist as the server:

- `geo_dataset_search` → **GEO**
- `expression_atlas` → **Expression Atlas**

If both are excluded, the harness reports an error and skips repository calls.

## Implementation

| Path | Role |
|------|------|
| `server/evaluation/golden_queries.py` | Core harness: `evaluate_golden_query`, `evaluate_all_golden_queries`, `GOLDEN_QUERIES` |
| `server/domain/assay_ranking.py` | Assay mismatch detection, partial sub-tiers, `validate_rna_seq_assay_ranking` |
| `server/domain/ranking.py` | Integrated ranking: `rank_tier`, `evidence_score`, `display_rank_score` |
| `docs/dataset-ranking.md` | Scoring and ranking reference |
| `server/scripts/run_golden_queries.py` | CLI entry point |
| `scripts/run_golden_queries.sh` | Loads `.env`, runs harness via `uv` |
| `server/tests/test_golden_queries.py` | Structural tests (mocked) + optional live smoke test |
| `server/tests/test_assay_ranking.py` | Assay-aware ranking regression tests |

Per-source hit counts are captured by searching each enabled repository individually, then merging results with the same deduplication logic used in production (`merge_repository_search_results`).

## Adding queries

Append new strings to `GOLDEN_QUERIES` in `server/evaluation/golden_queries.py` and document the intent in this file. Prefer queries that exercise facet interpretation, abbreviation resolution, grounding, and multi-source ranking—not one-off accession lookups.

## Related

ImmPort immunology golden queries (asthma PBMC flow cytometry, influenza vaccine, peanut allergy, tuberculosis T cell) are documented separately in [immport_golden_queries.md](immport_golden_queries.md).

OmicsDI multi-omics golden queries (UC colon RNA-seq, asthma lung proteomics, Alzheimer brain proteomics, breast cancer proteomics, IBD serum metabolomics) are documented separately in [omicsdi_golden_queries.md](omicsdi_golden_queries.md).

ProteomeXchange proteomics golden queries are documented in [proteomexchange_golden_queries.md](proteomexchange_golden_queries.md).

Vivli clinical trial golden queries are documented in [vivli_golden_queries.md](vivli_golden_queries.md).
