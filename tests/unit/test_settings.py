"""Settings load + startup credential preflight (FR-032; Principle VI).

The preflight is content-agnostic and value-safe: it reads only whether each required value is
non-blank (never its content) and its error names only the missing ENV VAR (never a value). What
is "required" is derived from which targets are ACTIVE in ``targets.yaml`` plus the always-needed
Claude scorer key. The same ``credential_preflight`` gate backs both the web ``/health`` endpoint
and the CLI ``preflight_or_error`` so a live run submits nothing when a required credential is
missing or empty. Mock runs skip the gate entirely (fully offline).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import pytest

from evidence_monitor import cli
from evidence_monitor.config.settings import (
    Settings,
    apply_credentials_to_environment,
    credential_preflight,
    required_credentials,
)


def _settings(**creds: str) -> Settings:
    """A Settings built from the environment-free baseline plus any explicit credentials."""
    return Settings(_env_file=None, **creds)


@dataclass
class _Target:
    """Minimal stand-in for an LLMTarget (preflight reads only target_id + active)."""

    target_id: str
    active: bool


# The default targets.yaml active set: the three unconditional providers; Open Evidence inactive.
_DEFAULT_ACTIVE = [
    _Target("openai-gpt4o", True),
    _Target("google-gemini", True),
    _Target("anthropic-claude-target", True),
    _Target("open-evidence", False),
]


# --------------------------------------------------------------------------- #
# The shared, active-target-aware gate
# --------------------------------------------------------------------------- #
def test_preflight_lists_every_missing_required_credential():
    missing = credential_preflight(_settings())
    assert set(missing) == {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"}


def test_preflight_passes_when_all_required_present():
    settings = _settings(ANTHROPIC_API_KEY="a", OPENAI_API_KEY="b", GOOGLE_API_KEY="c")
    assert credential_preflight(settings) == []


def test_preflight_reports_only_the_one_that_is_missing():
    settings = _settings(ANTHROPIC_API_KEY="a", GOOGLE_API_KEY="c")  # OPENAI_API_KEY absent
    assert credential_preflight(settings) == ["OPENAI_API_KEY"]


def test_preflight_flags_empty_or_whitespace_value_as_missing():
    # The .env.example copy-paste footgun: a present-but-blank KEY= must still fail (non-empty).
    settings = _settings(ANTHROPIC_API_KEY="a", OPENAI_API_KEY="", GOOGLE_API_KEY="   ")
    assert set(credential_preflight(settings)) == {"OPENAI_API_KEY", "GOOGLE_API_KEY"}


def test_inactive_open_evidence_needs_no_key():
    # Open Evidence inactive (default) → its key is never required, even when unset.
    settings = _settings(ANTHROPIC_API_KEY="a", OPENAI_API_KEY="b", GOOGLE_API_KEY="c")
    assert credential_preflight(settings, targets=_DEFAULT_ACTIVE) == []


def test_activating_open_evidence_requires_its_key():
    # If (and only if) Open Evidence is activated, its key becomes required by the same gate.
    targets = [*_DEFAULT_ACTIVE[:3], _Target("open-evidence", True)]
    settings = _settings(ANTHROPIC_API_KEY="a", OPENAI_API_KEY="b", GOOGLE_API_KEY="c")
    assert credential_preflight(settings, targets=targets) == ["OPENEVIDENCE_API_KEY"]


def test_deactivating_a_target_drops_its_credential_requirement():
    # Deactivate OpenAI → its key is no longer required (config change, no code change).
    targets = [_Target("openai-gpt4o", False), *_DEFAULT_ACTIVE[1:]]
    settings = _settings(ANTHROPIC_API_KEY="a", GOOGLE_API_KEY="c")  # no OpenAI key
    assert credential_preflight(settings, targets=targets) == []


def test_anthropic_scorer_key_required_even_if_claude_target_inactive():
    # Claude is the orchestrator/scorer: its key is required for any live run regardless of the
    # Claude *target* being active.
    targets = [_Target("openai-gpt4o", True), _Target("anthropic-claude-target", False)]
    assert ("anthropic_api_key", "ANTHROPIC_API_KEY") in required_credentials(targets)


# --------------------------------------------------------------------------- #
# .env → os.environ bridge (provider SDKs read os.environ, not the Settings object)
# --------------------------------------------------------------------------- #
@pytest.fixture
def clean_cred_env():
    """Snapshot + clear the credential env vars so each bridge test starts/ends clean."""
    names = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "OPENEVIDENCE_API_KEY"]
    saved = {n: os.environ.get(n) for n in names}
    for n in names:
        os.environ.pop(n, None)
    yield
    for n, v in saved.items():
        if v is None:
            os.environ.pop(n, None)
        else:
            os.environ[n] = v


def test_bridge_copies_dotenv_keys_into_environment(clean_cred_env):
    # The core fix: keys present only in .env (the Settings object) must land in os.environ so the
    # provider SDKs (anthropic.Anthropic()/OpenAI()/genai.Client()) authenticate.
    s = _settings(
        ANTHROPIC_API_KEY="sk-ant-aaaaaaaa", OPENAI_API_KEY="sk-bbbb", GOOGLE_API_KEY="AIzacc"
    )
    applied = apply_credentials_to_environment(s)
    assert set(applied) == {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"}
    assert os.environ["OPENAI_API_KEY"] == "sk-bbbb"
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-aaaaaaaa"


def test_bridge_does_not_overwrite_an_explicitly_exported_key(clean_cred_env):
    os.environ["OPENAI_API_KEY"] = "real-exported-value"
    s = _settings(OPENAI_API_KEY="from-dotenv")
    apply_credentials_to_environment(s)
    assert os.environ["OPENAI_API_KEY"] == "real-exported-value"  # explicit export wins


def test_bridge_replaces_a_blank_exported_key(clean_cred_env):
    os.environ["GOOGLE_API_KEY"] = "   "  # the empty/blank-export footgun
    s = _settings(GOOGLE_API_KEY="AIza-real-value")
    apply_credentials_to_environment(s)
    assert os.environ["GOOGLE_API_KEY"] == "AIza-real-value"


def test_bridge_skips_absent_keys(clean_cred_env):
    s = _settings(ANTHROPIC_API_KEY="sk-ant-aaaaaaaa")  # only one present
    applied = apply_credentials_to_environment(s)
    assert applied == ["ANTHROPIC_API_KEY"]
    assert "OPENAI_API_KEY" not in os.environ


def test_api_keys_are_secretstr_and_never_render_their_value():
    settings = _settings(ANTHROPIC_API_KEY="super-secret-value")
    assert "super-secret-value" not in repr(settings)
    assert "super-secret-value" not in str(settings.anthropic_api_key)


# --------------------------------------------------------------------------- #
# CLI startup gate (preflight_or_error + the run path)
# --------------------------------------------------------------------------- #
def test_cli_preflight_error_is_clear_and_non_secret():
    error = cli.preflight_or_error(_settings(ANTHROPIC_API_KEY="a"))  # missing OPENAI + GOOGLE
    assert error is not None
    assert "OPENAI_API_KEY" in error and "GOOGLE_API_KEY" in error
    assert "submitted" in error  # tells the operator nothing was sent
    assert "a" not in error.split()  # the present secret value never appears


def test_cli_preflight_returns_none_when_all_present():
    settings = _settings(ANTHROPIC_API_KEY="a", OPENAI_API_KEY="b", GOOGLE_API_KEY="c")
    assert cli.preflight_or_error(settings) is None


def test_cli_live_run_exits_nonzero_and_submits_nothing_when_creds_missing(monkeypatch, capsys):
    """A non-mock ``run`` with missing creds exits 1 BEFORE building the store / dispatching."""
    monkeypatch.setattr(cli, "get_settings", lambda: _settings())  # no credentials

    def _boom(*args, **kwargs):  # the store must never be opened on a failed preflight
        raise AssertionError("SqliteStore must not be constructed when preflight fails")

    monkeypatch.setattr(cli, "SqliteStore", _boom)

    code = cli.main(["run"])  # not --mock → live path → preflight gate

    assert code == 1
    err = capsys.readouterr().err
    assert "preflight failed" in err
    assert "ANTHROPIC_API_KEY" in err


def test_cli_mock_run_skips_the_credential_gate(monkeypatch):
    """``run --mock`` is fully offline and must run even with zero credentials present."""
    monkeypatch.setattr(cli, "get_settings", lambda: _settings(EM_DB_PATH=":memory:"))

    calls: dict[str, bool] = {}

    def _fake_cmd_run(settings, store, *, mock, question_filter=None, target_id=None, limit=None):
        calls["ran"] = True
        calls["mock"] = mock

    monkeypatch.setattr(cli, "cmd_run", _fake_cmd_run)

    code = cli.main(["--mock", "run"])

    assert code == 0
    assert calls == {"ran": True, "mock": True}
