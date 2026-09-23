FROM node:24-alpine AS job-ui
WORKDIR /build
COPY apps/web/package.json apps/web/package-lock.json ./apps/web/
RUN npm --prefix apps/web ci
COPY apps/web/scripts/build-mcp.mjs ./apps/web/scripts/build-mcp.mjs
COPY services/agent/zagent/job_ui ./services/agent/zagent/job_ui
RUN npm --prefix apps/web run build:mcp

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml uv.lock ./
COPY services/agent/zagent ./services/agent/zagent
COPY --from=job-ui /build/services/agent/zagent/resources/jobs.html ./services/agent/zagent/resources/jobs.html
RUN uv sync --frozen --no-dev
RUN python -m zagent.knowledge
EXPOSE 8000
CMD ["uvicorn", "zagent.app:app", "--host", "0.0.0.0", "--port", "8000"]
