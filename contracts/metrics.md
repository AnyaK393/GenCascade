# Metric contract

Every service exposes `/metrics` through the shared middleware. All custom metrics start
with `cs_` and carry a `service` label. `/metrics` and `/health` are not recorded in the
HTTP metrics, so scrapes do not dilute latency.

## `service` label values

| Service | `service` label | Port |
| --- | --- | --- |
| gateway_service | `gateway` | 8000 |
| student_service | `student` | 8001 |
| orchestrator_service | `orchestrator` | 8002 |
| curriculum_rag_service | `curriculum_rag` | 8003 |
| llm_inference_service | `llm_inference` | 8004 |

The same names are used in Redis keys (`cs:risk:llm_inference`) and in the dependency graph.

## Metrics

The "Emitted by" column uses: `all`, `gateway`, `student`, `orchestrator`, `rag`, `llm`.

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
| `cs_orch_degradation_level` | gauge | orchestrator | 0 to 4 (see `control_api.md`) |
| `cs_orch_breaker_state` | gauge | orchestrator | 0 closed, 1 half-open, 2 open |
| `cs_orch_responses_total{level,source}` | counter | orchestrator | Answers by level and source (llm, cache, rag, hint, queued) |
| `cs_rag_query_seconds` | histogram | rag | Retrieval time |
| `cs_cache_hits_total`, `cs_cache_misses_total` | counter | rag | Semantic cache |
| `cs_sessions_active` | gauge | gateway | Distinct sessions seen in the last 60 s |
| `cs_shed_requests_total{priority}` | counter | gateway | Requests rejected or queued by admission control |
| `cs_submissions_total{status}` | counter | student | Quiz submits: committed, duplicate, failed |

Histogram buckets for `cs_http_request_duration_seconds`:
`0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 12, 15, 20, 30`.

## Phase 3 additions

Not checked by `check_contracts.py` until `--phase 3` is passed.

| Metric | Type | Emitted by | Meaning |
| --- | --- | --- | --- |
| `cs_admission_limit` | gauge | gateway | Current adaptive concurrency limit for tutoring requests |

## Prometheus recording rules (Fedora, `control/prometheus/rules.yml`)

Every consumer uses these, never its own PromQL:
`cs:latency_p95:15s`, `cs:error_rate:15s`, `cs:rps:15s`, all `by (service)`.
