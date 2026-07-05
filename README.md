# SciAgent Studio

SciAgent Studio is a scientific multi-database search agent with transparent execution tracing. Ask a natural-language question; the agent plans which databases to query, executes tools server-side, and returns both a synthesized answer and a step-by-step execution trace.

## Architecture

```
Browser (React)
  ├── Tools sidebar  ← GET /api/tools
  ├── Chat panel     ← POST /api/query → { response, traces }
  └── Trace panel    ← renders traces[] as a timeline

FastAPI (sciagent_server)
  └── AgentOrchestrator.run(query) → (response, traces)
        └── ToolRegistry → external scientific APIs
```

The FastAPI layer is intentionally thin: it only calls `orchestrator.run(prompt)` and exposes the result. All routing logic lives in the ported SciAgent Studio agent module.

## How the orchestrator works (no LLM required)

Most of SciAgent Studio does **not** use an LLM. The orchestrator runs a plan → act → observe → synthesize loop, but planning, tool selection, and the final chat answer are **rule-based**—not LLM tool-calling.

```
User query
  → keyword heuristics + entity extraction (gene symbols, disease terms, …)
  → ToolRegistry → public scientific APIs
  → template formatters → response + execution trace
```

Optional LLM layers (summarization, ontology synonym expansion) sit on top of this pipeline and are skipped when API keys are not set.

### Standard agent path

| Step | What happens | LLM needed? |
|------|----------------|-------------|
| **Plan** | Match query keywords (`gene`, `variants`, `literature`, `structure`, …) and extract entities to choose tools | No |
| **Act** | Call selected tools against external APIs (MyGene, UniProt, PubMed, ClinVar, AlphaFold, …) | No |
| **Observe / synthesize** | Count successes and failures; decide whether to retry | No |
| **Normalize (tool results)** | Map free-text terms in tool outputs to ontology IDs via OLS → BioPortal → Claude | Only tiers 2–3 (optional) |
| **Respond** | Assemble the answer from structured tool JSON using string templates | No |

### Dataset discovery path

Queries that mention datasets (`RNA-seq`, `GEO`, `dataset`, …) take a separate seven-step pipeline (documented below): regex facet extraction → ontology grounding → GEO search → evidence-based ranking → structured response. Grounding uses OLS and curated aliases first; BioPortal and LLM disambiguation are optional fallbacks.

### Where LLM API keys matter

