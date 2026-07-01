FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY server/pyproject.toml server/uv.lock ./server/
WORKDIR /app/server
RUN uv sync --frozen --no-dev

WORKDIR /app
COPY server/agent ./server/agent
COPY server/tools ./server/tools
COPY server/sciagent_server ./server/sciagent_server

ENV PYTHONPATH=/app/server
ENV SCIAGENT_HOST=0.0.0.0
ENV SCIAGENT_PORT=8000
ENV SCIAGENT_CORS_ORIGINS=*

EXPOSE 8000

WORKDIR /app/server

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=8)"

CMD ["uv", "run", "uvicorn", "sciagent_server.main:app", "--host", "0.0.0.0", "--port", "8000"]
