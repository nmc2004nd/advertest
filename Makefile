# Lệnh chung cho agent và CI. Chạy `make help` để xem danh sách.
# TORCH chọn biến thể torch: cpu (dev, CI) hoặc cuda (image Docker).

SHELL := /bin/bash
TORCH ?= cpu
UV_RUN := uv run --extra $(TORCH)
PNPM := pnpm --dir frontend
COMPOSE_FILE := docker/compose.yaml

# pytest trả mã 5 khi không thu được test nào; lúc đó coi là pass nhưng in rõ.
define pytest_allow_empty
	@$(UV_RUN) pytest $(1); code=$$?; \
	if [ $$code -eq 5 ]; then echo ">> Chưa có test nào trong: $(1)"; exit 0; fi; \
	exit $$code
endef

# Target của phần chưa làm: báo rõ thiếu gì, thuộc group nào, rồi thoát với mã 1.
define require_file
	@if [ ! -e "$(1)" ]; then echo ">> Chưa có $(1) ($(2))"; exit 1; fi
endef

.PHONY: help up down migrate contracts contracts-check fixtures lint typecheck test test-db test-acceptance check

help:
	@echo "up | down | migrate | contracts | contracts-check | fixtures | lint | typecheck | test | test-db | test-acceptance | check"

up:
	$(call require_file,$(COMPOSE_FILE),Phase 0 Group 7)
	docker compose -f $(COMPOSE_FILE) up -d --wait

down:
	$(call require_file,$(COMPOSE_FILE),Phase 0 Group 7)
	docker compose -f $(COMPOSE_FILE) down

migrate:
	$(call require_file,backend/alembic.ini,Phase 0 Group 3)
	$(UV_RUN) alembic -c backend/alembic.ini upgrade head

GENERATED := contracts/schemas contracts/openapi.json frontend/src/contracts

contracts:
	$(UV_RUN) python scripts/gen_contracts.py

# Sinh lại rồi so với bản đã commit: file sinh ra phải luôn khớp với nguồn Pydantic.
contracts-check: contracts
	@if [ -n "$$(git status --porcelain -- $(GENERATED))" ]; then \
		echo ">> File sinh từ contract lệch với bản đã commit (chạy make contracts rồi commit):"; \
		git status --porcelain -- $(GENERATED); exit 1; fi

fixtures:
	$(call require_file,scripts/fetch_fixtures.py,Phase 0 Group 6)
	$(UV_RUN) python scripts/fetch_fixtures.py

lint:
	$(UV_RUN) ruff check .
	$(UV_RUN) ruff format --check .
	$(PNPM) lint

typecheck:
	$(UV_RUN) mypy
	$(PNPM) typecheck

# Test đánh dấu `db` cần Postgres thật: chạy bằng `make test-db` (tự dựng container).
test:
	$(call pytest_allow_empty,--ignore=tests/acceptance -m "not db")
	@if grep -q '"test":' frontend/package.json; then $(PNPM) test; \
	else echo ">> Frontend chưa có script test (Phase 0 Group 5)"; fi

test-db:
	docker/postgres/test-db.sh $(UV_RUN) pytest -m db backend

test-acceptance:
	$(call pytest_allow_empty,tests/acceptance)

check: lint typecheck contracts-check test test-acceptance
