"""Unit tests for the optional 'provider-evidence-dev' target — a DEV stand-in for the future Open
Evidence Provider target (PubMed E-utilities + Claude synthesis).

Everything is exercised with the E-utilities HTTP calls and the Claude client MOCKED — NO live
network. The tests assert the two-step flow, that PMIDs are recorded in the (immutable) response
provenance, that the target is an active PROVIDER-only target (operator-enabled in config) while a
deliberately-inactive fixture is gated out, that the display name is "Provider evidence (dev)", and
that the target's name is NEVER the literal string "Open Evidence".
"""

from __future__ import annotations

import json
from pathlib import Path

from evidence_monitor.config.settings import Settings
from evidence_monitor.data_access.models import LLMTarget, Persona
from evidence_monitor.llm.adapters.base import MockBehavior
from evidence_monitor.llm.adapters.provider_evidence_dev import (
    DISPLAY_NAME,
    ProviderEvidenceDevAdapter,
)
from evidence_monitor.llm.client import ClaudeClient
from evidence_monitor.llm.registry import build_adapter, load_targets, targets_for_persona
from evidence_monitor.response_repo.schema import FinishReason, ResponseStatus

TARGETS_YAML = (
    Path(__file__).resolve().parents[2] / "src" / "evidence_monitor" / "config" / "targets.yaml"
)

_ESEARCH = json.dumps({"esearchresult": {"count": "3", "idlist": ["111", "222", "333"]}})
_EFETCH = (
    "1. Title A.\nAbstract A: a generic finding relevant to the question.\n\n"
    "2. Title B.\nAbstract B: another generic finding.\n\n"
    "3. Title C.\nAbstract C: a third generic finding.\n"
)


def _dev_target():
    targets = {t.target_id: t for t in load_targets(TARGETS_YAML)}
    return targets["provider-evidence-dev"]


def _settings() -> Settings:
    return Settings(_env_file=None)


def _make_http(calls: list, *, esearch: str = _ESEARCH, efetch: str = _EFETCH, status: int = 200):
    def _get(url: str, params: dict) -> tuple[int, str]:
        calls.append((url, params))
        if status != 200:
            return status, ""
        if "esearch" in url:
            return 200, esearch
        if "efetch" in url:
            return 200, efetch
        return 404, ""

    return _get


def _adapter(http_get, **kw) -> ProviderEvidenceDevAdapter:
    return ProviderEvidenceDevAdapter(
        _dev_target(),
        mock=False,  # exercise the REAL two-step flow (but with injected fakes — no live network)
        claude=ClaudeClient(model_id="test-claude", mock=True),
        http_get=http_get,
        settings=_settings(),
        sleep=lambda _s: None,  # no real backoff sleeps in tests
        max_attempts=2,
        **kw,
    )


# --------------------------------------------------------------------------- #
# Two-step flow + provenance
# --------------------------------------------------------------------------- #
def test_two_step_flow_searches_then_synthesizes():
    calls: list = []
    result = _adapter(_make_http(calls)).submit(
        question_text="What is the dosing guidance for this generic indication?",
        persona=Persona.PROVIDER,
        system_prompt="ignored",
    )
    # Step order: esearch THEN efetch (exactly the two E-utilities calls).
    endpoints = [url.rsplit("/", 1)[-1] for url, _ in calls]
    assert endpoints == ["esearch.fcgi", "efetch.fcgi"]
    # Required NCBI identification params are sent from config on every call.
    for _url, params in calls:
        assert params["tool"] == "evidence-monitoring-agent"
        assert "email" in params
    # The abstracts were passed to Claude for synthesis (mock echoes the instruction).
    assert "Abstract A" in result.response_text
    assert result.status is ResponseStatus.SUCCESS
    assert result.finish_reason is FinishReason.STOP
    # model_version comes from config (content-agnostic provenance label), not a hard-coded literal.
    assert result.model_version == "pubmed-eutils+claude-synthesis"


def test_pmids_recorded_in_response_provenance():
    calls: list = []
    result = _adapter(_make_http(calls)).submit(
        question_text="generic provider question",
        persona=Persona.PROVIDER,
        system_prompt="ignored",
    )
    # Every PMID used is traceable in the immutable response text (a delimited Sources footer).
    for pmid in ("111", "222", "333"):
        assert pmid in result.response_text
    assert "PubMed query: generic provider question" in result.response_text
    assert "PMIDs: 111, 222, 333" in result.response_text


def test_no_results_still_captures_gracefully():
    calls: list = []
    empty = json.dumps({"esearchresult": {"count": "0", "idlist": []}})
    result = _adapter(_make_http(calls, esearch=empty)).submit(
        question_text="no hits question",
        persona=Persona.PROVIDER,
        system_prompt="ignored",
    )
    # esearch only (no efetch when there are no PMIDs); a captured SUCCESS that says so.
    assert [url.rsplit("/", 1)[-1] for url, _ in calls] == ["esearch.fcgi"]
    assert result.status is ResponseStatus.SUCCESS
    assert "No relevant PubMed abstracts were found" in result.response_text
    assert "PMIDs: (none found)" in result.response_text


def test_pubmed_unreachable_fails_gracefully():
    calls: list = []
    result = _adapter(_make_http(calls, status=503)).submit(
        question_text="provider question",
        persona=Persona.PROVIDER,
        system_prompt="ignored",
    )
    # A 5xx is transient → retried; after the budget the record is FAILED and submit never raises
    # (so the run continues). No synthesis happened.
    assert result.status is ResponseStatus.FAILED
    assert result.response_text == ""
    assert len(calls) == 2  # max_attempts=2 esearch attempts, then give up


# --------------------------------------------------------------------------- #
# Config + labelling guarantees
# --------------------------------------------------------------------------- #
def _inactive_fixture_target() -> LLMTarget:
    """A target that is inactive ON PURPOSE — used to cover the inactive-path gating now that the
    dev target itself is active by the operator's config choice."""
    return LLMTarget(
        target_id="inactive-fixture",
        llm_name="inactive-fixture",
        model_version="none",
        personas=[Persona.PROVIDER],
        active=False,
        tos_acknowledged=False,
    )


def test_dev_target_is_active_provider_only():
    # The operator has enabled provider-evidence-dev in config: it is an active, PROVIDER-only
    # target that surfaces like any other active target.
    target = _dev_target()
    assert target.active is True
    assert target.tos_acknowledged is True
    assert target.personas == [Persona.PROVIDER]


def test_inactive_target_is_gated_out():
    # Inactive-path coverage against a deliberately-inactive fixture: persona gating
    # (active AND serves-persona) excludes it from every run, while the active dev target stays in.
    inactive = _inactive_fixture_target()
    assert inactive.active is False
    assert inactive.tos_acknowledged is False
    eligible = targets_for_persona([inactive, _dev_target()], Persona.PROVIDER)
    assert [t.target_id for t in eligible] == ["provider-evidence-dev"]


def test_display_name_is_provider_evidence_dev():
    assert DISPLAY_NAME == "Provider evidence (dev)"
    assert ProviderEvidenceDevAdapter.DISPLAY_NAME == "Provider evidence (dev)"


def test_target_name_is_never_open_evidence():
    target = _dev_target()
    assert target.target_id == "provider-evidence-dev"
    assert target.llm_name == "provider-evidence-dev"
    for label in (target.target_id, target.llm_name, DISPLAY_NAME):
        assert "Open Evidence" not in label


def test_registry_builds_the_dev_adapter():
    adapter = build_adapter(_dev_target(), mock=True, mock_behavior=MockBehavior.SUCCESS)
    assert isinstance(adapter, ProviderEvidenceDevAdapter)
