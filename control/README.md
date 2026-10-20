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
| `resilience_core/` | `main.py` loop, `collector.py`, `signals.py`, `features.py`, `model.py`, `predictor.py`, `dependency_graph.py`, `containment_engine.py`, `calendar.py`, `actuator.py`, `risk.py`, `settings.py` |
| `dashboard/app.py` | Streamlit; reads only the core's `/state` and Redis |
| `chaos/episode_runner.py`, `chaos/episodes.yaml` | Phase 2 episode runner and its parameter space |
| `experiments/` | `labels.py`, `build_dataset.py`, `plot_labels.py`, `evaluate.py`, `train.py`, `m3_check.py` |
| `data/exam_calendar.yaml` | Exams the control room prepares for |
| `models/` | `<name>.joblib` (git-ignored) + `<name>.json`; `metadata.json` names the active model |
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

## Phase 3: prediction and containment (M3)

```bash
make dataset && make train        # results/model_results.md, results/reliability.png, models/rf_v1.*
make platform-mock-up MODE=cascadeshield
make control-up                   # core loads models/metadata.json; dashboard on :8501
make m3-check                     # 5 x exam_ramp: breaker opens before p95 > SLO? (needs 4 of 5)
```

Each 2 s cycle the core reads the last 80 s of every signal, builds the same features as training,
and predicts per service (`llm_inference`, `orchestrator`, `gateway`; RAG and student keep the
p95 ÷ SLO risk). Cascade risk combines them over the dependency graph; the containment engine
acts on the LLM's cascade risk through the control API, with the reason, risk and SHAP factors.

- **Training** (`experiments/train.py`): split by episode (20 % held out per category), GroupKFold
  out-of-fold scores for isotonic calibration and the threshold (lowest with ≤ 1 false alarm per
  hour), logistic regression / random forest / XGBoost compared with the Phase 1 threshold rule,
  an unseen-fault test (no `leak` in training), and a time-to-failure regressor. Saved models are
  refitted on every episode; their metadata carries the holdout numbers.
- **Predictor**: refuses to start if feature columns differ from the model's; SHAP top-3 factors in
  plain words go to `cs:explain:<service>`. No model trained yet: the core falls back to the threshold risk.
- **Dependency graph weights** (`dependency_graph.py`): 0.9 for synchronous calls with no fallback
  (gateway → orchestrator, orchestrator → LLM), 0.6 for a synchronous call with a degraded fallback
  (orchestrator → RAG), 0.3 for a default fallback or isolated pool (→ student). The blast radius is
  the set of services pushed over 0.5 by the riskiest node.
- **Containment engine** (`containment_engine.py`): lean at R ≥ 0.6 for 6 s; breaker open + L2 at
  R ≥ threshold for 4 s; L3 if still rising 30 s later; L4 if admission is at its minimum and the
  queue grows; one step down per 30 s of R < 0.5 (2/open → 1/half-open → 1/closed → 0). At most one
  change per 10 s, except opening the breaker.
- **Operator controls** (dashboard sidebar → core `/ops/*`, token required): controller
  (`predictive` | `threshold` | `reactive`), dry run (log only), approval mode (Approve / Reject),
  dependency graph on/off (ablation), kill switch (stops actions and drops the heartbeat at once,
  so the platform's failsafe takes over), "Schedule exam in 2 minutes", reload model.
- **Exam calendar** (`calendar.py`, `data/exam_calendar.yaml`): pre-warm 10 min before, exam mode
  at the start (floor 1 if expected students exceed `CS_CAPACITY_USERS`, default 5), off at the end.
