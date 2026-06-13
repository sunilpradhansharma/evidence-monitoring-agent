"""Deterministic alerting: code decides whether an alert fires (US4; Principle VIII)."""

from __future__ import annotations

from evidence_monitor.alerts.rules import AlertThresholds, FiredRule, evaluate

__all__ = ["AlertThresholds", "FiredRule", "evaluate"]
