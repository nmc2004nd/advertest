# Image dùng chung cho service api và worker (tech-stack.md mục 6). TORCH=cpu (api, CI, worker-cpu)
# hoặc cuda (worker có GPU). Worker ghi đè entrypoint bằng `advertest-worker run`, cache ở /app/cache.
# Build context là gốc repo: docker build -f docker/api/Dockerfile .
# Stage `worker` (Phase R3) thêm fixture cho worker công cụ; stage cuối `api` là mặc định.
FROM python:3.11-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /usr/local/bin/uv

# Thư viện hệ thống cho opencv-python (ultralytics import cv2 khi nạp; api import qua ml_core).
# Phase 8: WeasyPrint (report PDF) cần pango, harfbuzz và font có dấu tiếng Việt (DejaVu).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libxcb1 \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

ARG TORCH=cpu
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    # User advertest không ghi được /app: cấu hình của matplotlib và ultralytics để ở /tmp.
    MPLCONFIGDIR=/tmp/matplotlib \
    YOLO_CONFIG_DIR=/tmp/ultralytics \
    # Phase 8: fontconfig (WeasyPrint) ghi cache vào $XDG_CACHE_HOME/fontconfig.
    XDG_CACHE_HOME=/tmp

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


# Worker (compose: target worker). `spec_check` và `model_check` cần 5 ảnh KITTI fixture, nhãn và
# yolov8n.pt ở FIXTURES_DIR (/app/tests/fixtures); chép từ tests/fixtures (`make fixtures`) và kiểm
# sha256 theo checksums.json: thiếu file hay lệch sha256 thì build fail.
FROM base AS worker
USER root
COPY tests/fixtures/checksums.json tests/fixtures/yolov8n.pt /app/tests/fixtures/
COPY tests/fixtures/kitti /app/tests/fixtures/kitti
COPY docker/worker/check_fixtures.py /tmp/check_fixtures.py
# Quyền của file trên máy build có thể là 600: chỉ đọc cho mọi user, không ghi được.
RUN chmod -R a+rX,go-w /app/tests \
    && python /tmp/check_fixtures.py /app/tests/fixtures \
    && rm /tmp/check_fixtures.py
USER advertest

FROM base AS api
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
