# Redis key contract

Redis runs on the Mac with a password (`REDIS_PASSWORD`), `maxmemory 64mb` and
`maxmemory-policy volatile-lru`, so only keys with a TTL (cache, rate limits) can be evicted.
Control keys have no TTL except where stated, so they are never evicted.

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

## `cs:actions` entry fields

Every `XADD` to `cs:actions` (capped with `MAXLEN ~ 10000`) carries string fields:

| Field | Example | Notes |
| --- | --- | --- |
| `ts` | `1792900000.123` | Unix time, seconds |
| `actor` | `cascadeshield`, `operator`, `failsafe`, `calendar` | Who decided |
| `action` | `set_level`, `set_breaker`, `set_exam`, `prewarm`, `reset` | What |
| `value` | `2`, `open` | New value |
| `reason` | `risk 0.86 >= 0.80 for 4s` | Human-readable |
| `risk` | `0.86` | Optional |
| `extra` | JSON | Optional (threshold, SHAP factors, ...) |
