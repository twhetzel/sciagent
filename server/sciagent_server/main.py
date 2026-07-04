"""FastAPI entrypoint for SciAgent Studio."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Ensure agent/ and tools/ imports resolve when running from server/
_server_root = Path(__file__).resolve().parent.parent
if str(_server_root) not in sys.path:
    sys.path.insert(0, str(_server_root))

from agent.orchestrator import AgentOrchestrator
from agent.registry import ToolRegistry

from . import config

app = FastAPI(
    title="SciAgent Studio API",
    description="Multi-database scientific search agent with transparent execution tracing",
    version=config.API_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = AgentOrchestrator()
registry = ToolRegistry()


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)


class QueryResponse(BaseModel):
    response: str
    traces: list[dict[str, Any]]
    dataset_search: dict[str, Any] | None = None


class DatasetSearchLoadMoreRequest(BaseModel):
    load_more_cursor: dict[str, Any]
    candidates: list[dict[str, Any]] = Field(default_factory=list)


class DatasetSearchLoadMoreResponse(BaseModel):
    dataset_search: dict[str, Any]
    added_count: int = 0
    has_more: bool = False


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": config.API_VERSION}


@app.get("/api/tools")
def list_tools() -> list[dict[str, Any]]:
    return registry.list_tools()


@app.post("/api/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    response, traces, dataset_search = orchestrator.run(req.query)
    return QueryResponse(
        response=response,
        traces=traces,
        dataset_search=dataset_search,
    )


@app.post("/api/dataset-search/more", response_model=DatasetSearchLoadMoreResponse)
def dataset_search_load_more(
    req: DatasetSearchLoadMoreRequest,
) -> DatasetSearchLoadMoreResponse:
    from agent import dataset_discovery as pipeline
    from domain.dataset_search import DatasetCandidate, DatasetSearchCursor
    from fastapi import HTTPException

    if not registry.get_tool("geo_dataset_search"):
        raise HTTPException(
            status_code=403,
            detail="Dataset discovery is disabled (geo_dataset_search is listed in SCIAGENT_EXCLUDED_SOURCES).",
        )

    cursor = DatasetSearchCursor.model_validate(req.load_more_cursor)
    existing = [DatasetCandidate.model_validate(item) for item in req.candidates]
    prior_count = len(existing)

    try:
        result = pipeline.load_more_dataset_search(cursor, existing)
    except RuntimeError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=502, detail=str(exc)) from exc

    payload = pipeline.dataset_search_result_payload(result)
    return DatasetSearchLoadMoreResponse(
        dataset_search=payload,
        added_count=max(0, len(result.candidates) - prior_count),
        has_more=result.has_more,
    )


def run() -> None:
    kwargs: dict[str, Any] = {
        "host": config.HOST,
        "port": config.PORT,
        "reload": config.WORKERS == 1,
    }
    if config.WORKERS > 1:
        kwargs["workers"] = config.WORKERS
    uvicorn.run("sciagent_server.main:app", **kwargs)


if __name__ == "__main__":
    run()
