# CascadeShield Build Guide — Mac Developer (Platform)

Oct 14, 2026 · @Anushka

## 1. Your role and the system

You build and own **the campus GenAI platform**: the system under stress. It runs on the M1 Mac (8 GB). Your partner on Fedora builds **the CascadeShield control room** that watches your platform, predicts failure and tells it to degrade. Neither half works alone, so both of you move through the same five phases and meet at a shared milestone at the end of each.

**What runs on the Mac**

- **Ollama** (native, Metal GPU) serving `qwen2.5:0.5b`, the real bottleneck.
- **Five FastAPI services** in Docker: `gateway_service`, `student_service`, `orchestrator_service`, `curriculum_rag_service`, `llm_inference_service`.
- **Redis**: breaker state, degradation level, semantic cache, rate limits.
- **SQLite** (inside `student_service`, on a Docker volume): durable quiz submissions.
- **A small student web page** served by the gateway: tutor chat, quiz submit, status banner.

**What runs on Fedora (your partner)**: Prometheus, Locust load generator, the resilience core (predictor, dependency graph, containment engine), the Streamlit dashboard, dataset generation and model training.

**The one rule that shapes your code:** the platform must stay correct even if the control room disappears. Fedora only *advises* through Redis keys and the control API. If its heartbeat goes stale, your orchestrator falls back to its own local reactive breaker.

**Your deliverables**

| Deliverable | Phase |
| --- | --- |
| Shared library `cs_common` (metrics, logging, Redis, settings) | 1 |
| Five services + Compose `platform` profile | 1 |
| Ollama client with real token telemetry, plus a mock backend | 1 |
| Degradation ladder L0–L4, breaker with hysteresis, heartbeat failsafe | 2 |
| Idempotent quiz path that never touches the LLM | 2 |
| Chaos hooks for fault injection | 2 |
| Exam mode, priority admission, adaptive concurrency, pre-warm | 3 |
| Student web page with status banner | 3 |
| `demo.sh`, mock switch, backup video, viva readiness | 4 |

&#91;embedded content: two-machine architecture · 5 services, 4 control-room parts\]

Load from Locust enters through the gateway; quiz submits go straight to the student service, while tutoring flows through the orchestrator to the single Ollama bottleneck. The control room only reads metrics and writes advice into Redis and the control API.

## 2. Shared contracts (identical in both guides)

These contracts let you work apart and still plug together. Agree on them in the first three days, commit them to `contracts/`, and change them only through a pull request both of you approve.

### 2.1 Repository layout

```
cascadeshield/
├── contracts/            metrics.md, redis_keys.md, control_api.md, features.md
├── docker-compose.yml    profiles: platform (Mac), control (Fedora)
├── .env.example          PLATFORM_HOST, CONTROL_HOST, CS_TOKEN, REDIS_PASSWORD, LLM_BACKEND
├── platform/             owned by Mac
│   ├── cs_common/        metrics middleware, logging, redis client, settings
│   ├── services/         gateway, student, orchestrator, rag, llm_inference
│   ├── mock_llm/         queueing simulator used when LLM_BACKEND=mock
│   ├── web/              student page (HTML + JS)
│   └── data/             curriculum/*.md, hints.yaml, faq.yaml
├── control/              owned by Fedora
│   ├── prometheus/       prometheus.yml, rules.yml
│   ├── chaos/            locustfile.py, scenarios/*.yaml, episode_runner.py
│   ├── resilience_core/  collector, features, predictor, graph, containment
│   ├── dashboard/        app.py
│   ├── experiments/      run_matrix.py, analysis notebooks
│   └── models/           *.joblib + metadata.json
├── scripts/              demo.sh, check_contracts.py
└── docs/                 calibration.md, results.md, figures/
```

Branches: `main` is protected; work on `mac/<feature>` or `fedora/<feature>`; the other person reviews every PR that touches `contracts/` or `docker-compose.yml`.

### 2.2 Ports

| Component | Host | Port | Notes |
| --- | --- | --- | --- |
| gateway\_service | Mac | 8000 | Public API, student web page, `/metrics` |
| student\_service | Mac | 8001 | `/metrics` |
| orchestrator\_service | Mac | 8002 | `/metrics`, `/control/*` |
| curriculum\_rag\_service | Mac | 8003 | `/metrics` |
| llm\_inference\_service | Mac | 8004 | `/metrics`, `/chaos/*` |
| Redis | Mac | 6379 | Password required (`REDIS_PASSWORD`) |
| Ollama | Mac (native) | 11434 | Bound to localhost; containers use `host.docker.internal` |
| Prometheus | Fedora | 9090 | Scrapes Mac every 2 s |
| Resilience core | Fedora | 8600 | `/state`, `/metrics` |
| Dashboard (Streamlit) | Fedora | 8501 |  |
| Locust web UI | Fedora | 8089 | Headless in experiments |

