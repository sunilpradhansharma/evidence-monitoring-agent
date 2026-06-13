"""Setup-phase smoke test: the package skeleton imports and settings load from env.

Deeper settings/preflight coverage is a Foundational task (T015/T016); this test
only verifies the Setup phase wiring so the suite is green from the start.
"""

import importlib

import pytest

SUBPACKAGES = [
    "evidence_monitor",
    "evidence_monitor.config",
    "evidence_monitor.config.settings",
    "evidence_monitor.data_access",
    "evidence_monitor.llm",
    "evidence_monitor.llm.adapters",
    "evidence_monitor.question_repo",
    "evidence_monitor.response_repo",
    "evidence_monitor.scoring",
    "evidence_monitor.alerts",
    "evidence_monitor.orchestrator",
    "evidence_monitor.dashboard",
    "evidence_monitor.observability",
]


@pytest.mark.parametrize("module", SUBPACKAGES)
def test_subpackage_imports(module):
    assert importlib.import_module(module) is not None


def test_settings_defaults_load():
    from evidence_monitor.config.settings import Settings

    settings = Settings(_env_file=None)  # ignore any local .env for a deterministic default
    assert settings.claude_model_id  # sourced from env/default, never hard-coded elsewhere
    assert settings.retry_max_attempts == 3
    assert settings.negative_sentiment_threshold == -0.3


def test_settings_read_env_override(monkeypatch):
    from evidence_monitor.config.settings import Settings

    monkeypatch.setenv("EM_MAX_TOKENS_PER_RUN", "12345")
    settings = Settings(_env_file=None)
    assert settings.max_tokens_per_run == 12345


def test_api_keys_are_not_exposed_in_repr(monkeypatch):
    from evidence_monitor.config.settings import Settings

    monkeypatch.setenv("ANTHROPIC_API_KEY", "super-secret-value")
    settings = Settings(_env_file=None)
    assert "super-secret-value" not in repr(settings)
    assert settings.anthropic_api_key is not None
    assert settings.anthropic_api_key.get_secret_value() == "super-secret-value"
