from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Load .env from the repo root (one directory above backend/).
_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ROOT_ENV) if _ROOT_ENV.exists() else ".env",
        extra="ignore",
        case_sensitive=False,
    )

    # MongoDB — single source for all stores. Atlas-friendly.
    mongodb_uri: str = Field(
        default="mongodb://localhost:27017", validation_alias="MONGODB_URI"
    )
    # Fall-back alias used by the original docker-compose example.
    mongo_uri: str | None = None
    mongo_db: str = "ims"

    # AI
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-lite"

    # Ingestion / concurrency
    queue_max_size: int = 50_000
    ingest_rate_limit_per_sec: int = 2_000
    worker_batch_size: int = 500
    worker_count: int = 4
    debounce_window_seconds: int = 10
    debounce_signal_threshold: int = 100

    # ML — default points to the repo-root ml/model.pkl so the path holds
    # whether the backend is launched from /backend or the repo root.
    anomaly_model_path: str = str(_ROOT_ENV.parent / "ml" / "model.pkl") if _ROOT_ENV.exists() else "ml/model.pkl"
    anomaly_score_threshold: float = -0.05

    # Metrics
    metrics_print_interval_seconds: int = 5

    @property
    def effective_mongo_uri(self) -> str:
        # Prefer MONGODB_URI; fall back to legacy MONGO_URI if someone still has it set.
        return self.mongodb_uri or self.mongo_uri or "mongodb://localhost:27017"

    @property
    def effective_db_name(self) -> str:
        # If the URI embeds a default DB (Atlas style), let the driver pick it; otherwise mongo_db.
        return self.mongo_db


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