### 2.3 Metric names

Every service exposes `/metrics` through the shared middleware. All custom metrics start with `cs_` and carry a `service` label.

| Metric | Type | Emitted by | Meaning |
| --- | --- | --- | --- |
| `cs_http_requests_total{route,status}` | counter | all | Requests by route and HTTP status |
| `cs_http_request_duration_seconds{route}` | histogram | all | Latency; buckets 0.05 to 30 s |
| `cs_inflight_requests` | gauge | all | Requests currently being handled |
| `process_resident_memory_bytes`, `process_cpu_seconds_total` | gauge, counter | all | Default process collector |
| `cs_llm_queue_depth` | gauge | llm | Requests waiting for a generation slot |
| `cs_llm_queue_wait_seconds` | histogram | llm | Time spent waiting for a slot |
| `cs_llm_tokens_generated_total` | counter | llm | From Ollama `eval_count` |
| `cs_llm_tokens_per_second` | gauge | llm | `eval_count / eval_duration`, last 10 s average |
| `cs_llm_prompt_tokens` | histogram | llm | From `prompt_eval_count` (context size) |
| `cs_llm_timeouts_total` | counter | llm | Generations that exceeded the timeout |
| `cs_llm_model_info{model}` | gauge | llm | 1 for the model currently in use |
| `cs_orch_active_prompts` | gauge | orchestrator | Tutor requests in progress |
| `cs_orch_degradation_level` | gauge | orchestrator | 0 to 4 (see 2.5) |
| `cs_orch_breaker_state` | gauge | orchestrator | 0 closed, 1 half-open, 2 open |
| `cs_orch_responses_total{level,source}` | counter | orchestrator | Answers by level and source (llm, cache, rag, hint, queued) |
| `cs_rag_query_seconds` | histogram | rag | Retrieval time |
| `cs_cache_hits_total`, `cs_cache_misses_total` | counter | rag | Semantic cache |
| `cs_sessions_active` | gauge | gateway | Distinct sessions seen in the last 60 s |
| `cs_shed_requests_total{priority}` | counter | gateway | Requests rejected or queued by admission control |
| `cs_submissions_total{status}` | counter | student | Quiz submits: committed, duplicate, failed |

Added in Phase 3: `cs_admission_limit` (gauge, gateway), the current adaptive concurrency limit for tutoring requests.

### 2.4 Redis keys

| Key | Type | Writer | Reader | Meaning |
| --- | --- | --- | --- | --- |
| `cs:control:heartbeat` | string, TTL 10 s | Fedora | Mac | Unix time; if missing, Mac uses its local breaker |
| `cs:mode:level` | string `0`–`4` | Fedora | Mac | Requested degradation level |
| `cs:breaker:llm` | `closed` / `half_open` / `open` | Fedora | Mac | Requested breaker state |
| `cs:mode:exam` | JSON | Fedora | Mac | `{"active":true,"course":"DSA101","ends_at":...}` |
| `cs:risk:<service>` | float, TTL 15 s | Fedora | Mac, dashboard | Latest failure probability |
| `cs:explain:<service>` | JSON, TTL 15 s | Fedora | dashboard | Top 3 SHAP factors |
| `cs:actions` | stream | both | dashboard | Every containment action with reason and actor |
| `cs:cache:<hash>` | hash, TTL 6 h | Mac | Mac | Cached answer, topic, vetted flag |
| `cs:rl:<student_id>` | string, TTL 60 s | Mac | Mac | Rate-limit token bucket |

Redis runs with `maxmemory 64mb` and `maxmemory-policy volatile-lru`, so only keys with a TTL (cache, rate limits) can be evicted.

### 2.5 Degradation levels

