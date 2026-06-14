"""Settings load + startup credential preflight (FR-032; Principle VI).

The preflight is *presence-only* and content-agnostic: it never reads a secret value, and its
error names only the missing ENV VAR (never a value). The same ``credential_preflight`` gate backs
both the web ``/health`` endpoint and the CLI ``preflight_or_error`` so a live run submits nothing
when a required credential is absent. Mock runs skip the gate entirely (fully offline).
"""

from __future__ import annotations

from evidence_monitor import cli
from evidence_monitor.config.settings import Settings, credential_preflight


def _settings(**creds: str) -> Settings:
    """A Settings built from the environment-free baseline plus any explicit credentials."""
    return Settings(_env_file=None, **creds)


# --------------------------------------------------------------------------- #
# The shared presence gate
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


def test_open_evidence_key_is_not_required():
    # The conditional Open Evidence target is inactive by default, so its key is never required.
    settings = _settings(ANTHROPIC_API_KEY="a", OPENAI_API_KEY="b", GOOGLE_API_KEY="c")
    assert "OPEN_EVIDENCE_API_KEY" not in credential_preflight(settings)


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

    def _fake_cmd_run(settings, store, *, mock, question_filter=None):
        calls["ran"] = True
        calls["mock"] = mock

    monkeypatch.setattr(cli, "cmd_run", _fake_cmd_run)

    code = cli.main(["--mock", "run"])

    assert code == 0
    assert calls == {"ran": True, "mock": True}
