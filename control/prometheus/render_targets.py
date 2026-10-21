#!/usr/bin/env python3
"""Write Prometheus file_sd targets from PLATFORM_HOST (environment, else the repo's .env).
Standard library only, so it runs on either machine without the control virtualenv.

Prometheus runs in a container on the compose project's network, so "localhost" there is the
container itself. A platform on this same host (PLATFORM_HOST localhost or compose) is part of the
same compose project, so its services are scraped by compose name (works on podman and Docker);
a remote platform by its address. The core is scraped as the resilience-core container; a core
run natively for development is not scraped.
"""

import json
import os
from pathlib import Path

SERVICE_PORTS = {"gateway": 8000, "student": 8001, "orchestrator": 8002, "curriculum_rag": 8003,
                 "llm_inference": 8004}  # contracts/metrics.md
LOCAL = {"localhost", "127.0.0.1", "::1", "host.docker.internal", "compose", ""}
COMPOSE_NAMES = {"gateway": "gateway", "student": "student", "orchestrator": "orchestrator",
                 "curriculum_rag": "rag", "llm_inference": "llm_inference"}  # platform/compose.yml
HERE = Path(__file__).resolve().parent


def platform_host() -> str:
    if os.environ.get("PLATFORM_HOST"):
        return os.environ["PLATFORM_HOST"].strip()
    env = HERE.parents[1] / ".env"
    for line in env.read_text().splitlines() if env.exists() else []:
        if line.startswith("PLATFORM_HOST="):
            return line.split("=", 1)[1].split("#")[0].strip()
    return "localhost"


configured = platform_host()
local = configured in LOCAL
targets = HERE / "targets"
(targets / "core").mkdir(parents=True, exist_ok=True)
(targets / "platform.json").write_text(json.dumps(
    [{"targets": [f"{COMPOSE_NAMES[s] if local else configured}:{p}"], "labels": {"service": s}}
     for s, p in SERVICE_PORTS.items()], indent=2) + "\n")
(targets / "core" / "core.json").write_text(json.dumps(
    [{"targets": ["resilience-core:8600"], "labels": {"service": "resilience_core"}}], indent=2) + "\n")
print(f"prometheus targets -> {'compose service names' if local else configured} (PLATFORM_HOST={configured or 'unset'})")
