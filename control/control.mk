# Fedora control-room targets, included from the root Makefile. Run from the repo root.
UV       ?= uv
COMPOSE  ?= docker compose
SCENARIO ?= exam_ramp
PY       := .venv/bin/python
RUN_DIR  := .run
# Long experiments keep the laptop awake even with the lid closed: a suspend in the middle of a
# run invalidates it (it happened during an M3 check). Linux only; elsewhere this is empty.
NOSLEEP  := $(shell command -v systemd-inhibit >/dev/null 2>&1 && echo systemd-inhibit --what=sleep:idle:handle-lid-switch --who=cascadeshield --why=experiment)
export CS_CONTROL_DIR := $(CURDIR)/control
# Address the control containers use for the platform: PLATFORM_HOST (environment, else .env);
# a platform on this same host is in the same compose project, reached by service name ("compose").
_PLATFORM_HOST := $(or $(PLATFORM_HOST),$(shell sed -n 's/^PLATFORM_HOST=\([^ ]*\).*/\1/p' .env 2>/dev/null))
export CS_PLATFORM_ADDR := $(if $(filter-out localhost 127.0.0.1 compose,$(_PLATFORM_HOST)),$(_PLATFORM_HOST),compose)

# $(call bg,name,command): start a control process in the background, pid in control/.run
define bg
	@mkdir -p control/$(RUN_DIR)
	@cd control && { PYTHONPATH=. nohup $(2) > $(RUN_DIR)/$(1).log 2>&1 < /dev/null & echo $$! > $(RUN_DIR)/$(1).pid; }
	@echo "started $(1)  (log: control/$(RUN_DIR)/$(1).log)"
endef
define stop
	@if [ -f control/$(RUN_DIR)/$(1).pid ]; then kill $$(cat control/$(RUN_DIR)/$(1).pid) 2>/dev/null || true; \
		rm -f control/$(RUN_DIR)/$(1).pid; echo "stopped $(1)"; fi
endef

.PHONY: control-setup prom-targets prom-up control-up control-down platform-mock-up platform-mock-down control-native \
	check core dashboard load locust-ui test control-logs control-status episodes episodes-plan dataset train m3-check matrix figures screenshot

control-setup: ## Install control-room Python deps with uv
	cd control && $(UV) sync

prom-targets: ## Point Prometheus at PLATFORM_HOST (no restart needed)
	@python3 control/prometheus/render_targets.py

prom-up: prom-targets ## Start Prometheus only (for dataset runs, with the core stopped)
	$(COMPOSE) --profile control up -d prometheus

control-up: prom-targets ## Start the control room in containers: Prometheus, core, dashboard
	$(COMPOSE) --profile control up -d --build
	@echo "dashboard http://localhost:8501  core http://localhost:8600/state  prometheus http://localhost:9090"

control-native: prom-up ## Demo-safe start: Prometheus container + core and dashboard as local processes
	$(call stop,core)
	$(call stop,dashboard)
	$(call bg,core,$(PY) -m resilience_core.main)
	$(call bg,dashboard,$(PY) -m streamlit run dashboard/app.py --server.port 8501)
	@echo "dashboard http://localhost:8501  core http://localhost:8600/state  (stop: make control-down)"

control-down: ## Stop the control room (containers, and any native core/dashboard started by hand)
	$(call stop,dashboard)
	$(call stop,core)
	$(COMPOSE) --profile control stop prometheus resilience-core dashboard  # not `down`: that touches the platform too

platform-mock-up: ## Run the Mac's platform here with the mock LLM and chaos hooks (MODE=none by default)
	@# SELinux (Fedora): git rewrites platform/data with the default label, which containers cannot read
	@if command -v getenforce >/dev/null 2>&1 && [ "$$(getenforce)" = Enforcing ]; then \
		chcon -R -t container_file_t platform/data && echo "relabelled platform/data for SELinux"; fi
	$(MAKE) platform-up BACKEND=mock CHAOS=1 MODE=$(or $(MODE),none)

platform-mock-down: ## Stop the local platform
	$(MAKE) platform-down

