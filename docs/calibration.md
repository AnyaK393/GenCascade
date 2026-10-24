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

## Phase 3 measurements (Mac, 2026-10-16, real Ollama, `make platform-exam`)

Load: 30 tutor loops with no think time (harsher than Locust's 8-20 s waits) plus quiz submits
at 5 per second for 40 s, exam mode on DSA101 with floor 1.

| Measurement | Result | Target |
| --- | --- | --- |
| Pre-warm, 10 DSA101 topics (100 level-0 answers, one at a time) | 270-303 s (two runs) | < 10 min before the exam |
| Quiz submit p95 / p50 during the exam | 95-271 ms / 11-12 ms (200/200 committed, two runs) | < 500 ms |
| AIMD admission limit | 4 -> 7, then steady | |
| Tutor requests shed to level 4 | 302 of 343 and 320 of 364 (no think time, so most are retries of a full limiter) | |
| Exam cache hit rate on Locust's question bank | 0% vetted only (nothing vetted yet); 53% if all were vetted | > 40% |
| Banner, server side | 76-100 ms + the page's 3 s poll | < 3 s |
| Solution chunks served to the exam course | 0 of 10 probes | 0 |

Tuned values (first pass, to revisit in the joint load test):

| Setting | Value | Where it is used |
| --- | --- | --- |
| `ADMISSION_START` / `ADMISSION_MAX` | 4 / 16 | gateway AIMD limit during an exam |
| `ADMISSION_TARGET_S` | 8 s | +1 every 5 s while gateway tutor p95 is under it |
| `ADMISSION_WAIT_S` | 3 s | then the request is shed to level 4 |
| AIMD decrease | halve on an LLM timeout, at most once per 2 s, min 1 | |
| `LLM_TIMEOUT_S`, `MAX_QUEUE` | unchanged (20 s, 40) | |

### Re-run with the vetted cache (2026-10-25, `make platform-exam`, real Ollama)

All 300 seed answers vetted (150 topic FAQs plus the 5 `_common` questions per topic). The RAG
lookup now picks the best match among vetted entries only; before, a closer unvetted entry hid a
vetted one, which gave 22% even with the topic FAQs vetted. **11/11 checks pass.**

| Measurement | Result | Target |
| --- | --- | --- |
| Pre-warm, 10 DSA101 topics | 0 s: all 100 answers come from the vetted seed, none generated | < 10 min |
| Exam cache hit rate, vetted only | **80%** | > 40% |
| Quiz submit p95 / p50 during the exam | 102 ms / 13 ms, 200/200 committed | < 500 ms |
| Solution chunks served to the exam course | 0 of 10 probes | 0 |
| Banner, server side | 12 ms + the page's 3 s poll | < 3 s |

Run with the control room stopped: a run with a leftover control room and other apps open on the
same Mac gave a quiz p95 of 28.7 s, from the whole Docker VM stalling, not from the quiz path.

## Run 2: 2026-10-23 (Clean Hardware Baseline)

Apple MacBook Air (M-series), `qwen2.5:0.5b` on native Ollama (Metal). Tested with clean background conditions (all apps closed, plugged in).

| Concurrency | Requests | p50 (s) | p95 (s) | tok/s per request | tok/s total | prompt tok | output tok |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 30 | 4.92 | 6.24 | 39.7 | 38.1 | 70 | 199 |
| 2 | 8 | 6.32 | 6.33 | 32.7 | 63.7 | 70 | 200 |
| 4 | 16 | 12.32 | 12.80 | 32.8 | 64.5 | 70 | 200 |
| 8 | 32 | 25.10 | 26.04 | 32.2 | 63.4 | 70 | 200 |

- Unloaded p95: **6.24 s**; unloaded tokens/s per request: **39.7**
- Knee (first concurrency with p95 > 3x unloaded p95): **8**
- Proposed `llm_inference` SLO: Confirmed at **16 s** (aligned with trained model).

