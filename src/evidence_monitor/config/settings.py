"""Application settings sourced entirely from environment variables / `.env`.

Content-agnostic by constitution (Principle IV): no drug, competitor, or
indication names appear here — only generic configuration. Model ids, rate
limits, thresholds, paths, cron, and the token budget are all externalized
(Principle V). API keys are held as ``SecretStr`` so they are never emitted by
logging, reprs, or tracebacks (secrets are never logged).

Note: this module only *loads* configuration. The startup credential preflight
(presence + reachability checks) is a later, Foundational concern and is not
implemented here.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed, env-sourced configuration for the Evidence Monitoring Agent."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Credentials (never logged; presence/reachability validated by the
    #     Foundational preflight, not here) ---
    anthropic_api_key: SecretStr | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    openai_api_key: SecretStr | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    google_api_key: SecretStr | None = Field(default=None, validation_alias="GOOGLE_API_KEY")
    open_evidence_api_key: SecretStr | None = Field(
        default=None, validation_alias="OPEN_EVIDENCE_API_KEY"
    )

    # --- Model + orchestration (ids come only from config, Principle V) ---
    claude_model_id: str = Field(default="claude-opus-4-6", validation_alias="CLAUDE_MODEL_ID")

    # --- Storage + scheduling ---
    db_path: str = Field(default="./data/evidence.db", validation_alias="EM_DB_PATH")
    schedule_cron: str = Field(default="0 2 * * *", validation_alias="EM_SCHEDULE_CRON")
    max_tokens_per_run: int = Field(default=2_000_000, validation_alias="EM_MAX_TOKENS_PER_RUN")

    # --- Targets config + outputs ---
    targets_config_path: str = Field(
        default="./src/evidence_monitor/config/targets.yaml",
        validation_alias="EM_TARGETS_CONFIG",
    )
    output_dir: str = Field(default="./out", validation_alias="EM_OUTPUT_DIR")
    log_level: str = Field(default="INFO", validation_alias="EM_LOG_LEVEL")
    offline_mock: bool = Field(default=False, validation_alias="EM_OFFLINE_MOCK")

    # --- Deterministic alert thresholds (code decides; tunable, Principle VIII) ---
    negative_sentiment_threshold: float = Field(
        default=-0.3, validation_alias="EM_NEGATIVE_SENTIMENT_THRESHOLD"
    )
    competitor_sentiment_margin: float = Field(
        default=0.3, validation_alias="EM_COMPETITOR_SENTIMENT_MARGIN"
    )
    retry_max_attempts: int = Field(default=3, validation_alias="EM_RETRY_MAX_ATTEMPTS")


@lru_cache
def get_settings() -> Settings:
    """Return a process-cached :class:`Settings` loaded from the environment / `.env`."""
    return Settings()
