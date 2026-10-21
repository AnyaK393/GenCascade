# Failure label and features (owner: Fedora)

Status: **Phase 2, for Mac review.** Code: `control/experiments/labels.py`,
`control/resilience_core/features.py`, signals in `control/resilience_core/signals.py`.
All series come from Prometheus at a **2 s step**; SLOs from `docs/calibration.md`.

## SLOs (p95 latency)

| Service | SLO | Why |
| --- | --- | --- |
| `llm_inference` | 16 s | 3 x unloaded p95 (5.36 s), calibration run 1 |
| `orchestrator` | 18 s | the LLM call plus its own hops: LLM SLO + 2 s |
| `gateway` | 18 s | same tutor path as the orchestrator |
| `curriculum_rag` | 1 s | = the orchestrator's RAG timeout |
| `student` | 0.3 s | = the orchestrator's profile timeout |

Override on Fedora with `CS_SLO_<SERVICE>`; a change here means relabelling the dataset.

## Failure label

Labelled services: `llm_inference`, `orchestrator`, `gateway`.

- **Failed state** at t: `cs:latency_p95:15s > SLO` held for ≥ 20 s, **or** `cs:error_rate:15s > 0.05`
  held for ≥ 20 s, **or** (`llm_inference` only) `cs_llm_queue_depth > 30`.
  "Held for ≥ 20 s" means a run of consecutive samples spanning at least 20 s; the whole run is failed.
  A p95 missing because no request finished is carried forward for up to 14 s (one rate window), then 0.
- Failed runs separated by less than 20 s are merged, so one stall with a brief dip counts once.
- **Onset**: the first timestamp of a failed run. A run already under way at the episode's first
  sample has no observed onset.
- **Label** `y(t) = 1` if an onset falls in `(t, t + 90 s]`, else 0.
- **Excluded rows**: inside a failed state; in the first 60 s of an episode (incomplete windows);
  and rows whose 90 s look-ahead runs past the end of the episode without an onset (unknown outcome).
- Also stored: `time_to_onset_s` (seconds to the next onset, NaN if none), for the optional time-to-failure model.

## Features

One row per (t, labelled service). 64 columns, in this order (the order is saved with every model
in `control/models/metadata.json`; the live predictor refuses to run on a mismatch).

| Group | Columns | Unit / definition |
| --- | --- | --- |
| Instant (own service) | `p95_s`, `error_rate`, `rps`, `inflight`, `rss_bytes`, `cpu_rate` | s; fraction; req/s; requests; bytes; CPU s/s. Rates over 15 s |
| LLM (from `llm_inference`) | `llm_queue_depth`, `llm_queue_wait_p95_s`, `llm_tokens_per_s`, `llm_prompt_tokens_p95`, `llm_timeout_rate` | requests; s; tokens/s (10 s average); tokens; timeouts/s |
| Trend | `<x>_mean30`, `_std30`, `_mean60`, `_std60`, `_delta30`, `_slope60` for x in `p95_s`, `rps`, `inflight`, `rss_bytes`, `llm_queue_depth`, `llm_tokens_per_s`, `llm_queue_wait_p95_s` | rolling over 30 s (15 rows) / 60 s (30 rows); delta = x(t) − x(t − 30 s); slope = least-squares per second over 60 s |
| Velocity and ratios | `error_rate_velocity`, `tokens_ratio`, `p95_slo_ratio`, `queue_growth_per_s` | (err(t) − err(t − 10 s)) / 10; tokens/s ÷ 42.1 (calibrated baseline); p95 ÷ own SLO; queue Δ30 / 30 |
| Graph | `downstream_pressure` | max over the service's synchronous dependencies of their p95 ÷ SLO (gateway → orchestrator, student; orchestrator → llm_inference, curriculum_rag, student; llm_inference → none: 0) |
| Context | `sessions_active`, `exam_active`, `degradation_level` | gateway's 60 s session count; 1 while `cs:mode:exam` is active; orchestrator's level 0–4 |
| Service | `svc_llm_inference`, `svc_orchestrator`, `svc_gateway` | one-hot, so one model can score all three services |

Missing values: latency-like signals (`p95_s`, queue wait, prompt tokens, tokens/s) are carried
forward for up to 14 s, then 0; every other missing value is 0.
Exception: `tokens_per_s` that is 0 or still missing after that means nothing was generated recently
(e.g. a freshly started platform); it is set to the calibrated baseline (42.1) so that "no data" never
reads as "extremely slow". Found live: an idle, just-restarted platform scored 0.65 risk without it.

### Deviation from the guide (5.3)

The guide's graph feature is "max risk among downstream dependencies from the previous cycle".
That risk does not exist when building training data from recorded episodes, and feeding a model
its own earlier output makes training and live inference differ. `downstream_pressure` uses the
dependencies' measured p95 ÷ SLO instead; cascade risk over the graph is still computed from model
outputs in Phase 3 (guide 6.4).

### Known limit

Dataset episodes run with `PROTECTION_MODE=none`, so `degradation_level` and the breaker are always
0 in training. Live, under `cascadeshield`, level changes alter the load the LLM sees. Phase 3
reports how predictions behave once containment acts.
