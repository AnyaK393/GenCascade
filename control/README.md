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

SELinux (Fedora only): the platform mounts `platform/data` into its containers. Relabel it once with
`chcon -R -t container_file_t platform/data`, or RAG and student fail with "Permission denied".

## Daily use (all from the repo root)

```bash
make platform-mock-up           # the Mac's platform here: mock LLM, chaos on, MODE=none (MODE=... to change)
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
| `chaos/episode_runner.py`, `chaos/episodes.yaml` | Phase 2 episode runner and its parameter space |
| `experiments/` | `labels.py`, `build_dataset.py`, `plot_labels.py`; Phase 3-4 training and analysis |
| `models/` | Phase 3 |
| `tests/` | `make test` |

## Settings

From the root `.env`, with control-only overrides (defaults in `resilience_core/settings.py`):
`PROMETHEUS_URL`, `CORE_URL`, `REDIS_HOST` (defaults to `PLATFORM_HOST`), `CS_LOOP_S`,
`CS_SLO_<SERVICE>` for p95 SLOs in seconds (defaults from `docs/calibration.md`, LLM 16 s; see
`contracts/features.md`), and `CS_TOKENS_PER_S_BASELINE` (42.1).

## Phase 1 status (M1)

Verified against the original stand-in platform (since removed): all 5 targets UP, contracts pass, an 80-user ramp pushes LLM p95
over the SLO in ~20 s, the threshold rule opens the breaker (L3) in one cycle, recovers through
half-open (L1) to closed, and stopping the core makes the platform log a failsafe switch.

Known limit: under sustained overload the latency-only threshold rule cycles open -> half-open
-> closed -> open (about every 2 min), because a lean trickle of probes looks healthy. That is
what Phase 3's load-aware predictor and one-step-at-a-time containment engine replace.

## Phase 2: dataset (M2)

```bash
make platform-mock-up             # or point PLATFORM_HOST at the Mac running MODE=none CHAOS=1
make prom-up                      # Prometheus only; keep the resilience core stopped
make episodes-plan N=60           # what will run (60/25/15 fail/safe/fault-only, ~10 h)
make episodes N=30                # one overnight run; continues numbering, so run it twice
make dataset                      # data/train.parquet, data/dataset_summary.txt, results/label_check/*.png
```

Each episode: `/admin/reset` + `/chaos/clear` + student reset, 20 s settle, a 90-150 s lead-in at
light load, the seeded Locust shape, an optional fault fired on schedule, then a 2 s `query_range`
export of every signal in `resilience_core/signals.py` into `data/episodes/<id>/series.parquet`
with `meta.json` (all parameters, seed, fault log, onsets). An episode is marked invalid if a
service restarted or a scrape gap exceeds 10 s; `build_dataset` skips it.
Label and feature definitions: `contracts/features.md`.
