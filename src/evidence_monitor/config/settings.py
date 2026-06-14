"""Application settings sourced entirely from environment variables / `.env`.

Content-agnostic by constitution (Principle IV): no drug, competitor, or
indication names appear here — only generic configuration. Model ids, rate
limits, thresholds, paths, cron, and the token budget are all externalized
(Principle V). API keys are held as ``SecretStr`` so they are never emitted by
logging, reprs, or tracebacks (secrets are never logged).

This module loads configuration and owns the *presence* half of the startup
credential preflight (:func:`credential_preflight`). The CLI (``preflight_or_error``)
and the web ``/health`` endpoint share that gate so a live run submits nothing
when a required credential is missing (FR-032); reachability is probed per target
by the adapter health checks.
"""

from __future__ import annotations

import os
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

    # --- Credentials (held as SecretStr so a value is never emitted by logging, reprs, or
    #     tracebacks; presence + non-emptiness gated by ``credential_preflight``) ---
    anthropic_api_key: SecretStr | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    openai_api_key: SecretStr | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    google_api_key: SecretStr | None = Field(default=None, validation_alias="GOOGLE_API_KEY")
    # Conditional Open Evidence target — only required when that target is ACTIVE in targets.yaml
    # (it is inactive by default, so these stay unset/unrequired).
    openevidence_api_key: SecretStr | None = Field(
        default=None, validation_alias="OPENEVIDENCE_API_KEY"
    )
    openevidence_org_id: SecretStr | None = Field(
        default=None, validation_alias="OPENEVIDENCE_ORG_ID"
    )

    # --- Model + orchestration (ids come only from config, Principle V) ---
    claude_model_id: str = Field(default="claude-opus-4-6", validation_alias="CLAUDE_MODEL_ID")

    # --- NCBI E-utilities (PubMed) — used ONLY by the optional dev target 'provider-evidence-dev'
    #     (a dev stand-in for the future Open Evidence Provider target). NCBI asks callers to
    #     identify via `tool` + `email`; an api_key is optional (higher rate limits only). Basic
    #     access needs no key, so none of these is a required credential. ---
    ncbi_tool: str = Field(default="evidence-monitoring-agent", validation_alias="EM_NCBI_TOOL")
    ncbi_email: str = Field(default="", validation_alias="EM_NCBI_EMAIL")
    ncbi_api_key: SecretStr | None = Field(default=None, validation_alias="NCBI_API_KEY")

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

    # --- Feature flags ---
    # FR-408 human score-override review is scaffolded but OFF by default for the POC.
    enable_score_review: bool = Field(default=False, validation_alias="EM_ENABLE_SCORE_REVIEW")


# Provider credential map: target_id → (settings field, ENV VAR). Structural provider→env wiring
# (content-agnostic — no drug/competitor/indication names). A target's key is required only when
# that target is ACTIVE in targets.yaml; inactive targets (e.g. Open Evidence) need no key (FR-007).
_TARGET_CREDENTIAL: dict[str, tuple[str, str]] = {
    "openai-gpt4o": ("openai_api_key", "OPENAI_API_KEY"),
    "google-gemini": ("google_api_key", "GOOGLE_API_KEY"),
    "anthropic-claude-target": ("anthropic_api_key", "ANTHROPIC_API_KEY"),
    "open-evidence": ("openevidence_api_key", "OPENEVIDENCE_API_KEY"),
}

# Always required for ANY live run: Claude is the orchestrator + scorer, independent of whether the
# Claude *target* is active. Every captured response is scored through this key.
_SCORER_CREDENTIAL: tuple[str, str] = ("anthropic_api_key", "ANTHROPIC_API_KEY")


def _is_blank(secret: SecretStr | None) -> bool:
    """True when a credential is absent OR empty/whitespace. Reads length only — never logs/returns
    the value (so an empty pasted ``KEY=`` is caught without disclosing anything)."""
    return secret is None or not secret.get_secret_value().strip()


def required_credentials(targets: list) -> list[tuple[str, str]]:
    """The (field, ENV VAR) credentials a live run needs: the Claude scorer key plus every ACTIVE
    target's key. Inactive targets contribute nothing. De-duplicated, config-order stable."""
    required: dict[str, str] = {_SCORER_CREDENTIAL[0]: _SCORER_CREDENTIAL[1]}
    for target in targets:
        if getattr(target, "active", False) and target.target_id in _TARGET_CREDENTIAL:
            field, env = _TARGET_CREDENTIAL[target.target_id]
            required[field] = env
    return list(required.items())


def credential_preflight(settings: Settings, targets: list | None = None) -> list[str]:
    """Return the ENV-VAR names of any required credential that is missing OR empty (``[]`` ⇒ all
    present & non-empty).

    "Required" is derived from which targets are ACTIVE in ``targets.yaml`` (plus the always-needed
    Claude orchestrator/scorer key) — so activating/deactivating a target changes the requirement
    with no code change, and an inactive Open Evidence target is never required (FR-007). The check
    reads only whether each value is non-blank; no secret content is read for meaning or logged. The
    web ``/health`` endpoint and the CLI preflight share this gate (FR-032)."""
    if targets is None:
        # Local import keeps this lightweight module free of an import-time dependency on the llm/
        # package (no circular import at module load).
        from evidence_monitor.llm.registry import load_targets

        targets = load_targets(settings.targets_config_path)
    return [
        env for field, env in required_credentials(targets) if _is_blank(getattr(settings, field))
    ]


# Every credential field that a provider SDK expects to read from the process environment. The
# SDKs (anthropic.Anthropic(), openai.OpenAI(), google.genai.Client()) read these env vars; pydantic
# loads them from .env into the Settings OBJECT but does not put them in os.environ — so a .env-only
# setup must be bridged or the SDKs see no key (every live call would fail auth).
_ENV_CREDENTIALS: tuple[tuple[str, str], ...] = (
    ("anthropic_api_key", "ANTHROPIC_API_KEY"),
    ("openai_api_key", "OPENAI_API_KEY"),
    ("google_api_key", "GOOGLE_API_KEY"),
    ("openevidence_api_key", "OPENEVIDENCE_API_KEY"),
)


def apply_credentials_to_environment(settings: Settings) -> list[str]:
    """Bridge ``.env``-loaded credentials into ``os.environ`` so provider SDKs find them.

    pydantic reads ``.env`` into the Settings object only; the SDKs read ``os.environ``. This copies
    each present, non-empty credential into the environment so a ``.env``-only setup actually
    authenticates. An already-set, non-blank environment value is left untouched (an explicitly
    exported real key wins; a blank one is replaced). Returns the env-var names that were applied.
    Secrets are moved by value but never logged."""
    applied: list[str] = []
    for field, env in _ENV_CREDENTIALS:
        secret = getattr(settings, field)
        if secret is None:
            continue
        value = secret.get_secret_value()
        if value and not os.environ.get(env, "").strip():
            os.environ[env] = value
            applied.append(env)
    return applied


@lru_cache
def get_settings() -> Settings:
    """Return a process-cached :class:`Settings` loaded from the environment / `.env`."""
    return Settings()