check: ## Check the platform exposes every contract metric
	python3 scripts/check_contracts.py

core: ## Run the resilience core natively in the foreground (dev; stop the container first)
	cd control && PYTHONPATH=. $(PY) -m resilience_core.main

dashboard: ## Run the dashboard natively in the foreground (dev; stop the container first)
	cd control && PYTHONPATH=. $(PY) -m streamlit run dashboard/app.py

load: ## Headless Locust run: make load SCENARIO=exam_ramp
	@mkdir -p control/results
	cd control && RUN=$(SCENARIO)-$$(date +%Y%m%d-%H%M%S) && \
		PYTHONPATH=. CS_SCENARIO=$(SCENARIO) $(PY) -m locust -f chaos/locustfile.py --headless \
		--csv results/$$RUN --html results/$$RUN.html --only-summary

locust-ui: ## Locust web UI on :8089 (MANUAL=1: type your own user count)
	cd control && PYTHONPATH=. CS_SCENARIO=$(SCENARIO) CS_MANUAL=$(if $(MANUAL),1,0) $(PY) -m locust -f chaos/locustfile.py

test: ## Run control-room tests
	cd control && $(UV) run pytest -q

control-logs: ## Tail control-room logs
	tail -n 30 -f control/$(RUN_DIR)/*.log

control-status: ## Show what is running and the core's latest state
	@for f in control/$(RUN_DIR)/*.pid; do [ -f $$f ] && n=$$(basename $$f .pid) && \
		(kill -0 $$(cat $$f) 2>/dev/null && echo "up    $$n" || echo "dead  $$n"); done; true
	@$(COMPOSE) --profile control ps --format '{{.Service}}: {{.Status}}' 2>/dev/null | grep -v '^$$' || true
	@curl -s localhost:8600/state | python3 -c 'import json,sys; s=json.load(sys.stdin); print("core healthy:", s.get("healthy"), "| risk:", s.get("risk"), "| platform:", s.get("platform"))' 2>/dev/null || echo "core not reachable"

episodes: ## Record dataset episodes: make episodes N=30 [SEED=2026] (platform in MODE=none, CHAOS=1)
	cd control && PYTHONPATH=. $(NOSLEEP) $(PY) -m chaos.episode_runner --n $(or $(N),1) --seed $(or $(SEED),2026)

episodes-plan: ## Print the next N episode plans without running them
	cd control && PYTHONPATH=. $(PY) -m chaos.episode_runner --n $(or $(N),60) --seed $(or $(SEED),2026) --dry-run

dataset: ## Build control/data/train.parquet from valid episodes, then plot label checks
	cd control && PYTHONPATH=. $(PY) -m experiments.build_dataset
	cd control && PYTHONPATH=. $(PY) -m experiments.plot_labels

train: ## Train, calibrate and evaluate models; activates rf_v1 (results/model_results.md)
	cd control && PYTHONPATH=. $(PY) -m experiments.train

m3-check: ## M3: breaker opens before p95 > SLO on exam_ramp (platform cascadeshield, core live)
	cd control && PYTHONPATH=. $(NOSLEEP) $(PY) -m experiments.m3_check --runs $(or $(RUNS),5) --scenario $(or $(SCENARIO),exam_ramp)

matrix: ## Comparison runs: make matrix [RUNS=3] [VARIANTS=none,reactive,cascadeshield] [RESTART=local|manual]
	cd control && PYTHONPATH=. $(NOSLEEP) $(PY) -m experiments.run_matrix --runs $(or $(RUNS),3) \
		--variants $(or $(VARIANTS),none,reactive,cascadeshield) --restart $(or $(RESTART),local)

figures: ## Chapter figures into docs/figures (latest matrix results)
	cd control && PYTHONPATH=. $(PY) -m experiments.figures all

screenshot: ## Dashboard screenshot via headless Chrome: make screenshot SHOT=healthy|contained
	cd control && PYTHONPATH=. $(PY) -m experiments.figures screenshot $(or $(SHOT),healthy)