| Level | Name | Behaviour | Uses LLM? |
| --- | --- | --- | --- |
| 0 | Full | Socratic answer, up to 256 tokens, 3 RAG chunks, last 4 turns of history | Yes |
| 1 | Lean | Up to 80 tokens, 1 RAG chunk, no history | Yes, cheaper |
| 2 | Cache + RAG | Cached answer if similarity ≥ 0.75, else the best syllabus passage with a guiding question | No |
| 3 | Static hints | Rule-based Socratic hint for the detected topic from `hints.yaml` | No |
| 4 | Shed | Question saved, student told their place in the queue; quiz path unaffected | No |

Fallback paths (levels 2–4) must never call Ollama. They use TF-IDF in the RAG service and plain files.

### 2.6 Control API

Served by `orchestrator_service` on port 8002. Every call needs header `X-CS-Token`. Every call also appends to `cs:actions`.

| Method and path | Body | Effect |
| --- | --- | --- |
| `GET /control/state` | none | Current level, breaker, exam mode, heartbeat age, protection mode |
| `POST /control/mode` | `{"level":2,"reason":"risk 0.86","actor":"cascadeshield"}` | Set degradation level |
| `POST /control/breaker` | `{"state":"open","reason":"..."}` | Set breaker state |
| `POST /control/exam` | `{"active":true,"course":"DSA101","ends_at":"2026-11-20T10:30:00+05:30"}` | Exam mode on or off |
| `POST /control/prewarm` | `{"course":"DSA101","topics":["bst","heaps"]}` | Generate and cache FAQ answers |
| `POST /admin/reset` | none | Clear queues, counters and cache between experiment episodes |

Chaos hooks on `llm_inference_service` and `curriculum_rag_service` (only when `CHAOS_ENABLED=1`): `POST /chaos/latency {"extra_ms":800,"seconds":120}`, `POST /chaos/leak {"mb_per_s":2,"seconds":180}`, `POST /chaos/errors {"rate":0.1,"seconds":60}`, `POST /chaos/clear`.

### 2.7 Public API (gateway, port 8000)

| Method and path | Body | Response |
| --- | --- | --- |
| `POST /api/tutor/ask` | `{"student_id","session_id","course","question"}` | `{"answer","level","source","latency_ms"}` |
| `POST /api/quiz/submit` | `{"student_id","quiz_id","answers","idempotency_key"}` | `202 {"status":"committed"}` |
| `GET /api/status` | none | `{"level","banner"}` for the student page |
| `GET /health` | none | `200` when the service is ready |

### 2.8 Phase milestones

| Milestone | End of | Both machines together show |
| --- | --- | --- |
| M0 | Day 3 | Contracts merged; each person runs the stack locally (Fedora with the mock LLM) |
| M1 | Week 2 | Walking skeleton: Locust on Fedora loads the Mac, a threshold rule opens the breaker, the dashboard turns red then green |
| M2 | Week 4 | Full ladder L0–L4 controlled remotely; at least 50 recorded episodes |
| M3 | Week 6 | ML predictor drives containment; SHAP, cascade graph, exam mode and pre-warm all live |
| M4 | Week 8 | Three-mode comparison done; chapter figures captured; `demo.sh` rehearsed; backup video recorded |

Meet for a two-machine integration session every Friday. Use a phone hotspot or travel router so both laptops are on the same network, and turn on time sync (NTP) on both machines so timestamps line up.

## 3. Phase 0 — Setup (Days 1–3, milestone M0)

By day 3 the Mac runs Ollama with a calibrated baseline and the contracts are merged. Your partner is doing the same on Fedora in parallel.

### 3.1 Install and configure

1. Install Homebrew, Git, and Python 3.12 through `uv` (`brew install uv`, then `uv python install 3.12`).
2. Install **Docker Desktop**. In Settings → Resources set: Memory **2.5 GB**, Swap **1 GB**, CPUs **4**, disk 32 GB. Turn **Resource Saver off** so containers never pause during a demo.
3. Install the **Ollama** macOS app. Set its environment, then quit and reopen the app:

```bash
launchctl setenv OLLAMA_NUM_PARALLEL 2
launchctl setenv OLLAMA_KEEP_ALIVE -1
launchctl setenv OLLAMA_CONTEXT_LENGTH 2048
launchctl setenv OLLAMA_MAX_LOADED_MODELS 1
ollama pull qwen2.5:0.5b
ollama pull smollm2:135m   # optional lean model, test before relying on it
```

4. Confirm Ollama returns the timing fields you will turn into metrics:

```bash
curl -s localhost:11434/api/generate -d '{"model":"qwen2.5:0.5b","prompt":"Explain a binary search tree in two sentences.","stream":false}' | python3 -m json.tool
# look for: eval_count, eval_duration, prompt_eval_count, load_duration
```

