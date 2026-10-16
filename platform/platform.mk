# Mac platform targets, included from the root Makefile. Run from the repo root.
COMPOSE ?= docker compose
export CS_PLATFORM_DIR := $(CURDIR)/platform
PLATFORM_ENV = $(if $(MODE),PROTECTION_MODE=$(MODE)) $(if $(BACKEND),LLM_BACKEND=$(BACKEND)) \
	$(if $(CHAOS),CHAOS_ENABLED=$(CHAOS))
VENV_PY = platform/.venv/bin/python

.PHONY: platform-build platform-up platform-down platform-restart platform-logs platform-ps \
	platform-smoke calibrate platform-ladder platform-breaker seed-cache

platform-build: ## Build the platform image
	$(COMPOSE) --profile platform build

platform-up: ## Start the platform (MODE=none|reactive|cascadeshield BACKEND=ollama|mock CHAOS=1)
	$(PLATFORM_ENV) $(COMPOSE) --profile platform up -d --build --wait

platform-down: ## Stop the platform (keeps the submissions volume)
	$(COMPOSE) --profile platform down

platform-restart: platform-down platform-up ## Restart, e.g. to switch MODE between experiment runs

platform-logs: ## Tail platform logs
	$(COMPOSE) --profile platform logs -f --tail 50

platform-ps: ## Show platform containers, health and restart counts
	@$(COMPOSE) --profile platform ps --format 'table {{.Service}}\t{{.Status}}'

platform-smoke: ## Ask one tutor question and submit one quiz through the gateway
	@python3 platform/tools/smoke.py

calibrate: ## Ollama baseline (guide 3.2): writes docs/calibration_run.md
	python3 platform/tools/calibrate.py --out docs/calibration_run.md

platform-ladder: ## Phase 2 check: levels 0-4, breaker, shed queue, failsafe (cascadeshield mode)
	$(VENV_PY) platform/tools/ladder_check.py

platform-breaker: ## Phase 2 check: local breaker and chaos hooks (MODE=reactive CHAOS=1)
	$(VENV_PY) platform/tools/breaker_check.py

seed-cache: ## Answer data/faq.yaml at level 0 into data/cache_seed.yaml (LOAD=1: reload only)
	$(VENV_PY) platform/tools/seed_cache.py $(if $(LOAD),--load)
