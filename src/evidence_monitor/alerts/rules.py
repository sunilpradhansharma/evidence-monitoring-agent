"""Deterministic alert rules (Principle VIII — Claude scores, CODE decides).

The model never decides an alert; these threshold rules do, in code, and are reproducible for
identical inputs. :func:`evaluate` reads one :class:`ScoringRecord` and returns the rules that
fired (FR-019/020/021). Thresholds are injected from config (``config/settings.py``), never
hard-coded business policy.

Content-agnostic (Principle IV): rules compare scores and enum positions only — no brand,
competitor, or indication names appear here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from evidence_monitor.data_access.models import (
    AlertRule,
    CitationStatus,
    CompetitivePosition,
    ScoringRecord,
)


@dataclass(frozen=True)
class AlertThresholds:
    """Tunable alert thresholds, externalized from code (Principle VIII)."""

    negative_sentiment: float = -0.3
    competitor_margin: float = 0.3


@dataclass(frozen=True)
class FiredRule:
    """One rule that fired, with the non-secret reason to record on the alert."""

    rule: AlertRule
    reason: str


# Module-level default so the public signature has a stable, no-call default (the real thresholds
# are injected from config by the orchestrator).
_DEFAULT_THRESHOLDS = AlertThresholds()


def evaluate(
    record: ScoringRecord,
    *,
    thresholds: AlertThresholds = _DEFAULT_THRESHOLDS,
    competitor_sentiments: Mapping[str, float] | None = None,
) -> list[FiredRule]:
    """Return the alert rules that fire for ``record`` (deterministic; FR-020).

    - WRONG_INDICATION citation → highest-severity alert (FR-021).
    - ``sentiment_score`` below the negative threshold.
    - ``competitive_position`` == NOT_RECOMMENDED.
    - a competitor brand whose sentiment exceeds our therapy's by ≥ the margin, in the same
      response. The POC scoring schema captures a single sentiment (toward our therapy), so
      per-competitor sentiment is supplied separately when available; with none provided this
      rule cannot fire (it is wired for the US2 scoring-schema extension).
    """
    fired: list[FiredRule] = []

    if record.citation_status is CitationStatus.WRONG_INDICATION:
        fired.append(
            FiredRule(AlertRule.WRONG_INDICATION, "response cited the wrong disease/indication")
        )
    if record.sentiment_score < thresholds.negative_sentiment:
        fired.append(
            FiredRule(
                AlertRule.NEGATIVE_SENTIMENT,
                f"sentiment {record.sentiment_score:.2f} below threshold "
                f"{thresholds.negative_sentiment:.2f}",
            )
        )
    if record.competitive_position is CompetitivePosition.NOT_RECOMMENDED:
        fired.append(FiredRule(AlertRule.NOT_RECOMMENDED, "our therapy was marked NOT_RECOMMENDED"))
    if competitor_sentiments:
        for sentiment in competitor_sentiments.values():
            if sentiment - record.sentiment_score >= thresholds.competitor_margin:
                fired.append(
                    FiredRule(
                        AlertRule.COMPETITOR_HIGHER,
                        f"a competitor's sentiment exceeds ours by ≥ "
                        f"{thresholds.competitor_margin:.2f}",
                    )
                )
                break

    return fired


__all__ = ["AlertThresholds", "FiredRule", "evaluate"]
