"""Token + cost accounting tests."""

from __future__ import annotations

import pytest

from evidence_monitor.observability.cost import CostTracker, TokenPrice


def test_accumulates_tokens_and_cost_from_config_prices():
    tracker = CostTracker(prices={"provider-a": TokenPrice(input_per_1k=1.0, output_per_1k=2.0)})
    inc = tracker.record("provider-a", input_tokens=1000, output_tokens=500)
    assert tracker.total_tokens == 1500
    assert inc == pytest.approx(1.0 + 1.0)  # 1k in @1.0 + 0.5k out @2.0
    assert tracker.est_cost == pytest.approx(2.0)


def test_unknown_target_contributes_tokens_but_zero_cost():
    tracker = CostTracker()
    tracker.record("mystery", input_tokens=100, output_tokens=100)
    assert tracker.total_tokens == 200
    assert tracker.est_cost == 0.0


def test_negative_tokens_rejected():
    with pytest.raises(ValueError):
        CostTracker().record("x", input_tokens=-1)


def test_over_budget_flips_at_threshold():
    tracker = CostTracker()
    tracker.record("x", input_tokens=900, output_tokens=0)
    assert tracker.over_budget(1000) is False
    tracker.record("x", input_tokens=100, output_tokens=0)
    assert tracker.over_budget(1000) is True