| Feature | Env var | Without key |
|---------|---------|-------------|
| `summarize` tool | `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | Other tools still run; summarize returns an error in the response |
| Ontology normalization tier 3 | `ANTHROPIC_API_KEY` | Tier 1 (OLS) still runs; unmatched terms stay unmatched |
| BioPortal lookup (tier 2) | `BIOPORTAL_API_KEY` | Skipped; OLS and curated fallback still run |
| Dataset grounding LLM step | `ANTHROPIC_API_KEY` | Skipped when OLS or curated aliases already match |

Queries like `BRCA1 gene`, `marfan syndrome variants`, or `Find RNA-seq datasets for ulcerative colitis colon tissue` work out of the box: the agent fetches real API data and formats it with code, not an LLM reasoning through the question.

## Tool inventory

| Tool | Data source | Auth |
|------|-------------|------|
| `pubmed` | NCBI E-utilities (PubMed) | `NCBI_EMAIL`, `PUBMED_TOOL` recommended; `PUBMED_EMAIL` fallback |
| `openalex` | OpenAlex REST API | Optional `OPENALEX_EMAIL` |
| `europepmc` | Europe PMC REST API | None |
| `expression_atlas` | EMBL-EBI Expression Atlas (EBI Search + GXA JSON API) | None; dataset-discovery pipeline when GEO is excluded or for routed dataset queries |
| `immport` | ImmPort Shared Data API (study metadata search) | None; integrated dataset-discovery pipeline with GEO and Expression Atlas |
| `mygene` | MyGene.info v3 | None |
| `uniprot` | UniProt REST | None |
| `clinvar` | NCBI E-utilities (ClinVar) | Same NCBI env vars as PubMed |
| `alphafold` | AlphaFold EBI API | None |
| `geo_dataset_search` | NCBI GEO (GDS) | Same NCBI env vars as PubMed |
| `summarize` | OpenAI / Anthropic | `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY` |
| *(post-processing)* | OLS / BioPortal / Claude | Optional `BIOPORTAL_API_KEY`, `ANTHROPIC_API_KEY` for ontology normalization and dataset `interpret_llm` fallback |

See [How the orchestrator works](#how-the-orchestrator-works-no-llm-required) for the full routing model. To add a new source, follow [docs/adding-a-source.md](docs/adding-a-source.md). On the standard agent path, `tools/ontology_normalizer.py` runs after tools finish and appears in the trace as **Normalize (tool results)**. Dataset discovery queries use a separate seven-step pipeline documented below.

## Example queries

SciAgent Studio routes queries based on keywords and simple entity extraction (gene symbols, disease terms). Use the **execution trace panel** in the UI to see which tools ran and what parameters were passed.

### Queries that work today

| Question | Tools typically invoked | What you should see |
|----------|-------------------------|---------------------|
| `BRCA1 gene` | MyGene, UniProt | Gene summary, Entrez/Ensembl IDs, protein accession |
| `Tell me about TP53` | MyGene, UniProt | Same as above for TP53 |
| `TP53 variants` | MyGene, UniProt, ClinVar | Gene/protein info plus ClinVar variant list |
| `marfan syndrome variants` | PubMed, OpenAlex, Europe PMC, ClinVar | Literature + ClinVar condition search (disease term extracted as `marfan`) |
| `breast cancer literature` | PubMed, OpenAlex, Europe PMC | Normalized article hits from three literature sources |
| `ulcerative colitis gene expression` | Expression Atlas | Ranked Expression Atlas experiments with accession, species, and type |
| `Find public RNA-seq datasets for ulcerative colitis colon tissue` | GEO + Expression Atlas dataset discovery (merged, de-duped when both enabled) | Ranked dataset panel with facets, evidence snippets, and per-repository strategy trace |
| `TP53 expression atlas` | MyGene, UniProt, Expression Atlas | Gene/protein metadata plus matching Atlas experiments |
| `search articles on cystic fibrosis` | PubMed, OpenAlex, Europe PMC | Literature results (disease keyword triggers literature tools) |
| `AlphaFold structure for EGFR` | AlphaFold, UniProt | Structure confidence, PDB URL, protein metadata |
| `Summarize BRCA1 gene` | MyGene, UniProt, summarize | Requires `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` for the summarize step |
| `CFTR pathogenic variants` | MyGene, UniProt, ClinVar | Gene/protein metadata plus pathogenic variant list |
| `APOE gene structure` | MyGene, UniProt, AlphaFold | Gene summary, protein record, and AlphaFold model |
| `Find research on Huntington disease` | PubMed, OpenAlex, Europe PMC | Literature search (use `find`/`research` + `disease`) |
| `What ClinVar variants are linked to Marfan syndrome?` | PubMed, OpenAlex, Europe PMC, ClinVar | Condition-based ClinVar search + literature |
| `SIGMAR1 protein sequence` | MyGene, UniProt | Less common gene symbol; good routing smoke test |
| `EGFR 3D structure` | MyGene, UniProt, AlphaFold | `3D` triggers AlphaFold alongside gene tools |
| `Summarize TP53 gene function` | MyGene, UniProt, summarize | Summarize step aggregates gene/protein text |

### Dataset discovery (GEO)

These queries use a dedicated trace path and **do not** call `ontology_normalizer.py`. Do not confuse **Normalize Records** (repository payload → `DatasetCandidate`) with **Normalize (tool results)** on the gene/literature/ClinVar path.

| Step | Responsibility |
|------|----------------|
| **Interpret Query** | Extract disease, tissue, assay, organism facets via regex patterns, abbreviation resolution, and phrase grounding; **organism is only set when the query names it** (e.g. human, Homo sapiens) — no implicit human default |
| **Ground Query** | Map requested facets to ontology concepts using curated aliases/cache plus ontology lookup providers |
| **Search Repository** | Search GEO using grounded labels and synonyms |
| **Normalize Records** | Convert GEO API payloads into shared `DatasetCandidate` records |
| **Annotate Evidence** | Identify metadata fields that support facet matches; collect evidence snippets |
| **Rank Results** | Score and order candidates by evidence (`evidence_score`) and match tier (`display_rank_score`); see [dataset ranking](docs/dataset-ranking.md) |
| **Respond** | Render chat response, structured `dataset_search` payload, and warnings |

| Question | What you should see |
|----------|---------------------|
| `Find public RNA-seq datasets for ulcerative colitis colon tissue` | Ranked GEO datasets in the middle panel; trace steps above; requested vs observed assay, evidence snippets, metadata warnings; **Load more** when additional GEO hits remain |
| `Find public RNA-seq datasets for UC colon tissue` | Same as above: `UC` resolves to ulcerative colitis for search planning; **4 search strategies**; GEO query uses full disease terms, not `UC` |
| `Find public RNA-seq datasets for Crohn's disease ileum tissue` | Disease and tissue resolved via phrase grounding; **4 search strategies** |