5. Allow incoming connections: System Settings → Network → Firewall → allow Docker. Note the Mac's LAN address with `ipconfig getifaddr en0` and put it in `.env` as `PLATFORM_HOST`. Turn on "Set time automatically" for NTP.

### 3.2 Calibrate the baseline (the most important task this phase)

Every threshold in the project comes from this measurement, so do it carefully and write it in `docs/calibration.md`.

1. Close other apps. Send 30 sequential tutor-style prompts (about 60 prompt tokens, 200 output tokens) and record latency and tokens per second.
2. Repeat with 2, 4 and 8 concurrent requests.
3. Record: unloaded p50 and p95 latency, tokens per second, and the concurrency at which p95 first exceeds 3× the unloaded p95. That knee is the platform's real capacity.
4. Propose the latency SLO for `llm_inference_service` as 3× unloaded p95 and share it with your partner. Their failure labels depend on it.

Watch Activity Monitor → Memory during the test. Memory pressure must stay green. If it turns yellow, lower Docker memory or drop `OLLAMA_NUM_PARALLEL` to 1.

### 3.3 Repo and contracts

1. Create the repository with the layout in 2.1, add `.env.example`, `.gitignore` and a README with the run commands.
2. Write `contracts/metrics.md`, `contracts/redis_keys.md` and `contracts/control_api.md` from section 2 with your partner. They write `contracts/features.md`.
3. Add `scripts/check_contracts.py` (your partner owns it): it scrapes every `/metrics` endpoint and fails if a metric named in `metrics.md` is missing. Run it in every integration session.

**M0 exit check**

- [ ] `ollama run qwen2.5:0.5b` answers in under 2 s on the Mac
- [ ] `docs/calibration.md` committed with the proposed SLO
- [ ] Contracts merged to `main`
- [ ] Fedora can `ping` the Mac on the shared network

## 4. Phase 1 — Platform core (Weeks 1–2, milestone M1)

By the end of Week 2 all five services run in Compose, emit the contract metrics, and serve real Socratic answers from Ollama. Fedora meanwhile builds Prometheus, Locust and a skeleton control loop against the mock LLM.

### 4.1 Shared library `cs_common`

- `metrics.py`: a FastAPI middleware that records `cs_http_requests_total`, `cs_http_request_duration_seconds` and `cs_inflight_requests` for every route, plus a `/metrics` endpoint using `prometheus_client`. Exclude `/metrics` and `/health` from the latency histogram.
- `logging.py`: JSON logs with a `request_id` passed between services in the `X-Request-ID` header.
- `redis_client.py`: one async connection pool; helpers `get_level()`, `get_breaker()`, `heartbeat_age()`, `log_action()`.
- `settings.py`: `pydantic-settings` reading `.env` (`SERVICE_NAME`, URLs of other services, timeouts, `PROTECTION_MODE`, `LLM_BACKEND`, `CHAOS_ENABLED`).
- Use one `httpx.AsyncClient` per service with explicit timeouts. A missing timeout is the most common cause of a real cascade, so never leave one at the default.

### 4.2 `llm_inference_service` (port 8004)

1. `POST /generate {prompt, max_tokens, model?}` → forwards to `http://host.docker.internal:11434/api/generate` with `stream:false` and `options.num_predict = max_tokens`.
2. Model the GPU's limited slots explicitly: an `asyncio.Semaphore(MAX_INFLIGHT)` with `MAX_INFLIGHT` equal to `OLLAMA_NUM_PARALLEL`. Count waiters to export `cs_llm_queue_depth` and time the wait for `cs_llm_queue_wait_seconds`.
3. From each Ollama response update `cs_llm_tokens_generated_total`, `cs_llm_prompt_tokens` and the rolling `cs_llm_tokens_per_second`.
4. Timeout per generation: `LLM_TIMEOUT_S` (start at 20 s). On timeout increment `cs_llm_timeouts_total` and return 504.
5. Queue cap `MAX_QUEUE`: very large (1000) in `PROTECTION_MODE=none`, so the unprotected baseline fails naturally; 40 otherwise, returning 503 beyond it.
6. `LLM_BACKEND=mock` swaps Ollama for `mock_llm`: a simulator that sleeps for `prompt_tokens × 0.002 + output_tokens / tokens_per_s` seconds with tokens per second taken from your calibration and the same semaphore. Your partner develops against this, and it is your demo fallback.

