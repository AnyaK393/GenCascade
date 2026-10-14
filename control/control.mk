# Fedora control-room targets, included from the root Makefile. Run from the repo root.
UV       ?= uv
COMPOSE  ?= docker compose
SCENARIO ?= exam_ramp
PY       := .venv/bin/python
RUN_DIR  := .run
export CS_CONTROL_DIR := $(CURDIR)/control

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

.PHONY: control-setup prom-targets prom-up control-up control-down platform-mock-up platform-mock-down \
	check core dashboard mock load locust-ui test control-logs control-status

control-setup: ## Install control-room Python deps with uv
	cd control && $(UV) sync

prom-targets: ## Point Prometheus at PLATFORM_HOST (no restart needed)
	@cd control && PYTHONPATH=. $(PY) prometheus/render_targets.py

prom-up: prom-targets ## Start Prometheus (compose profile "control")
	$(COMPOSE) --profile control up -d

control-up: prom-up ## Start Prometheus, resilience core and dashboard in the background
	$(call bg,core,$(PY) -m resilience_core.main)
	$(call bg,dashboard,$(PY) -m streamlit run dashboard/app.py --server.headless true --server.port 8501)
	@echo "dashboard http://localhost:8501  core http://localhost:8600/state  prometheus http://localhost:9090"

control-down: ## Stop the core, dashboard and Prometheus
	$(call stop,dashboard)
	$(call stop,core)
	$(COMPOSE) --profile control down

platform-mock-up: ## Start the local mock platform (Redis container + 5 mock services)
	$(COMPOSE) --profile mock up -d
	$(call bg,mock,$(PY) -m mock_platform.run_all)

platform-mock-down: ## Stop the mock platform
	$(call stop,mock)
	$(COMPOSE) --profile mock down

check: ## Check the platform exposes every contract metric
	python3 scripts/check_contracts.py

core: ## Run the resilience core in the foreground
	cd control && PYTHONPATH=. $(PY) -m resilience_core.main

dashboard: ## Run the dashboard in the foreground
	cd control && PYTHONPATH=. $(PY) -m streamlit run dashboard/app.py

mock: ## Run the mock platform services in the foreground
	cd control && PYTHONPATH=. $(PY) -m mock_platform.run_all

load: ## Headless Locust run: make load SCENARIO=exam_ramp
	@mkdir -p control/results
	cd control && RUN=$(SCENARIO)-$$(date +%Y%m%d-%H%M%S) && \
		PYTHONPATH=. CS_SCENARIO=$(SCENARIO) $(PY) -m locust -f chaos/locustfile.py --headless \
		--csv results/$$RUN --html results/$$RUN.html --only-summary

locust-ui: ## Locust web UI on :8089
	cd control && PYTHONPATH=. CS_SCENARIO=$(SCENARIO) $(PY) -m locust -f chaos/locustfile.py

test: ## Run control-room tests
	cd control && $(UV) run pytest -q

control-logs: ## Tail control-room logs
	tail -n 30 -f control/$(RUN_DIR)/*.log

control-status: ## Show what is running and the core's latest state
	@for f in control/$(RUN_DIR)/*.pid; do [ -f $$f ] && n=$$(basename $$f .pid) && \
		(kill -0 $$(cat $$f) 2>/dev/null && echo "up    $$n" || echo "dead  $$n"); done; true
	@curl -s localhost:8600/state | python3 -c 'import json,sys; s=json.load(sys.stdin); print("core healthy:", s.get("healthy"), "| risk:", s.get("risk"), "| platform:", s.get("platform"))' 2>/dev/null || echo "core not reachable"