#### Query interpretation: what works and what can still break

Interpretation runs in three layers:

1. **Regex patterns** — fast matches for common assays (`RNA-seq`), tissues (`colon`), and a small set of explicit disease phrases
2. **Abbreviation resolution** — short acronyms (`UC`, `CD`, `PD`, …) grounded via curated aliases and ontology lookup, with clinical-context checks
3. **Phrase resolution** — multi-word n-grams grounded via curated aliases, OLS/BioPortal, and optional LLM expansion

Abbreviations are resolved for **understanding** but excluded from **GEO query strings** when they are ambiguous (e.g. `UC` is never sent to NCBI; `ulcerative colitis` is).

**Synonym tiers (retrieval vs evidence)**

| Source | Used in GEO primary query | Used in evidence matching |
|--------|---------------------------|---------------------------|
| Preferred label | Yes | Yes |
| OLS/BioPortal exact synonyms | Yes | Yes |
| Curated dataset phrases (e.g. `colonic`, `RNA-seq`) | Yes | Yes |
| OLS broad / related synonyms (e.g. `hindgut` for colon) | No | Yes |
| Contextual acronyms (`UC`, `PD`, …) | No | Yes, with supporting context |

Related ontology synonyms can support ranking and evidence snippets but do not automatically broaden the primary repository search.

**What works well**

| Query shape | Example | Notes |
|-------------|---------|-------|
| Full disease + tissue + assay | `Find public RNA-seq datasets for ulcerative colitis colon tissue` | Baseline path; **4 search strategies** |
| Clinical abbreviations with context | `Find public RNA-seq datasets for UC colon tissue` | `UC` → ulcerative colitis; requires supporting context (colon, colitis, tissue, …) |
| Multi-word disease/tissue not in regex | `Find public RNA-seq datasets for Crohn's disease ileum tissue` | Phrase grounding via curated cache or OLS |
| Punctuation-normalized phrasing | `ulcerative-colitis`, `Crohn's disease; ileum`, `Parkinson's disease (PD) substantia nigra` | Parentheticals stripped for n-grams; abbrevs extracted from `(UC)` / `(PD)`; hyphens and apostrophes normalized for lookup |
| Hyphenated compounds | `ulcerative-colitis`, `UC-colon biopsies` | Lookup tries spaced variants (`ulcerative colitis`) |
| Curated concepts | ulcerative colitis, Crohn's disease, Parkinson's disease, colon, ileum, RNA-seq, human | Fast, offline hits |

**Safety behavior (intentional)**

- Abbreviations like `UC` at `UC Berkeley` are **not** resolved as disease (no clinical context)
- Blocked acronyms are used for facet intent, not GEO retrieval query terms
- Grounded concepts must match expected ontology IDs for the slot (e.g. UBERON anatomy is not accepted as a disease)

**What can still break**

| Limitation | Example | Why |
|------------|---------|-----|
| Inverted or non-adjacent phrasing | `ileum biopsies from Crohn's patients` | Phrase scan uses contiguous n-grams; disease/tissue words far apart may not form a groundable phrase |
| Multi-clause sentences | `I need RNA-seq. Disease is lupus. Tissue is kidney.` | No full-sentence semantic parser; each clause is not interpreted independently |
| Unknown terms outside ontology coverage | Obscure disease names with no OLS/MONDO match | Dynamic lookup capped at 6 OLS/BioPortal attempts per query after curated misses |
| List ordering for tissues | `ileum, colon, Crohn's disease` | First grounded tissue wins (`colon` before `ileum` in scan order) |
| Single-word dynamic lookup | Rare one-word tissue/disease/assay terms not in curated cache | Dynamic pass allows single-word **disease** and **assay** when OLS returns a strong match; tissue still prefers curated anatomy; acronyms remain guarded |
| Assay / organism regex coverage | `ChIP-seq`, `mouse` studies | Regex patterns are narrow; may need phrase grounding or pattern expansion |
| LLM expansion | Obscure aliases | Requires `ANTHROPIC_API_KEY`; without it, only curated + OLS/BioPortal exact/synonym matches apply |
| Unusual nested punctuation | Multiple parentheticals, heavy nested qualifiers | Parentheticals are stripped; very complex structure may still produce noisy n-grams |

