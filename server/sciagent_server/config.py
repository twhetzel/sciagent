"""Environment-based configuration for SciAgent server."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

API_VERSION = "0.1.0"

HOST = os.environ.get("SCIAGENT_HOST", "127.0.0.1")
PORT = int(os.environ.get("SCIAGENT_PORT", "8000"))
WORKERS = int(os.environ.get("SCIAGENT_WORKERS", "1"))

CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "SCIAGENT_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://localhost:8080",
    ).split(",")
    if origin.strip()
]
