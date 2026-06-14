"""Unit tests for the deterministic alert rules (US4; Principle VIII — code decides).

Each rule is exercised at and around its boundary, plus the highest-severity WRONG_INDICATION case
and the determinism guarantee (identical inputs → identical output).
"""

from __future__ import annotations

from evidence_monitor.alerts.rules import AlertThresholds, evaluate
from evidence_monitor.data_access.models import (
    AlertRule,
    CitationStatus,
    CompetitivePosition,
    ScoringRecord,
)


def _record(**overrides) -> ScoringRecord:
    base = dict(
        response_id="RESP-1",
        sentiment_score=0.0,
        competitive_position=CompetitivePosition.AMONG_OPTIONS,
        citation_status=CitationStatus.CITED,
        scoring_rationale="generic rationale",
        scorer_model="scorer-model-1",
    )
    base.update(overrides)
    return ScoringRecord(**base)


def _fired(record, **kwargs) -> set[AlertRule]:
    return {f.rule for f in evaluate(record, **kwargs)}


def test_no_rule_fires_for_a_neutral_record():
    assert evaluate(_record()) == []


def test_negative_sentiment_fires_below_threshold_only():
    thresholds = AlertThresholds(negative_sentiment=-0.3)
    assert _fired(_record(sentiment_score=-0.31), thresholds=thresholds) == {
        AlertRule.NEGATIVE_SENTIMENT
    }
    # At the threshold it does NOT fire (strictly below).
    assert _fired(_record(sentiment_score=-0.3), thresholds=thresholds) == set()


def test_not_recommended_position_fires_only_when_not_recommended():
    assert _fired(_record(competitive_position=CompetitivePosition.NOT_RECOMMENDED)) == {
        AlertRule.NOT_RECOMMENDED
    }
    # Any other position does not fire this rule.
    assert AlertRule.NOT_RECOMMENDED not in _fired(
        _record(competitive_position=CompetitivePosition.SECOND_LINE)
    )


def test_wrong_indication_fires_at_highest_severity_only_when_wrong():
    fired = evaluate(_record(citation_status=CitationStatus.WRONG_INDICATION))
    assert [f.rule for f in fired] == [AlertRule.WRONG_INDICATION]
    # A correct (or any non-WRONG) citation status does not fire it.
    assert AlertRule.WRONG_INDICATION not in _fired(_record(citation_status=CitationStatus.PARTIAL))


def test_competitor_higher_fires_only_with_sufficient_margin():
    thresholds = AlertThresholds(competitor_margin=0.3)
    ours = _record(sentiment_score=0.0)
    # Competitor 0.4 above ours (≥ margin) → fires.
    assert AlertRule.COMPETITOR_HIGHER in _fired(
        ours, thresholds=thresholds, competitor_sentiments={"rival": 0.4}
    )
    # Competitor only 0.2 above ours (< margin) → does not fire.
    assert AlertRule.COMPETITOR_HIGHER not in _fired(
        ours, thresholds=thresholds, competitor_sentiments={"rival": 0.2}
    )
    # No competitor data → cannot fire.
    assert AlertRule.COMPETITOR_HIGHER not in _fired(ours, thresholds=thresholds)


def test_multiple_rules_can_fire_together():
    fired = _fired(
        _record(
            sentiment_score=-0.9,
            competitive_position=CompetitivePosition.NOT_RECOMMENDED,
            citation_status=CitationStatus.WRONG_INDICATION,
        )
    )
    assert fired == {
        AlertRule.WRONG_INDICATION,
        AlertRule.NEGATIVE_SENTIMENT,
        AlertRule.NOT_RECOMMENDED,
    }


def test_evaluation_is_deterministic():
    record = _record(sentiment_score=-0.5)
    assert evaluate(record) == evaluate(record)
