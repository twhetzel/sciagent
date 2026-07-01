"""FastAPI entrypoint for SciAgent."""

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
    title="SciAgent API",
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


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": config.API_VERSION}


@app.get("/api/tools")
def list_tools() -> list[dict[str, Any]]:
    return registry.list_tools()


@app.post("/api/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    response, traces = orchestrator.run(req.query)
    return QueryResponse(response=response, traces=traces)


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
