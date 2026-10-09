# Lệnh chung cho agent và CI. Chạy `make help` để xem danh sách.
# TORCH chọn biến thể torch: cpu (dev, CI) hoặc cuda (image Docker).

SHELL := /bin/bash
TORCH ?= cpu
UV_RUN := uv run --extra $(TORCH)
PNPM := pnpm --dir frontend
COMPOSE_FILE := docker/compose.yaml
# File biến môi trường cho Docker Compose (xem .env.example).
ENV_FILE ?= .env
COMPOSE := docker compose -f $(COMPOSE_FILE) --env-file $(ENV_FILE)

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

.PHONY: help up down migrate contracts contracts-check fixtures lint typecheck test test-db test-acceptance test-e2e check check-fast

help:
	@echo "up | down | migrate | contracts | contracts-check | fixtures | lint | typecheck | test | test-db | test-acceptance | test-e2e | check | check-fast P=<đường dẫn>"

up:
	$(call require_file,$(COMPOSE_FILE),Phase 0 Group 7)
	$(call require_file,$(ENV_FILE),tạo từ .env.example)
	$(COMPOSE) up -d --build --wait

down:
	$(call require_file,$(COMPOSE_FILE),Phase 0 Group 7)
	$(COMPOSE) down

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
	docker/postgres/test-db.sh $(UV_RUN) pytest -m db backend tests/acceptance

# E2E Playwright 3 viewport với backend thật trên Postgres tạm (cần `pnpm --dir frontend exec
# playwright install chromium` ở lần đầu).
test-e2e:
	docker/postgres/test-db.sh scripts/e2e.sh

# Test nghiệm thu cần Postgres/MinIO (marker `db`) chạy trong `make test-db`.
test-acceptance: fixtures
	$(call pytest_allow_empty,tests/acceptance -m "not db")

check: lint typecheck contracts-check test test-acceptance

# Vòng lặp nhanh trong lúc implement, chỉ trên đường dẫn P (thư mục hoặc file, cách nhau bởi dấu cách).
# Python: ruff + mypy (cache tăng dần) + pytest "not db" trên P; frontend/: lint, typecheck, test.
# Không thay `make check`: check đầy đủ vẫn bắt buộc ở cuối group và trước merge.
P ?=
PY_P := $(filter-out frontend frontend/%,$(P))
FE_P := $(filter frontend frontend/%,$(P))
check-fast:
	@test -n "$(strip $(P))" || { echo ">> Dùng: make check-fast P='backend/app tests/acceptance/phase_r2'"; exit 2; }
ifneq ($(strip $(PY_P)),)
	$(UV_RUN) ruff check $(PY_P)
	$(UV_RUN) ruff format --check $(PY_P)
	$(UV_RUN) mypy
	$(call pytest_allow_empty,-q --tb=short -m "not db" $(PY_P))
endif
ifneq ($(strip $(FE_P)),)
	$(PNPM) lint
	$(PNPM) typecheck
	@if grep -q '"test":' frontend/package.json; then $(PNPM) test; fi
endif
