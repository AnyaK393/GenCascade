# Calibration (Mac, owner: Mac developer)

Baseline for every threshold in the project (guide 3.2). Re-run with `make calibrate`
(writes `docs/calibration_run.md`), then copy the table here.

## Run 1: 2026-10-14 (provisional)

Apple M1, 8 GB, `qwen2.5:0.5b` on native Ollama (Metal). Tutor-style prompts of about 70 prompt
tokens and 200 output tokens. **Provisional:** other apps were open and `OLLAMA_NUM_PARALLEL`
was not set yet. Re-run after the Phase 0 Ollama settings are applied.

| Concurrency | Requests | p50 (s) | p95 (s) | tok/s per request | tok/s total | prompt tok | output tok |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 30 | 4.84 | 5.36 | 42.1 | 40.8 | 70 | 200 |
| 2 | 8 | 9.65 | 10.54 | 41.3 | 40.5 | 70 | 200 |
| 4 | 16 | 19.23 | 19.89 | 42.0 | 41.3 | 70 | 200 |
| 8 | 32 | 37.74 | 38.78 | 42.6 | 41.8 | 70 | 198 |

- Unloaded p95: **5.36 s**; unloaded tokens/s per request: **42.1**
- Knee (first concurrency with p95 > 3x unloaded p95): **4**
- Proposed `llm_inference` SLO (3x unloaded p95): **16.1 s**

### What it means

- Aggregate throughput is flat at about **41 tok/s** at every concurrency level, so Ollama was
  serving one generation at a time and latency grows linearly with load.
  The mock LLM (`platform/mock_llm/sim.py`) models exactly this: a shared 41 tok/s.
- Real capacity is about **2 concurrent tutor requests**. At 4, p95 already exceeds 3x the
  unloaded p95.

## Proposed values (to agree with Fedora)

| Setting | Value | Where it is used |
| --- | --- | --- |
| `llm_inference` p95 SLO | **16 s** (3 x 5.36 s) | Fedora: `CS_SLO_LLM_INFERENCE`, failure labels |
| `LLM_TIMEOUT_S` | 20 s | Mac: per-generation timeout, > SLO |
| `MAX_INFLIGHT` | 2 | Mac: = `OLLAMA_NUM_PARALLEL` |
| `MAX_QUEUE` | 40 (1000 in `none` mode) | Mac: 503 beyond it |
| `MOCK_TOKENS_PER_S` | 41 (aggregate) | Mac and Fedora: mock backend |

Tuned values from the Phase 3 load tests go below.
