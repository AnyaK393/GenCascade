| Concurrency | Requests | p50 (s) | p95 (s) | tok/s per request | tok/s total | prompt tok | output tok |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 30 | 4.92 | 6.24 | 39.7 | 38.1 | 70 | 199 |
| 2 | 8 | 6.32 | 6.33 | 32.7 | 63.7 | 70 | 200 |
| 4 | 16 | 12.32 | 12.80 | 32.8 | 64.5 | 70 | 200 |
| 8 | 32 | 25.10 | 26.04 | 32.2 | 63.4 | 70 | 200 |

- Unloaded p95: **6.24 s**; unloaded tokens/s per request: **39.7**
- Knee (first concurrency with p95 > 3x unloaded p95): **8**
- Proposed `llm_inference` SLO (3x unloaded p95): **18.7 s**
