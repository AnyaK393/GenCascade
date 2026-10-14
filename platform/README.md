# Platform (Mac)

The campus GenAI tutoring platform: five FastAPI services, Redis and native Ollama.
Contracts live in `../contracts/`; nothing here may change them without Fedora's review.

## Run

```bash
cp .env.example .env            # set PLATFORM_HOST to the Mac's IP, LLM_BACKEND=ollama
make platform-up                # build + start, waits for every health check
make platform-smoke             # health, tutor answer, idempotent quiz submit, banner
make platform-up MODE=reactive  # PROTECTION_MODE: none | reactive | cascadeshield
make platform-up BACKEND=mock   # no Ollama needed (simulator calibrated on the M1)
make calibrate                  # Ollama baseline -> docs/calibration_run.md
make platform-ps / platform-logs / platform-down
```

Ollama (native, once):

```bash
launchctl setenv OLLAMA_NUM_PARALLEL 2
launchctl setenv OLLAMA_KEEP_ALIVE -1
launchctl setenv OLLAMA_CONTEXT_LENGTH 2048
launchctl setenv OLLAMA_MAX_LOADED_MODELS 1   # then quit and reopen the Ollama app
ollama pull qwen2.5:0.5b
```

## Layout

| Path | What |
| --- | --- |
| `cs_common/` | settings, JSON logging with `X-Request-ID`, contract metrics middleware, Redis helpers |
| `services/gateway` | :8000 public API, student page, sessions, rate limit, quiz path to student (own pool) |
| `services/student` | :8001 SQLite (WAL) profiles and idempotent submissions, `/admin/stats` |
| `services/orchestrator` | :8002 Socratic tutor, control API, local breaker and heartbeat failsafe |
| `services/rag` | :8003 TF-IDF search and semantic cache; never calls the LLM |
| `services/llm_inference` | :8004 Ollama client, slot semaphore, token telemetry, `LLM_BACKEND=mock` |
| `mock_llm/` | queueing simulator with the M1's measured 41 tok/s shared across slots |
| `data/` | `curriculum/<COURSE>/<topic>.md` (3 x 10), `hints.yaml`, `seed.py` |
| `tools/` | `calibrate.py`, `smoke.py` (standard library only), `quiz_under_load.py` (guide 5.4 test) |

## Internal routes (not in the contracts)

`orchestrator POST /tutor/ask`, `student GET /profile/{id}`, `student POST /submissions`,
`student POST /admin/reset` (wipes submissions), `rag POST /search`, `rag POST /cache/get`,
`rag POST /cache/put`, `rag GET /topics`, `llm POST /generate`.

## Control behaviour

- `none`: ignores Redis control keys, no breaker, LLM queue cap 1000.
- `reactive`: local breaker only (5 LLM failures in 10 s -> open; 20 s -> half-open, 10% probes;
  5 good probes -> closed, 1 failure -> open). Open serves static hints.
- `cascadeshield`: follows `cs:mode:level` and `cs:breaker:llm` while `cs:control:heartbeat` is
  under 10 s old, taking the safer of Fedora's and the local breaker's decision. A stale heartbeat
  falls back to the local breaker and logs `actor=failsafe` to `cs:actions`.
- Phase 1 ladder: levels 0 and 1 use the LLM (256 or 80 tokens, 3 or 1 chunks); any level >= 2
  serves a level-3 hint. Phase 2 adds the cache + RAG (2) and shed (4) paths.