**Tips for reliable dataset-discovery queries**

- Prefer `{assay} datasets for {disease} {tissue}` when possible
- Spell out disease names or use abbreviations with clinical context (`UC colon tissue`, not `UC` alone)
- Use commas or semicolons between facets freely; hyphens and apostrophes in disease names are fine
- If a term is important and often used, add it to `server/domain/ontology_providers/curated.py` for faster, more reliable routing

#### GEO retrieval and load more

Dataset discovery retrieves GEO records in batches rather than ranking the entire repository at once.

| Setting / field | Meaning |
|-----------------|--------|
| `GEO_MAX_RESULTS` | Batch size for each initial search and each **Load more** click (default `15`, cap `200`) |
| `total_found` | Maximum hit count across all search strategies (e.g. disease-only broad query) |
| `primary_total_found` | Hit count for the strict disease + assay + tissue query |
| `retrieved_count` | Number of GEO records fetched and ranked so far |
| `has_more` | Whether additional unseen GEO IDs remain in the strategy cursors |
| `load_more_cursor` | Opaque state returned to the client for the next batch |

**Initial query** runs all strategy count queries, retrieves the first batch (strict strategy first), annotates evidence, ranks, and returns a cursor.

**Load more** (`POST /api/dataset-search/more`) sends the cursor plus the current ranked candidates. The server:

1. Pages the next unseen GEO IDs using per-strategy `retstart` offsets (strict → broad)
2. Fetches metadata (`esummary`) for the new batch only
3. Annotates the new records
4. Merges with prior candidates and **re-ranks the full retrieved set** by evidence

The UI banner shows `Showing X of Y GEO hits` where `Y` is `total_found` and `X` is `retrieved_count`. Use **Load more** to increase `X` without re-running the original chat query.

While loading, a sticky action bar above the query input shows a spinner and status; newly fetched datasets are highlighted and the view scrolls to the first new result.

When dataset discovery results are shown, the middle column uses a **split layout**: query context (hit counts, facets, grounded concepts) stays fixed at the top; only the ranked dataset cards scroll in the pane below.

**Tips for reliable routing:**

- Use standard gene symbols (`BRCA1`, not `brca1`).
- Include action or domain keywords: `gene`, `variants`, `literature`, `structure`, `search`, `pathogenic`, `summarize`.
- For ClinVar **by condition**, include a disease term (`syndrome`, `disease`, `disorder`, `condition`)—not just a colloquial name.
- Multi-tool queries can take 10–30 seconds; watch the trace panel for progress.

### Ontology normalization (standard agent path)

After gene/literature/ClinVar tools run, the agent maps free-text terms from **tool results** to formal ontology IDs (MONDO, HP, GO, NCBITaxon, CHEBI, UBERON) using a three-tier lookup in `tools/ontology_normalizer.py`: **OLS** → **BioPortal** (`BIOPORTAL_API_KEY`) → **Claude synonym expansion** (`ANTHROPIC_API_KEY`). Results appear on each tool payload as `normalized_terms` and in a **`normalize`** trace step labeled **Normalize (tool results)**.

This is separate from dataset discovery, where **Ground Query** maps requested facets via curated aliases/cache and ontology lookup providers (OLS, BioPortal, LLM disambiguation) and **Normalize Records** handles GEO payload shaping.

| Question | What normalization demonstrates | Optional env vars |
|----------|--------------------------------|-------------------|
| `marfan syndrome variants` | ClinVar condition text → MONDO via OLS tier 1 (`match_type: exact` or `synonym`) | — |
| `What ClinVar variants are linked to Marfan syndrome?` | Same ClinVar condition grounding after a multi-tool run | — |
| `CFTR pathogenic variants` | MyGene GO terms and UniProt organism name → GO / NCBITaxon | — |
| `TP53 variants` | Gene display name and ClinVar variant conditions → MONDO / HP where matched | — |
| `breast cancer gene` (colloquial phrasing) | Tier 3: Claude expands synonyms, then OLS retry (`match_type: ai_expanded_synonym`) | `ANTHROPIC_API_KEY` |
| Niche agricultural/environmental terms in tool results | BioPortal fallback when OLS has no hit | `BIOPORTAL_API_KEY` |