### 4.3 `curriculum_rag_service` (port 8003)

1. Write course content in `data/curriculum/`: three courses (for example DSA101 Data Structures, DBMS201, OS202), about 10 topics each, one Markdown file per topic with headings `Concept`, `Example`, `Common mistakes`, `Practice question`. Tag any worked solution with `<!-- type: solution -->` so exam mode can exclude it.
2. At startup, split files into about 400-character chunks and fit a scikit-learn `TfidfVectorizer` (bigrams, English stop words). Keep the matrix in memory; it is tiny.
3. `POST /search {query, course, k}` → top k chunks with cosine scores.
4. `POST /cache/get {question, course}` and `POST /cache/put {question, course, answer, vetted}`: store answers in Redis as `cs:cache:<hash>` and keep their TF-IDF vectors in memory; a hit needs cosine similarity ≥ 0.75.
5. No call in this service may reach Ollama. That is what makes it a safe fallback.

### 4.4 `student_service` (port 8001)

1. SQLite file on a named volume, opened with `PRAGMA journal_mode=WAL`. Tables: `students(id, name, course, mastery_json)`, `submissions(idempotency_key PRIMARY KEY, student_id, quiz_id, answers_json, received_at)`.
2. Seed 1,500 synthetic students with random mastery per topic (a seed script in `platform/data/seed.py`).
3. `GET /profile/{id}` → mastery levels. `POST /submissions` → insert; a duplicate key returns the existing row with status `duplicate`. Update `cs_submissions_total{status}`.
4. `GET /admin/stats` → counts of committed submissions, used by the comparison experiments to measure loss.

### 4.5 `orchestrator_service` (port 8002)

1. `POST /tutor/ask`: fetch the profile (timeout 300 ms; on failure use a default "intermediate" profile), fetch 3 RAG chunks, build the prompt, call `/generate`, return `{answer, level, source}`.
2. Socratic system prompt, kept in `prompts/socratic.txt`: respond with one guiding question and one hint, never the full solution, adapt to the student's mastery level, at most 120 words.
3. For now implement only level 0 and a simple check: if `cs:breaker:llm` is `open`, return the static hint for the topic. Phase 2 replaces this with the full ladder.
4. Implement the control API from 2.6 (state, mode, breaker; exam and prewarm can return 501 until Phase 3).

### 4.6 `gateway_service` (port 8000)

1. Routes from 2.7. Issue a session id on first contact; track active sessions for `cs_sessions_active`.
2. Per-student token bucket in Redis (`cs:rl:<id>`): 6 tutor questions per minute.
3. `POST /api/quiz/submit` goes **directly to `student_service`**, never through the orchestrator. This is the session-preservation guarantee; keep it that way.
4. Serve a placeholder page at `/`; Phase 3 makes it the real student page.

### 4.7 Compose `platform` profile

- Images from `python:3.12-slim`, one `uvicorn` worker per service.
- Memory limits: 160 MB per service, 320 MB for the RAG service, 96 MB for Redis. Total under 1.3 GB.
- `redis` command: `redis-server --requirepass ${REDIS_PASSWORD} --maxmemory 64mb --maxmemory-policy volatile-lru`.
- Health checks on `/health`; `depends_on` with `condition: service_healthy`.
- Publish ports 8000–8004 and 6379 to the LAN so Prometheus and the control room can reach them.

### 4.8 Joint work for M1

In the Week 2 integration session: your partner points Locust at your gateway and Prometheus at your five `/metrics` endpoints; their skeleton loop reads risk from simple thresholds and writes `cs:breaker:llm`. You confirm the orchestrator switches to static hints and back.

**M1 exit check**

- [ ] `docker compose --profile platform up` brings all services healthy in under 30 s
- [ ] `check_contracts.py` passes from Fedora against the Mac
- [ ] A tutor question through the gateway returns a Socratic answer from Ollama
- [ ] Under Locust load, p95 latency climbs and Fedora's breaker flips the orchestrator to static hints
- [ ] Quiz submits succeed while the LLM is saturated

## 5. Phase 2 — Degradation and data (Weeks 3–4, milestone M2)

By the end of Week 4 the full ladder works under remote control, the platform can be faulted on demand, and the two of you have recorded at least 50 experiment episodes. Fedora meanwhile writes the failure labels and the episode runner.

### 5.1 Degradation ladder in the orchestrator

