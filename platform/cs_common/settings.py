"""Platform settings: environment variables (set by compose) over the shared repo-root .env."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PLATFORM_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(PLATFORM_DIR.parent / ".env", ".env"), extra="ignore")

    service_name: str = "gateway"
    cs_token: str = "dev-token"
    protection_mode: str = "cascadeshield"  # none | reactive | cascadeshield
    chaos_enabled: bool = False

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""

    gateway_url: str = "http://localhost:8000"
    student_url: str = "http://localhost:8001"
    orchestrator_url: str = "http://localhost:8002"
    rag_url: str = "http://localhost:8003"
    llm_url: str = "http://localhost:8004"

    llm_backend: str = "ollama"  # ollama | mock
    ollama_url: str = "http://host.docker.internal:11434"
    llm_model: str = "qwen2.5:0.5b"
    llm_timeout_s: float = 20.0
    max_inflight: int = 2  # = OLLAMA_NUM_PARALLEL
    max_queue: int = 40  # forced to 1000 when protection_mode=none
    mock_tokens_per_s: float = 41.0  # aggregate tok/s on the M1, docs/calibration.md

    profile_timeout_s: float = 0.3
    rag_timeout_s: float = 1.0
    quiz_timeout_s: float = 2.0
    rate_limit_per_min: int = 6
    heartbeat_stale_s: float = 10.0

    data_dir: Path = PLATFORM_DIR / "data"
    db_path: Path = PLATFORM_DIR / "data" / "student.db"


settings = Settings()
