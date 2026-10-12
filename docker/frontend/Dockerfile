# Frontend production (bản triển khai, deploy/railway/README.md): build tĩnh rồi Caddy phục vụ,
# proxy /api/* sang API (bỏ tiền tố /api, giống proxy của Vite khi dev).
# Build context là gốc repo: docker build -f docker/frontend/Dockerfile .
FROM node:22-alpine AS build
WORKDIR /app/frontend
RUN corepack enable && corepack prepare pnpm@12.6.0 --activate

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# src/api/mocks.ts glob contracts/mocks lúc build; bản production không chứa mock (verify:build).
COPY contracts/mocks /app/contracts/mocks
COPY frontend ./
ENV VITE_API_BASE_URL=/api \
    VITE_USE_MOCKS=false
RUN pnpm verify:build

FROM caddy:2.10.2-alpine
COPY docker/frontend/Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/frontend/dist /srv