**Note:** Pure literature queries (e.g. `breast cancer literature`) usually produce a **skipped** normalize step today—PubMed/OpenAlex/Europe PMC results do not yet expose MeSH/keyword fields for extraction. Use gene, ClinVar, or MyGene/UniProt queries to see normalization in action.

Normalization is non-blocking: if lookup fails, the query still completes and unmatched terms show `match_type: "unmatched"`.

**Queries that route poorly today** (orchestrator heuristics, not normalization):

| Question | Issue | Better phrasing |
|----------|--------|-----------------|
| `Type 2 diabetes variants` | No `disease`/`syndrome`/… keyword → ClinVar params may not resolve | `Type 2 diabetes disease variants` or `ClinVar variants for diabetes condition` |
| `childhood asthma` | No literature or disease keyword | `Find literature on childhood asthma` |
| `What is cystic fibrosis` | No tool keywords unless gene symbol present | `search articles on cystic fibrosis` or `CFTR gene` |

## Project layout

```
sciagent-io/
├── server/
│   ├── agent/              # Orchestrator, registry, tracing
│   ├── tools/              # Scientific API clients
│   └── sciagent_server/    # FastAPI app
├── web/                    # Vite + React frontend
├── deploy/nginx.conf
├── Dockerfile
├── Dockerfile.web
└── docker-compose.yml
```

## Local development

### Backend

```bash
cp .env.example .env
cd server
uv sync
PYTHONPATH=. uv run uvicorn sciagent_server.main:app --reload --port 8000
```

