# Demo runbook (Mac side, guide section 7)

Owner: Mac developer. Fedora's half (load, dashboard, matrix, figures) is in `control/README.md`.

## Commands

```bash
scripts/demo.sh --prepare   # once, with internet: build platform + control images, pull the model
scripts/demo.sh             # preflight, platform in cascadeshield mode on real Ollama, warm-up, reset
scripts/demo.sh --mock      # Ollama misbehaving: LLM_BACKEND=mock (calibrated simulator)
scripts/demo.sh --single    # no network to Fedora: control room (Prometheus, core, dashboard) on this Mac
scripts/demo.sh --single --mock
scripts/demo.sh --stop      # stop everything; the submissions volume is kept
```

Preflight prints PASS / WARN / FAIL for: `.env`, Ollama responding, model loaded, Docker memory
2.5 GB, `PLATFORM_HOST` equal to this Mac's current address, Fedora answering ping, memory
pressure green. A FAIL does not stop the script; the summary counts them. Compose output goes to
`.demo.log`.

## The day before

- [ ] `git pull`, then `scripts/demo.sh --prepare` on the network you have now (the venue may have none)
- [ ] Phone hotspot on; both laptops joined; `ipconfig getifaddr en0` → `PLATFORM_HOST` in `.env` on **both** machines; Fedora's IP → `CONTROL_HOST`
- [ ] Docker Desktop: Memory 2.5 GB, Swap 1 GB, CPUs 4, Resource Saver off
- [ ] Ollama env set (`launchctl getenv OLLAMA_KEEP_ALIVE` prints `-1`), app restarted
- [ ] Cache answers vetted (`platform/data/cache_seed.yaml`, then `make seed-cache LOAD=1`), or the exam serves no cached answers
- [ ] Power plugged in, `caffeinate -dims &`, every app except Terminal and one browser closed
- [ ] Backup video on the laptop **and** on a USB stick or cloud drive

## Viva script (Mac part, about 3 minutes)

