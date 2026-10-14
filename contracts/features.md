# Failure label and features (owner: Fedora)

Status: **draft** — finalised in Phase 2 (Weeks 3–4). The SLO values come from `docs/calibration.md`.

## Failure label

- **Failed state** of `llm_inference` at time t: `cs:latency_p95:15s > SLO` held for ≥ 20 s,
  **or** `cs:error_rate:15s > 0.05` for ≥ 20 s, **or** `cs_llm_queue_depth > 30`.
- **Onset**: the first timestamp where the failed state begins.
- **Label** `y(t) = 1` if an onset happens in `(t, t + 90 s]`, else 0.
- **Excluded**: rows already inside a failed state.
- The same definition applies to `orchestrator` and `gateway` with their own latency SLO.

## Features

To be written in Phase 2: exact column list, units and window sizes.
The column order is saved with every model in `control/models/metadata.json`.
