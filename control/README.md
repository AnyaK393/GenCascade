# Control room (Fedora)

Everything that watches the platform, predicts failure, decides what to do and shows it.
The control room only **advises**: it reads metrics, writes Redis keys / calls the control
API, and writes `cs:control:heartbeat` every 2 s. It writes the heartbeat only on cycles with
fresh telemetry, so if Prometheus or the core dies the Mac's local breaker takes over.

## Setup (once)

```bash
cp .env.example .env            # at the repo root; set CS_TOKEN and REDIS_PASSWORD
make control-setup              # uv sync -> control/.venv (Python 3.12)
```

Containers run through `docker compose` (on this laptop podman-compose emulates it; both work).

## Daily use (all from the repo root)

```bash
make platform-mock-up           # local Redis + 5 mock services on :8000-8004
make check                      # every contract metric present?
make control-up                 # Prometheus :9090, core :8600, dashboard :8501
make load SCENARIO=exam_ramp    # headless Locust -> control/results/
make control-status             # what's running + latest core state
make control-down platform-mock-down
```

Pointing at the real Mac: set `PLATFORM_HOST=<mac ip>` in `.env`, then `make prom-targets`
(Prometheus picks up the new targets without a restart) and restart the core.

## Layout

| Path | What |
| --- | --- |
| `prometheus/` | `prometheus.yml`, recording rules, `render_targets.py` (file_sd from `PLATFORM_HOST`) |
| `chaos/` | `locustfile.py`, `questions.py` (300-question bank), `scenarios/*.yaml` |
| `resilience_core/` | `main.py` loop, `collector.py`, `risk.py`, `containment.py`, `actuator.py`, `settings.py` |
| `dashboard/app.py` | Streamlit; reads only the core's `/state` and Redis |
| `mock_platform/` | Stand-in for the Mac's services for local dev; delete once the real platform runs here with `LLM_BACKEND=mock` |
| `experiments/`, `models/` | Phase 2-4 |
| `tests/` | `make test` |

## Settings

From the root `.env`, with control-only overrides (defaults in `resilience_core/settings.py`):
`PROMETHEUS_URL`, `CORE_URL`, `REDIS_HOST` (defaults to `PLATFORM_HOST`), `CS_LOOP_S`,
and `CS_SLO_<SERVICE>` for p95 SLOs in seconds (placeholders until `docs/calibration.md` exists).

Mock platform knobs: `MOCK_LLM_SLOTS` (4), `MOCK_LLM_TPS` (160 aggregate tokens/s),
`MOCK_LLM_TIMEOUT_S` (30), `PROTECTION_MODE` (`cascadeshield` | `reactive` | `none`), `CHAOS_ENABLED` (1).

## Phase 1 status (M1)

Working against the mock: all 5 targets UP, contracts pass, an 80-user ramp pushes LLM p95
over the SLO in ~20 s, the threshold rule opens the breaker (L3) in one cycle, recovers through
half-open (L1) to closed, and stopping the core makes the platform log a failsafe switch.

Known limit: under sustained overload the latency-only threshold rule cycles open -> half-open
-> closed -> open (about every 2 min), because a lean trickle of probes looks healthy. That is
what Phase 3's load-aware predictor and one-step-at-a-time containment engine replace.
