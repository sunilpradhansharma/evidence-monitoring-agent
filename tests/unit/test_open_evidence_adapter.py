"""Unit test for the conditional Open Evidence target: persona/active gating + mock submit.

Open Evidence is PROVIDER-only and inactive by default, so it must be excluded from every run
unless explicitly enabled — its absence never counts against the capture rate (FR-007). Gating is
decided in code (``registry.targets_for_persona``), never by the model.
"""

from __future__ import annotations

from pathlib import Path

from evidence_monitor.data_access.models import LLMTarget, Persona, ResponseStatus
from evidence_monitor.llm.adapters.base import LLMAdapter
from evidence_monitor.llm.adapters.open_evidence import OpenEvidenceAdapter
from evidence_monitor.llm.registry import load_targets, targets_for_persona

TARGETS_YAML = (
    Path(__file__).resolve().parents[2] / "src" / "evidence_monitor" / "config" / "targets.yaml"
)


def _open_evidence(**over: object) -> LLMTarget:
    fields: dict[str, object] = {
        "target_id": "open-evidence",
        "llm_name": "open-evidence",
        "model_version": "open-evidence-v1",
        "personas": [Persona.PROVIDER],
        "active": False,
        "rpm_limit": 0,
    }
    fields.update(over)
    return LLMTarget(**fields)


def test_inactive_open_evidence_is_excluded_for_all_personas():
    targets = load_targets(TARGETS_YAML)  # config ships open-evidence as active: false
    for persona in (Persona.PROSPECT, Persona.PROVIDER, Persona.PATIENT):
        eligible = {t.target_id for t in targets_for_persona(targets, persona)}
        assert "open-evidence" not in eligible


def test_active_open_evidence_is_provider_only():
    targets = [_open_evidence(active=True)]
    assert [t.target_id for t in targets_for_persona(targets, Persona.PROVIDER)] == [
        "open-evidence"
    ]
    assert targets_for_persona(targets, Persona.PROSPECT) == []  # non-provider excluded
    assert targets_for_persona(targets, Persona.PATIENT) == []


def test_mock_submit_succeeds_without_endpoint_or_key():
    adapter = OpenEvidenceAdapter(_open_evidence(active=True), mock=True)
    assert isinstance(adapter, LLMAdapter)
    r = adapter.submit(
        question_text="What is the dosing?", persona=Persona.PROVIDER, system_prompt="sys"
    )
    assert r.status is ResponseStatus.SUCCESS
    assert r.model_version == "open-evidence-v1"
