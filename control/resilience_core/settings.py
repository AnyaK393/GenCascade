"""Control-room settings: the shared .env at the repo root plus control-only overrides."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

# `service` label value -> port (contracts/metrics.md)
SERVICE_PORTS = {
    "gateway": 8000,
    "student": 8001,
    "orchestrator": 8002,
    "curriculum_rag": 8003,
    "llm_inference": 8004,
}
SERVICES = list(SERVICE_PORTS)

# p95 latency SLOs in seconds. Placeholders until docs/calibration.md lands;
# override with CS_SLO_<SERVICE>=<seconds>.
DEFAULT_SLO_S = {
    "gateway": 12.0,
    "student": 0.5,
    "orchestrator": 12.0,
    "curriculum_rag": 1.0,
    "llm_inference": 10.0,
}


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip() or default


@dataclass(frozen=True)
class Settings:
    platform_host: str = _env("PLATFORM_HOST", "localhost")
    control_host: str = _env("CONTROL_HOST", "localhost")
    cs_token: str = _env("CS_TOKEN", "dev-token")
    redis_host: str = _env("REDIS_HOST", _env("PLATFORM_HOST", "localhost"))
    redis_port: int = int(_env("REDIS_PORT", "6379"))
    redis_password: str = _env("REDIS_PASSWORD", "dev-redis")
    prometheus_url: str = _env("PROMETHEUS_URL", "http://localhost:9090")
    core_url: str = _env("CORE_URL", "http://localhost:8600")
    core_port: int = int(_env("CORE_PORT", "8600"))
    loop_s: float = float(_env("CS_LOOP_S", "2"))
    slo_s: dict[str, float] = field(
        default_factory=lambda: {
            s: float(_env(f"CS_SLO_{s.upper()}", str(v))) for s, v in DEFAULT_SLO_S.items()
        }
    )

    def service_url(self, service: str) -> str:
        return f"http://{self.platform_host}:{SERVICE_PORTS[service]}"

    @property
    def control_api(self) -> str:
        return self.service_url("orchestrator")


settings = Settings()