1. Compute the effective level on every request: `level = max(redis_level, local_level, exam_floor)`. `redis_level` comes from Fedora, `local_level` from the local breaker, `exam_floor` from exam mode (Phase 3).
2. Implement each level from 2.5 as its own function (`answer_full`, `answer_lean`, `answer_cache_rag`, `answer_hint`, `answer_shed`) so each can be tested alone.
3. Level 2 detail: try `/cache/get`; on a miss, take the best `/search` chunk and append a guiding question from `hints.yaml` ("What happens to the tree's height if you insert sorted keys?").
4. Level 4 detail: store the question in a Redis list per course and return its position. A background task answers the queue when the level drops back to 0 or 1.
5. Every response carries `level` and `source`; update `cs_orch_responses_total{level,source}` and `cs_orch_degradation_level`.
6. Write `data/hints.yaml` with at least 3 Socratic hints per topic (90+ in total). This is real content work; start it early.

### 5.2 Circuit breaker with hysteresis

The breaker protects the orchestrator's calls to the LLM service.

| State | Enter when | Behaviour | Leave when |
| --- | --- | --- | --- |
| Closed | Start, or half-open probes succeed | All calls go to the LLM | Open condition met |
| Open | Fedora sets `open`, or 5 timeouts within 10 s (local) | No LLM calls; level ≥ 2 | After 20 s (local) or Fedora sets `half_open` |
| Half-open | Timer expires or Fedora request | 10% of requests probe the LLM | 5 probes succeed → closed; 1 fails → open |

Hysteresis lives in Fedora's containment engine (open at risk ≥ 0.8, close only after risk < 0.5 for 30 s). Your local rule exists for the `reactive` baseline and as a failsafe.

### 5.3 Protection modes and failsafe

- `PROTECTION_MODE` is read at startup: `none` (no breaker, huge queue, never reads Redis control keys), `reactive` (local breaker only), `cascadeshield` (follows Fedora, local breaker as backup). The experiments restart the stack between modes.
- Heartbeat failsafe: in `cascadeshield` mode, if `cs:control:heartbeat` is older than 10 s, ignore Fedora's keys and use the local breaker. Log the switch to `cs:actions`. This is a strong viva answer to "what if your AI fails?".

### 5.4 Quiz path guarantees

1. Client generates `idempotency_key` (UUID) per submission; the page and Locust retry the same key up to 3 times.
2. The gateway forwards to `student_service` with a 2 s timeout and its own small connection pool, separate from the tutor path. A saturated tutor path cannot starve it.
3. Test: with the LLM fully saturated, 200 concurrent submits must all commit with zero duplicates.

### 5.5 Chaos hooks

Add the endpoints in 2.6, active only when `CHAOS_ENABLED=1`:

- `/chaos/latency`: add `extra_ms` before each Ollama call (simulates a slower GPU).
- `/chaos/leak`: allocate and hold `mb_per_s` of memory each second (stays inside the 160 MB limit by capping at 120 MB, then the container gets slow, not killed).
- `/chaos/errors`: return 500 for a fraction of requests.
- RAG `/chaos/latency`: slow retrieval (tests a non-LLM bottleneck).
- `/chaos/clear` and `/admin/reset` restore a clean state between episodes in under 5 s.

### 5.6 Overnight dataset runs (joint)

Fedora's episode runner drives the experiments, but the Mac must stay up:

1. Before starting: `caffeinate -dims &`, plug in power, close all other apps, `PROTECTION_MODE=none`, `CHAOS_ENABLED=1`.
2. Check memory pressure stays green during the first two episodes, then leave it running.
3. Next morning, check `docker compose logs` for restarts. A container restart in the middle of an episode invalidates that episode; tell your partner which ones.

### 5.7 Semantic cache seeding

Write `data/faq.yaml`: 5 likely student questions per topic. A script `seed_cache.py` asks each at level 0 during quiet time and stores the answers with `vetted=false`. Read through them together and mark the good ones `vetted=true`; only vetted answers are served in exam mode.

**M2 exit check**

- [ ] `POST /control/mode` moves the platform through levels 0–4 and each level answers correctly
- [ ] Local breaker opens and closes in `reactive` mode under load
- [ ] Failsafe triggers when the control room is stopped
- [ ] 200 concurrent submits under saturation: 100% committed, 0 duplicates
- [ ] At least 50 clean episodes recorded

## 6. Phase 3 — Exam intelligence (Weeks 5–6, milestone M3)

