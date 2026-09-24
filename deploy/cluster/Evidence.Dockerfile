ARG BACKEND_IMAGE=zagent-backend:plan9
FROM ${BACKEND_IMAGE}
COPY services/agent/zagent ./services/agent/zagent
COPY services/agent/tests ./services/agent/tests
COPY evals ./evals
COPY .github/workflows ./.github/workflows
COPY deploy/cluster ./deploy/cluster
COPY deploy/cluster/run_checks.py ./deploy/cluster/run_checks.py
COPY conftest.py Tiltfile .gitignore .dockerignore ./
RUN uv sync --frozen
ENV UV_OFFLINE=1