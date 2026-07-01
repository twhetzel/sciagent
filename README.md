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

## Tool inventory

| Tool | Data source | Auth |
|------|-------------|------|
| `pubmed` | NCBI E-utilities (PubMed) | `PUBMED_EMAIL`, `PUBMED_TOOL` recommended |
| `openalex` | OpenAlex REST API | Optional `OPENALEX_EMAIL` |
| `europepmc` | Europe PMC REST API | None |
| `mygene` | MyGene.info v3 | None |
| `uniprot` | UniProt REST | None |
| `clinvar` | NCBI E-utilities (ClinVar) | Same NCBI env vars as PubMed |
| `alphafold` | AlphaFold EBI API | None |
| `geo_dataset_search` | NCBI GEO (GDS) | Same NCBI env vars as PubMed |
| `summarize` | OpenAI / Anthropic | `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY` |
| *(post-processing)* | OLS / BioPortal / Claude | Optional `BIOPORTAL_API_KEY`, `ANTHROPIC_API_KEY` for ontology normalization |

The orchestrator uses keyword heuristics (not LLM tool-calling) to select tools. On the standard agent path, `tools/ontology_normalizer.py` runs after tools finish and appears in the trace as **Normalize (tool results)**. Dataset discovery queries use a separate seven-step pipeline documented below.

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
| **Interpret Query** | Extract disease, tissue, assay, organism facets from the query |
| **Ground Query** | Map requested facets to ontology concepts (curated seed mappings) |
| **Search Repository** | Search GEO using grounded labels and synonyms |
| **Normalize Records** | Convert GEO API payloads into shared `DatasetCandidate` records |
| **Annotate Evidence** | Identify metadata fields that support facet matches; collect evidence snippets |
| **Rank Results** | Score candidates by evidence coverage (requested facets are not inherited without evidence) |
| **Respond** | Render chat response, structured `dataset_search` payload, and warnings |

| Question | What you should see |
|----------|---------------------|
| `Find public RNA-seq datasets for ulcerative colitis colon tissue` | Ranked GEO datasets in the middle panel; trace steps above; requested vs observed assay, evidence snippets, metadata warnings |

**Tips for reliable routing:**

- Use standard gene symbols (`BRCA1`, not `brca1`).
- Include action or domain keywords: `gene`, `variants`, `literature`, `structure`, `search`, `pathogenic`, `summarize`.
- For ClinVar **by condition**, include a disease term (`syndrome`, `disease`, `disorder`, `condition`)—not just a colloquial name.
- Multi-tool queries can take 10–30 seconds; watch the trace panel for progress.

### Ontology normalization (standard agent path)

After gene/literature/ClinVar tools run, the agent maps free-text terms from **tool results** to formal ontology IDs (MONDO, HP, GO, NCBITaxon, CHEBI, UBERON) using a three-tier lookup in `tools/ontology_normalizer.py`: **OLS** → **BioPortal** (`BIOPORTAL_API_KEY`) → **Claude synonym expansion** (`ANTHROPIC_API_KEY`). Results appear on each tool payload as `normalized_terms` and in a **`normalize`** trace step labeled **Normalize (tool results)**.

This is separate from dataset discovery, where **Ground Query** handles ontology mapping of the user request and **Normalize Records** handles GEO payload shaping.

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
  "traces": [{ "id": "agent_run", "steps": [...], "status": "completed" }]
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
| `ground_query` | *(dataset discovery)* **Ground Query** — ontology mapping of requested facets |
| `search_repository` | *(dataset discovery)* **Search Repository** — GEO search using grounded synonyms |
| `normalize_records` | *(dataset discovery)* **Normalize Records** — GEO payloads → `DatasetCandidate` |
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

| Variable | Purpose |
|----------|---------|
| `SCIAGENT_HOST` / `SCIAGENT_PORT` | API bind address |
| `SCIAGENT_CORS_ORIGINS` | Allowed browser origins (comma-separated) |
| `PUBMED_EMAIL` | NCBI politeness for PubMed/ClinVar |
| `OPENALEX_EMAIL` | OpenAlex `mailto` parameter |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | Optional summarization and ontology tier 3 |
| `BIOPORTAL_API_KEY` | Optional BioPortal ontology lookup (tier 2) |

## Deployment

### Render (backend)

1. Create a **Web Service** from this repo.
2. Use the root `Dockerfile` or run:
   `cd server && uv sync && PYTHONPATH=. uv run uvicorn sciagent_server.main:app --host 0.0.0.0 --port $PORT`
3. Set environment variables from `.env.example`.
4. Health check path: `/api/health`
5. Increase request timeout to **120s** for multi-tool queries.

### Vercel (frontend)

1. Set **Root Directory** to `web`.
2. Build command: `npm run build`
3. Output directory: `dist`
4. Environment variable: `VITE_API_BASE=https://<your-render-service>.onrender.com`
5. Add your Vercel URL to backend `SCIAGENT_CORS_ORIGINS`.

For same-origin API access in production without CORS, use the Docker/nginx stack (`docker compose`) or proxy `/api` through your frontend host.

## License

See repository license file if present.