By the end of Week 6 the platform understands exams: it protects graded work first, sheds tutoring fairly, pre-warms answers before a scheduled exam, and shows students an honest status banner. Fedora meanwhile trains the predictor and builds the containment engine that drives your control API.

### 6.1 Exam mode

Implement `POST /control/exam`. While active:

1. **Priority admission at the gateway.** Two classes: P0 quiz submits (never shed, own pool), P1 tutoring. Tutoring passes through an admission limiter.
2. **Adaptive concurrency limit for P1** (AIMD, like TCP congestion control): start at 4 concurrent tutor requests; every 5 s, if gateway tutor p95 is under target, raise the limit by 1; on any LLM timeout, halve it (minimum 1). Requests over the limit wait up to 3 s, then get level 4 (shed). Export the limit as `cs_admission_limit` and add it to `contracts/metrics.md`.
3. **Academic integrity filter.** For the exam's course, fallback levels exclude chunks tagged `type: solution` and serve only vetted cache entries. The tutor can still help, but cannot hand out answers during the exam.
4. **Exam floor.** Fedora may set a minimum level (usually 1, lean) for the exam window. The orchestrator applies it through `exam_floor`.

### 6.2 Pre-warm

Implement `POST /control/prewarm {course, topics}`. For each topic, take its FAQ questions, generate level-0 answers at low concurrency (1 at a time), and store them in the cache. Fedora calls this 10 minutes before a scheduled exam from its calendar. Measure and record how long pre-warming 10 topics takes; it must finish before the exam starts.

### 6.3 Student web page

A single `web/index.html` with plain JavaScript, served by the gateway at `/`:

- Course picker, chat box for tutor questions, a quiz panel with 5 questions and a Submit button.
- Each answer shows a small tag for its source: "AI tutor", "Light mode", "From course notes", "Hint".
- A status banner polling `/api/status` every 3 s: green "Tutor running normally", amber "Tutor in light mode: answers are shorter", blue "High demand: showing course notes and hints. Your quiz is safe."
- Show "Submitted ✓" only after the server confirms the commit.

This page is your live demo moment: an evaluator types a question while Locust is hammering the system and still gets a useful answer.

### 6.4 Control integration

1. Every control call writes to `cs:actions` with `actor`, `reason` and, when Fedora provides them, the top SHAP factors. The dashboard reads this stream.
2. Add `GET /control/state` fields Fedora needs: effective level, breaker state, admission limit, exam status, heartbeat age.
3. Load-test together and tune: `LLM_TIMEOUT_S`, `MAX_QUEUE`, AIMD target and step size. Record the final values in `docs/calibration.md`.

### 6.5 Fairness check

Add `course` as a label on `cs_orch_responses_total`. After a run, compare each course's share of degraded answers. If one course always gets level 3 while another gets level 0, change the shed queue to round-robin by course.

**M3 exit check**

- [ ] With exam mode on, quiz submits stay under 500 ms p95 while tutoring is degraded
- [ ] Pre-warm of 10 topics finishes and cache hit rate during the exam is above 40%
- [ ] Integrity filter: no `solution` chunk is served to the exam's course during the window
- [ ] Banner changes within 3 s of a level change
- [ ] Fedora's ML-driven containment moves your platform through levels with no manual input

## 7. Phase 4 — Evaluation and demo (Weeks 7–8, milestone M4)

By the end of Week 8 the comparison results exist, the chapter figures are captured, and the demo starts with one command and survives a bad network or a misbehaving model. Fedora meanwhile runs the experiment matrix and polishes the dashboard.

### 7.1 `scripts/demo.sh` (Mac side)

1. Preflight checks, each printing pass or fail: Ollama responds, model is loaded (`ollama ps`), Docker memory setting is 2.5 GB, Fedora answers on the network, memory pressure is green.
2. Start the `platform` profile in `cascadeshield` mode, wait for all health checks.
3. Warm the model with 5 requests so the first demo answer is not slow.
4. `POST /admin/reset`, then print the student page URL.
5. A `--mock` flag starts with `LLM_BACKEND=mock` for when Ollama misbehaves. A `--single` flag runs the control profile on the Mac too, for when the network fails (slower, but it works).

### 7.2 Comparison runs (joint)

Fedora's `run_matrix.py` runs the same seeded exam scenario under each mode, 3 runs each. Your job between runs:

