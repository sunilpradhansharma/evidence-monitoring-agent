"""Adapter registry: load targets from config and build the right adapter per target.

This is the config→adapter wiring that keeps orchestration target-agnostic (Principle V/X):
``config/targets.yaml`` is the only place targets are declared, and adding one is a config entry
plus an adapter class — no core change. It also owns the deterministic **gating** rule
(``targets_for_persona``): a target is eligible for a question only when it is ``active`` AND it
serves that question's persona. That excludes the conditional Open Evidence target unless it is
both enabled and the persona is PROVIDER (FR-007) — code decides, never the model.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from evidence_monitor.data_access.models import LLMTarget, Persona
from evidence_monitor.llm.adapters.base import LLMAdapter, MockBehavior
from evidence_monitor.llm.adapters.claude_target import ClaudeTargetAdapter
from evidence_monitor.llm.adapters.gemini import GeminiAdapter
from evidence_monitor.llm.adapters.open_evidence import OpenEvidenceAdapter
from evidence_monitor.llm.adapters.openai_gpt4o import OpenAIGpt4oAdapter

# Provider id (structural, content-agnostic) → adapter class. Provider names are not regulated
# content; brand/competitor/indication values never appear here (Principle IV).
_ADAPTER_BY_ID: dict[str, type] = {
    "openai-gpt4o": OpenAIGpt4oAdapter,
    "google-gemini": GeminiAdapter,
    "anthropic-claude-target": ClaudeTargetAdapter,
    "open-evidence": OpenEvidenceAdapter,
}

# Keys present in targets.yaml that are consumed elsewhere (cost.py), not by LLMTarget.
_NON_TARGET_KEYS = ("prices",)


def load_targets(config_path: str | Path) -> list[LLMTarget]:
    """Parse ``config/targets.yaml`` into validated :class:`LLMTarget`s (model ids from config)."""
    raw = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    targets: list[LLMTarget] = []
    for entry in raw.get("targets", []):
        fields = {k: v for k, v in entry.items() if k not in _NON_TARGET_KEYS}
        targets.append(LLMTarget(**fields))
    return targets


def build_adapter(
    target: LLMTarget,
    *,
    mock: bool = False,
    mock_behavior: MockBehavior = MockBehavior.SUCCESS,
    max_attempts: int = 3,
) -> LLMAdapter:
    """Construct the adapter for ``target`` (its model id/params come from the target config)."""
    cls = _ADAPTER_BY_ID.get(target.target_id) or _ADAPTER_BY_ID.get(target.llm_name)
    if cls is None:
        raise ValueError(f"no adapter registered for target {target.target_id!r}")
    return cls(target, mock=mock, mock_behavior=mock_behavior, max_attempts=max_attempts)


def targets_for_persona(targets: list[LLMTarget], persona: Persona) -> list[LLMTarget]:
    """The targets eligible for a persona's question: active AND serving that persona (gating)."""
    return [t for t in targets if t.active and t.serves(persona)]


__all__ = ["build_adapter", "load_targets", "targets_for_persona"]
