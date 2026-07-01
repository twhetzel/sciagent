# SciAgent

SciAgent is a scientific multi-database search agent with transparent execution tracing. Ask a natural-language question; the agent plans which databases to query, executes tools server-side, and returns both a synthesized answer and a step-by-step execution trace.

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

The FastAPI layer is intentionally thin: it only calls `orchestrator.run(prompt)` and exposes the result. All routing logic lives in the ported SciAgent agent module.

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
| `summarize` | OpenAI / Anthropic | `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY` |

The orchestrator uses keyword heuristics (not LLM tool-calling) to select tools. Example queries:

- `BRCA1 gene` — MyGene, UniProt, ClinVar
- `TP53 variants` — ClinVar, gene/protein tools
- `breast cancer literature` — PubMed, OpenAlex, Europe PMC
- `AlphaFold structure for EGFR` — AlphaFold (+ UniProt lookup)

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
| `plan` | Goal and `tools_needed` |
| `iteration` | Loop counter |
| `tool_execution` | Tool name, status, parameters, result |
| `observe` | Success/failure counts |
| `synthesize` | Updated plan |
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
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | Optional summarization |

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
