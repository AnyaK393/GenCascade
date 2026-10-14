# Ports, control API and public API

## Ports

| Component | Host | Port | Notes |
| --- | --- | --- | --- |
| gateway_service | Mac | 8000 | Public API, student web page, `/metrics` |
| student_service | Mac | 8001 | `/metrics` |
| orchestrator_service | Mac | 8002 | `/metrics`, `/control/*` |
| curriculum_rag_service | Mac | 8003 | `/metrics` |
| llm_inference_service | Mac | 8004 | `/metrics`, `/chaos/*` |
| Redis | Mac | 6379 | Password required (`REDIS_PASSWORD`) |
| Ollama | Mac (native) | 11434 | Bound to localhost; containers use `host.docker.internal` |
| Prometheus | Fedora | 9090 | Scrapes Mac every 2 s |
| Resilience core | Fedora | 8600 | `/state`, `/metrics` |
| Dashboard (Streamlit) | Fedora | 8501 | |
| Locust web UI | Fedora | 8089 | Headless in experiments |

## Degradation levels

| Level | Name | Behaviour | Uses LLM? |
| --- | --- | --- | --- |
| 0 | Full | Socratic answer, up to 256 tokens, 3 RAG chunks, last 4 turns of history | Yes |
| 1 | Lean | Up to 80 tokens, 1 RAG chunk, no history | Yes, cheaper |
| 2 | Cache + RAG | Cached answer if similarity ≥ 0.75, else the best syllabus passage with a guiding question | No |
| 3 | Static hints | Rule-based Socratic hint for the detected topic from `hints.yaml` | No |
| 4 | Shed | Question saved, student told their place in the queue; quiz path unaffected | No |

Fallback paths (levels 2–4) must never call Ollama. They use TF-IDF in the RAG service and plain files.

## Control API

Served by `orchestrator_service` on port 8002. Every call needs header `X-CS-Token`.
Every call also appends to `cs:actions`.

| Method and path | Body | Effect |
| --- | --- | --- |
| `GET /control/state` | none | Current level, breaker, exam mode, heartbeat age, protection mode |
| `POST /control/mode` | `{"level":2,"reason":"risk 0.86","actor":"cascadeshield"}` | Set degradation level |
| `POST /control/breaker` | `{"state":"open","reason":"..."}` | Set breaker state |
| `POST /control/exam` | `{"active":true,"course":"DSA101","ends_at":"2026-11-20T10:30:00+05:30"}` | Exam mode on or off |
| `POST /control/prewarm` | `{"course":"DSA101","topics":["bst","heaps"]}` | Generate and cache FAQ answers |
| `POST /admin/reset` | none | Clear queues, counters and cache between experiment episodes |

`GET /control/state` response:

```json
{"level": 0, "breaker": "closed", "exam": {"active": false},
 "heartbeat_age_s": 1.4, "protection_mode": "cascadeshield"}
```

`heartbeat_age_s` is `null` when the heartbeat key is missing (failsafe active).
`protection_mode` is one of `none`, `reactive`, `cascadeshield` (env `PROTECTION_MODE` on the Mac).

## Chaos hooks

On `llm_inference_service` and `curriculum_rag_service`, only when `CHAOS_ENABLED=1`
(also require `X-CS-Token`):

| Method and path | Body |
| --- | --- |
| `POST /chaos/latency` | `{"extra_ms":800,"seconds":120}` |
| `POST /chaos/leak` | `{"mb_per_s":2,"seconds":180}` |
| `POST /chaos/errors` | `{"rate":0.1,"seconds":60}` |
| `POST /chaos/clear` | none |

## Public API (gateway, port 8000)

| Method and path | Body | Response |
| --- | --- | --- |
| `POST /api/tutor/ask` | `{"student_id","session_id","course","question"}` | `{"answer","level","source","latency_ms"}` |
| `POST /api/quiz/submit` | `{"student_id","quiz_id","answers","idempotency_key"}` | `202 {"status":"committed"}` |
| `GET /api/status` | none | `{"level","banner"}` for the student page |
| `GET /health` | none | `200` when the service is ready |
