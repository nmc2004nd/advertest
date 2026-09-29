# Image dùng chung cho service api và worker (tech-stack.md mục 6). TORCH=cpu (api, CI, worker-cpu)
# hoặc cuda (worker có GPU). Worker ghi đè entrypoint bằng `advertest-worker run`, cache ở /app/cache.
# Build context là gốc repo: docker build -f docker/api/Dockerfile .
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /usr/local/bin/uv

ARG TORCH=cpu
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Cài dependency trước (layer được cache khi chỉ đổi code).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra "$TORCH" --no-install-project

COPY contracts ./contracts
COPY ml_core ./ml_core
COPY attacks ./attacks
COPY backend ./backend
RUN uv sync --frozen --no-dev --extra "$TORCH"

COPY docker/api/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN useradd --system --uid 10001 --home-dir /app advertest \
    && mkdir -p /app/cache && chown advertest /app/cache
USER advertest

# Image không có .git: commit được truyền lúc build để /health báo đúng.
ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=$GIT_COMMIT

EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
