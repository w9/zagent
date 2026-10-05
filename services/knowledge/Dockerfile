FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH" \
    ZKNOWLEDGE_CORPUS=/app/services/knowledge/corpus
COPY pyproject.toml uv.lock ./
COPY services/knowledge ./services/knowledge
RUN uv sync --frozen --no-dev --package zknowledge
EXPOSE 8007
CMD ["uvicorn", "zknowledge.app:app", "--host", "0.0.0.0", "--port", "8007"]
