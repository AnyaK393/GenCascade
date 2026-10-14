# CascadeShield

Predictive cascade-failure protection for a campus GenAI tutoring platform.

| Directory | Owner | What |
| --- | --- | --- |
| `contracts/` | both (PR approved by both) | Metric names, Redis keys, control API, features |
| `platform/` | Mac | The GenAI platform: 5 FastAPI services, Redis, Ollama, student page |
| `control/` | Fedora | The control room: Prometheus, Locust, resilience core, dashboard, experiments |
| `scripts/` | shared | `check_contracts.py`, `demo.sh` |
| `docs/` | shared | calibration, results, figures |

Quick start: `cp .env.example .env`, then `make help`.
Each side's README (`control/README.md`, `platform/README.md`) has the details.

Branches: `main` is protected; work on `mac/<feature>` or `fedora/<feature>`.
Any PR touching `contracts/`, `docker-compose.yml`, `Makefile` or `.env.example` needs the other person's review.
