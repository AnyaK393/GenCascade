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
make platform-up CHAOS=1        # chaos hooks on (overnight dataset runs)
make calibrate                  # Ollama baseline -> docs/calibration_run.md
make platform-ladder            # Phase 2: levels 0-4, breaker, shed queue, failsafe
make platform-up MODE=reactive CHAOS=1 BACKEND=mock && make platform-breaker   # local breaker + chaos
make seed-cache                 # answer data/faq.yaml at level 0 -> data/cache_seed.yaml
make seed-cache LOAD=1          # reload the file after marking answers vetted: true
make platform-exam              # Phase 3: pre-warm, exam floor, integrity, hit rate, quiz p95, banner
make fairness                   # share of degraded answers per course
make platform-ps / platform-logs / platform-down
make demo                       # Phase 4: scripts/demo.sh (also demo-mock, demo-single, demo-prepare, demo-stop)
```

Demo runbook, viva script, rehearsal log and troubleshooting: `../docs/demo.md`.

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
| `data/` | `curriculum/<COURSE>/<topic>.md` (3 x 10), `hints.yaml`, `faq.yaml` (5 per topic), `cache_seed.yaml`, `seed.py` (mounted read-only, no rebuild needed) |
| `tools/` | `calibrate.py`, `smoke.py` (standard library only), `quiz_under_load.py` (guide 5.4), `ladder_check.py`, `breaker_check.py`, `seed_cache.py`, `exam_check.py`, `fairness.py` |
| `web/index.html` | student page: course picker, tutor chat with source tags, 5-question quiz, banner polling `/api/status` every 3 s |

## Internal routes (not in the contracts)

`orchestrator POST /tutor/ask`, `student GET /profile/{id}`, `student POST /submissions`,
`student POST /admin/reset` (wipes submissions), `rag POST /search`, `rag POST /cache/get`,
`rag POST /cache/put`, `rag POST /cache/reload`, `rag GET /topics`, `llm POST /generate`,
`orchestrator GET /tutor/queued/{id}`, `orchestrator POST /admin/answer` (forced level 0/1, for seeding),
`llm|rag POST /admin/reset`, `llm|rag GET /chaos/state`.

Public addition: `GET /api/tutor/queued/{queue_id}` returns `{"status":"queued","position":n}` or
`{"status":"answered","answer",...}`. A level 4 answer carries `queue_id` and `position`.

Control API additions: `POST /control/exam` also takes `floor` (0-4, minimum level for everyone);
`POST /control/prewarm` returns 202 and runs in the background, `GET /control/prewarm` shows progress;
`/control/mode` and `/control/breaker` also take `risk` and `factors` (logged to `cs:actions`);
`/control/state` adds `admission_limit`, `shed_queue` and `prewarm`. `GET /api/status` adds `exam`.
`cs_orch_responses_total` carries a `course` label (guide 6.5).

Mac-only Redis keys: `cs:admission:limit` (gateway AIMD limit, TTL 30 s), `cs:shed:<course>` (list of queue ids, TTL 6 h, capped at 500) and
`cs:shed:q:<id>` (hash: question, status, answer; TTL 6 h).

## Control behaviour

- `none`: ignores Redis control keys, no breaker, LLM queue cap 1000.
- `reactive`: local breaker only (5 LLM failures in 10 s -> open; 20 s -> half-open, 10% probes;
  5 good probes -> closed, 1 failure -> open). Open serves static hints.
- `cascadeshield`: follows `cs:mode:level` and `cs:breaker:llm` while `cs:control:heartbeat` is
  under 10 s old, taking the safer of Fedora's and the local breaker's decision. A stale heartbeat
  falls back to the local breaker and logs `actor=failsafe` to `cs:actions`.
- Effective level = max(Fedora's level, local level, exam floor); an open breaker forces level >= 2.
- 0 full and 1 lean use the LLM (256 or 80 tokens, 3 or 1 chunks). If that call fails the answer
  degrades to level 2 instead of erroring (except in `none` mode, which returns 504).
- 2: semantic cache hit (cosine >= 0.75), else the best non-solution passage plus a guiding question.
- 3: hint for the detected topic. 4: question queued per course with its position, plus a hint; a
  background task answers the queue one at a time (courses take turns) once the level is 0-1 and
  the breaker closed, and caches the answer. Levels 2-4 never call the LLM; RAG down -> level 3.
- Chaos (`CHAOS_ENABLED=1`, token required): LLM latency is added inside the generation slot; the
  leak stops at 120 MB or 140 MB resident, below the 160 MB limit; `/admin/reset` clears it all.

## Exam mode (Phase 3)

- `POST /control/exam {"active":true,"course":"DSA101","ends_at":"<ISO>","floor":1}` writes
  `cs:mode:exam` with an expiry at `ends_at`. It applies in `reactive` and `cascadeshield`, even with
  a stale heartbeat (the exam is still on if Fedora dies); `none` ignores it. `/admin/reset` ends it.
- Floor: effective level = max(Fedora, local, floor) for every course.
- Integrity, for the exam's course only: no `solution` chunks anywhere (LLM context, level 2) and
  only `vetted` cache entries.
- Gateway admission (P1 tutoring only; P0 quiz submits never wait): AIMD limit starting at 4, +1
  every 5 s while tutor p95 < `ADMISSION_TARGET_S` (8 s), halved on an LLM timeout (once per 2 s),
  max 16. Over the limit for 3 s -> level 4 (queued) and `cs_shed_requests_total{priority="P1"}`.
- Pre-warm: each topic's `faq.yaml` questions plus the `_common` templates. Vetted answers from
  `cache_seed.yaml` are loaded without the LLM; the rest are generated one at a time at level 0
  (with the integrity filter) and stored unvetted, so the exam can only serve the vetted ones.
  It pauses while the level is above 1 or the breaker is not closed.