Edit `.env` and set **`NCBI_EMAIL`** to your contact address. NCBI requires this for E-utilities requests (PubMed, ClinVar, GEO, and related tools). `PUBMED_EMAIL` is still accepted as a fallback. Add **`NCBI_API_KEY`** from [NCBI account settings](https://www.ncbi.nlm.nih.gov/account/settings/) for a higher rate limit (recommended for GEO dataset search and production).

Or from the repo root:

```bash
./scripts/run_server.sh
```

API: http://localhost:8000/api/health

### Frontend

```bash
cd web
npm install
npm run dev
```

UI: http://localhost:5173 (proxies `/api` to port 8000)

### Docker (full stack)

```bash
cp .env.example .env
docker compose up --build
```

- UI: http://localhost:8080
- API: http://localhost:8000/api/health

## Developer evaluation (golden queries)

Regression harness for integrated GEO + Expression Atlas dataset discovery (not exposed in the UI). Runs four fixed RNA-seq queries, reports interpretation, grounding, per-source hits, top-10 ranking (`display_rank_score`, `evidence_score`, `rank_tier`, assay sub-tiers), and fails on assay-ranking violations (e.g. proteomics partials above RNA-seq-supported partials).

```bash
./scripts/run_golden_queries.sh
```

See [docs/evaluation/golden_queries.md](docs/evaluation/golden_queries.md) for metrics, NCBI setup, and pytest commands. Scoring and rank tiers are documented in [docs/dataset-ranking.md](docs/dataset-ranking.md).

## API

### `POST /api/query`

Request:

```json
{ "query": "BRCA1 gene information" }
```

Response:

```json
{
  "response": "Based on your query ...",
  "traces": [{ "id": "agent_run", "steps": [...], "status": "completed" }],
  "dataset_search": { "...": "present for dataset-discovery queries" }
}
```

### `POST /api/dataset-search/more`

Load the next GEO batch for an in-progress dataset discovery result. Reuses the cursor from `dataset_search.load_more_cursor` and re-ranks merged candidates.

Request:

```json
{
  "load_more_cursor": { "...": "from prior dataset_search response" },
  "candidates": [{ "...": "current ranked candidates" }]
}
```

Response:

```json
{
  "dataset_search": { "...": "updated ranked results and cursor" },
  "added_count": 15,
  "has_more": true
}
```

### `GET /api/tools`

Returns registered tools from `ToolRegistry.list_tools()`.

### `GET /api/health`

Returns `{ "status": "ok", "version": "0.1.0" }`.

## Trace format

Each trace document includes:

| Step | Description |
|------|-------------|
| `interpret_query` | *(dataset discovery)* **Interpret Query** — extracted disease, tissue, assay, organism |
| `ground_query` | *(dataset discovery)* **Ground Query** — curated aliases/cache plus ontology lookup providers |
| `search_repository` | *(dataset discovery)* **Search Repository** — GEO or Expression Atlas search using grounded synonyms |
| `normalize_records` | *(dataset discovery)* **Normalize Records** — repository payloads → `DatasetCandidate` |
| `annotate_evidence` | *(dataset discovery)* **Annotate Evidence** — field-level concept/evidence matching |
| `rank_results` | *(dataset discovery)* **Rank Results** — evidence-based scoring |
| `respond` | *(dataset discovery)* **Respond** — rendered answer and structured results |
| `plan` | Goal and `tools_needed` |
| `iteration` | Loop counter |
| `tool_execution` | Tool name, status, parameters, result |
| `observe` | Success/failure counts |
| `synthesize` | Updated plan |
| `normalize` | *(standard agent path)* **Normalize (tool results)** — OLS / BioPortal / Claude on tool outputs |
| `error` | Failure details (if any) |

The React trace panel renders these as a color-coded timeline instead of raw JSON.

## Environment variables

See [`.env.example`](.env.example). Key variables:

**NCBI E-utilities:** set `NCBI_EMAIL` before using PubMed, ClinVar, or GEO dataset search (see setup above). Without it, NCBI may rate-limit or reject requests.

| Variable | Purpose |
|----------|---------|
| `SCIAGENT_HOST` / `SCIAGENT_PORT` | API bind address |
| `SCIAGENT_CORS_ORIGINS` | Allowed browser origins (comma-separated) |
| `SCIAGENT_EXCLUDED_SOURCES` | Optional blocklist of external data sources to skip (`pubmed`, `openalex`, `europepmc`, `expression_atlas`, `immport`, `mygene`, `uniprot`, `clinvar`, `alphafold`, `geo_dataset_search`). Excluding `geo_dataset_search` routes dataset-style queries to Expression Atlas and ImmPort when enabled; with all enabled, GEO, GXA, and ImmPort results are merged and ranked together. Planned NIAID sources (`omicsdi`, `vdjserver`, `vivli`) appear in `GET /api/config` but are not enabled until connectors ship. |
| `SCIAGENT_EXCLUDED_TOOLS` | Optional blocklist of agent tools to skip (`summarize`) |
| `NCBI_EMAIL` | **Recommended.** Contact email for NCBI E-utilities (PubMed, ClinVar, GEO); `PUBMED_EMAIL` fallback |
| `NCBI_API_KEY` | Optional NCBI API key for higher E-utilities rate limits |
| `GEO_MAX_RESULTS` | Max GEO records to retrieve and rank per dataset-discovery query (default `15`, cap `200`) |
| `OPENALEX_EMAIL` | OpenAlex `mailto` parameter |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | Optional summarization and ontology tier 3 |
| `SCIAGENT_LLM_INTERPRET` | When `true` (default) and `ANTHROPIC_API_KEY` is set, run a separate `interpret_llm` trace step when rule-based interpret leaves disease/tissue/assay empty; set `false` to A/B test with LLM off |
| `BIOPORTAL_API_KEY` | Optional BioPortal ontology lookup (tier 2) |

## Deployment

### Render (backend)

1. Create a **Web Service** from this repo.
2. Use the root `Dockerfile` or run:
   `cd server && uv sync && PYTHONPATH=. uv run uvicorn sciagent_server.main:app --host 0.0.0.0 --port $PORT`
3. Set environment variables from `.env.example`. At minimum for GEO/PubMed/ClinVar:
   - `NCBI_EMAIL` (required by NCBI policy)
   - `NCBI_API_KEY` (strongly recommended — shared by the web app and all NCBI tools; not stored in the frontend)
4. Health check path: `/api/health`
5. Increase request timeout to **120s** for multi-tool queries.

The web app does **not** use the golden-query `--pause-between-queries` setting. Each user query is throttled inside `geo_dataset_search` (~3 req/s without a key, ~10 req/s with `NCBI_API_KEY`) and retries on HTTP 429. The pause flag is only for the developer harness when running several evaluation queries back-to-back from your laptop.

### Vercel (frontend)

1. Set **Root Directory** to `web`.
2. Build command: `npm run build`
3. Output directory: `dist`
4. Environment variable: `VITE_API_BASE=https://<your-render-service>.onrender.com`
5. Add your Vercel URL to backend `SCIAGENT_CORS_ORIGINS`.

For same-origin API access in production without CORS, use the Docker/nginx stack (`docker compose`) or proxy `/api` through your frontend host.

## License

See repository license file if present.