1. Restart the platform with the next `PROTECTION_MODE` (`none`, `reactive`, `cascadeshield`).
2. `POST /admin/reset` and wipe the submissions table, so `GET /admin/stats` measures only that run.
3. Keep the Mac in the same state for all 9 runs: same apps closed, power plugged in, same Docker settings. Note any anomaly in `docs/results.md`.

### 7.3 Answer quality rating (joint)

Collect 30 answers per level (0, 1, 2, 3) for the same 30 questions. Both of you rate each answer 1–5 on "would this help a student move forward?" without seeing which level produced it. Average the two ratings. This gives the "learning utility retained" number per level, the metric no generic resilience tool reports.

### 7.4 Demo hardening

- Run the full demo end to end 5 times. Every failure becomes a fix or a line in the troubleshooting table.
- Record a backup video with QuickTime screen recording: healthy state, load ramp, prediction, containment, student page still answering, recovery. About 4 minutes.
- Freeze dependencies: pin versions in every `requirements.txt` and tag the repo `v1.0-demo`.

### 7.5 Viva script (your part, about 3 minutes)

1. Show the student page answering a question normally.
2. Partner starts the exam ramp from Fedora.
3. As the banner turns amber then blue, ask a question and show the fallback answer with its source tag.
4. Submit the quiz and show the confirmed commit.
5. Show `GET /control/state` and explain the level, breaker and failsafe.

**M4 exit check**

- [ ] 9 comparison runs complete with no container restarts
- [ ] Quality ratings collected for 120 answers
- [ ] `demo.sh`, `--mock` and `--single` each tested from a cold start
- [ ] Backup video saved in two places
- [ ] Repo tagged `v1.0-demo`

## 8. Definition of done, troubleshooting and viva questions

### 8.1 Definition of done (whole project, Mac side)

- [ ] All five services pass `check_contracts.py` and every health check
- [ ] Levels 0–4 each produce a useful answer; levels 2–4 never call Ollama
- [ ] Zero quiz submissions lost or duplicated in any comparison run
- [ ] Failsafe works when the control room is switched off
- [ ] Exam mode, integrity filter, pre-warm and banner all demonstrated
- [ ] Memory pressure stays green for a full 12-minute exam run
- [ ] `demo.sh` works from a cold start, plus `--mock` and `--single` fallbacks

### 8.2 Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Containers cannot reach Ollama | Wrong host name | Use `http://host.docker.internal:11434`; check Ollama is running with `ollama ps` |
| First answer takes 10+ s | Model unloaded | Check `OLLAMA_KEEP_ALIVE=-1` is set; run the warm-up in `demo.sh` |
| Mac becomes sluggish under load | Memory pressure, swapping | Lower `OLLAMA_NUM_PARALLEL` to 1, close the browser, check Docker is at 2.5 GB |
| Fedora cannot scrape `/metrics` | Firewall or network isolation | Allow Docker in the macOS firewall; use a hotspot instead of college Wi-Fi |
| Redis connection refused from Fedora | Bound to localhost or no password | Publish 6379 in Compose and pass `REDIS_PASSWORD` on both sides |
| Timelines do not line up between machines | Clock drift | Turn on automatic time on both machines |
| Breaker flips on and off rapidly | Hysteresis missing | Fedora must apply open ≥ 0.8, close < 0.5 held for 30 s |
| Episode results look odd | Container restarted mid-run | Check `docker compose ps` restart counts; discard that episode |

### 8.3 Viva questions to prepare

| Question | Answer in one line |
| --- | --- |
| Why not just scale the LLM? | One GPU on one machine; replicas would share it. Real capacity comes from lean mode, caching and shedding. |
| What if the AI predictor is wrong or offline? | The heartbeat failsafe drops back to a local reactive breaker; the platform never depends on the control room. |
| How do you guarantee no quiz is lost? | Separate path that bypasses the LLM, separate pool, idempotency keys, durable SQLite in WAL mode. |
| Why do fallbacks not call the LLM? | A fallback that shares the failing resource fails with it, so levels 2–4 use TF-IDF and files only. |
| Can students cheat using fallback answers during an exam? | The integrity filter removes solution chunks and unvetted cache entries for the exam's course. |
| Is the mock LLM cheating? | It is only the fallback; all reported results use the real Ollama model, and the mock is calibrated against it. |
| Why Docker Compose and not Kubernetes? | The project studies prediction and degradation, not orchestration; Compose keeps the demo reliable on 8 GB. |