| Step | Do | Say |
| --- | --- | --- |
| 1 | Student page `http://<mac-ip>:8000/`, DSA101, ask "Why does inserting sorted keys make a BST slow?" | Green banner, tag "AI tutor": a Socratic answer from qwen2.5 on this Mac's GPU, one guiding question, no full solution. |
| 2 | Partner starts the exam ramp on Fedora (`make load SCENARIO=exam_ramp`) | Locust is sending 8x what one GPU can serve. Watch the dashboard: risk rises before latency breaks. |
| 3 | When the banner turns amber, then blue, ask another question | The predictor degraded us early. Tag "Light mode" (80 tokens) or "From course notes" (TF-IDF, no LLM). Levels 2-4 never touch Ollama, so they cannot fail with it. |
| 4 | Answer the 5 quiz questions, Submit | "Submitted ✓" only after the server commits. Quiz submits skip the orchestrator, have their own connection pool, idempotency keys and SQLite in WAL mode: zero lost or duplicated in every comparison run. |
| 5 | `curl -s -H "X-CS-Token: $CS_TOKEN" localhost:8002/control/state \| python3 -m json.tool` | Effective level = max(Fedora's level, local breaker, exam floor). `heartbeat_age_s` is Fedora's pulse: if it goes over 10 s we ignore Fedora and use our local breaker (show it: partner presses the kill switch, `control_source` turns `local`). |

If something breaks mid-viva, say what the system is designed to do, then use the fallback:
Ollama hangs → `scripts/demo.sh --mock`; network drops → `scripts/demo.sh --single`; anything
worse → play the backup video.

## Cold-start tests (M4 check)

`scripts/demo.sh --stop`, then the command, timed from the command to "Ready.".

| Date | Command | Platform healthy | Total | Result |
| --- | --- | --- | --- | --- |
| 2026-10-21 | `scripts/demo.sh` | 10 s | 20 s | pass; warm-up 1-3 s per answer |
| 2026-10-21 | `scripts/demo.sh --mock` | 5 s (no rebuild), 41 s (mode switch) | 30-70 s | pass; mock warm-up 4-7 s per answer |
| 2026-10-21 | `scripts/demo.sh --single` | 16 s | 37 s | pass with the control image already built (first build: 22 min of downloads); heartbeat 1.4 s, all 6 Prometheus targets up, dashboard 200; no trained model on the Mac, so threshold rule |
| 2026-10-21 | failsafe (core stopped during `--single`) | | | pass: `control_source` remote → local after 9 s, `actor=failsafe` in `cs:actions` |

Preflight on 2026-10-21 correctly flagged: `PLATFORM_HOST` stale (192.168.0.100 in `.env`, Mac on
192.168.1.34), `CONTROL_HOST=localhost`, memory pressure yellow with other apps open.

## Rehearsals (guide 7.4: 5 full runs)

Every failure becomes a fix or a row in the troubleshooting table below.

| # | Date | Mode | Ran to the end? | What went wrong | Fix |
| --- | --- | --- | --- | --- | --- |
| 1 | | | | | |
| 2 | | | | | |
| 3 | | | | | |
| 4 | | | | | |
| 5 | | | | | |

## Backup video (about 4 minutes, QuickTime → File → New Screen Recording)

Split screen: student page left, Fedora's dashboard right (open it over the network on the Mac).

1. 0:00 Healthy: green banner, an "AI tutor" answer, dashboard all green
2. 0:40 Load ramp starts: sessions and LLM queue climb on the dashboard
3. 1:20 Prediction: risk crosses the threshold before p95 breaks the SLO; SHAP factors shown
4. 1:50 Containment: banner amber → blue, a "From course notes" answer, the `cs:actions` log
5. 2:40 Quiz submitted under load: "Submitted ✓"
6. 3:10 Recovery: load stops, one level down per 30 s, banner back to green
7. 3:50 `GET /control/state` and the failsafe line

Save as `cascadeshield-demo.mov` in two places (laptop + USB or cloud). Note them here: …

## Comparison runs: Mac's job (guide 7.2)

Fedora runs `make matrix RESTART=manual`. At each prompt on the Mac:

```bash
make platform-up MODE=<mode it asks for> CHAOS=1      # none | reactive | cascadeshield
```

then press Enter on Fedora. The runner resets the platform, wipes submissions and reads
`/admin/stats` itself. Keep the Mac identical for all 9 runs (power in, same apps closed, same
Docker settings) and write anything unusual in `docs/results.md` under "Mac notes".

## Answer quality (guide 7.3)

Platform in cascadeshield mode on real Ollama, Fedora's core kill switch on, then on Fedora:
`uv run python -m experiments.answer_quality sheet`. Both raters copy `docs/ratings/sheet.csv`
to `rater_a.csv` / `rater_b.csv`, fill `rating` (1-5, "would this help a student move
forward?") without looking up the level, then `... answer_quality score`.

## Troubleshooting

Guide 8.2, plus what the rehearsals found.

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Containers cannot reach Ollama | Wrong host name | `http://host.docker.internal:11434`; `ollama ps` |
| First answer takes 10+ s | Model unloaded | `OLLAMA_KEEP_ALIVE=-1`; the demo warm-up |
| Mac sluggish under load | Memory pressure, swapping | `OLLAMA_NUM_PARALLEL=1`, close the browser, Docker at 2.5 GB |
| Fedora cannot scrape `/metrics` | Firewall or network isolation | Allow Docker in the macOS firewall; hotspot, not college Wi-Fi |
| Redis refused from Fedora | Bound to localhost or no password | Port 6379 published; same `REDIS_PASSWORD` both sides |
| Timelines do not line up | Clock drift | Automatic time on both machines |
| Breaker flips rapidly | Hysteresis missing | Fedora: open ≥ 0.8, close < 0.5 held 30 s |
| Episode results odd | Container restarted mid-run | `make platform-ps` restart counts; discard the episode |
| Preflight: `PLATFORM_HOST` does not match | New network, new DHCP address | Update `.env` on both machines; Fedora `make prom-targets` |
| Every `demo.sh` run recreates all containers (about 40 s) | Build attestations give each build a new image id | `demo.sh` sets `BUILDX_NO_DEFAULT_ATTESTATIONS=1`; unchanged reruns take about 5 s |
| `--single`: "network ... not found" | Control containers left over from an older `--stop` | `scripts/demo.sh --stop` (now removes both profiles), then rerun |
| `--single`: core says `model refused: ... rf_v1.joblib` | Trained models are git-ignored, only on Fedora | Copy `control/models/*.joblib` from Fedora into `control/models/` on the Mac |
| `--single` stuck building for minutes | Control image missing, downloading its dependencies | `scripts/demo.sh --prepare` the day before, with internet |

## Release

When rehearsals pass: dependencies are pinned (`platform/requirements.txt`, `control/uv.lock`),
merge to `main`, then `git tag -a v1.0-demo -m "Demo build" && git push origin v1.0-demo`.

| Date | Mode | Scenario | Quiz p95 | Tutor p50 / p95 | Result |
| --- | --- | --- | --- | --- | --- |
| 2026-10-25 | Single (Mock) | exam_ramp | 140 ms | 24 ms / 3.9 s | Clean pass (0% quiz errors, fast cache responses) |
