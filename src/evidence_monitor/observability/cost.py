"""Token and cost accounting (run summary + token budget).

A small, content-agnostic accumulator: adapters and the scorer report token usage per call; the
orchestrator rolls those into a run total and an estimated dollar cost. Per-target prices come
from config (``config/targets.yaml``), never hard-coded business data — :class:`CostTracker`
takes a price table and applies it. Prices are expressed per 1K tokens.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TokenPrice:
    """USD price per 1,000 tokens for a target, split by direction."""

    input_per_1k: float = 0.0
    output_per_1k: float = 0.0


@dataclass
class CostTracker:
    """Accumulate token counts and estimated cost across a run.

    ``prices`` maps an ``llm_name`` to its :class:`TokenPrice`. Unknown targets contribute
    tokens but zero cost (so accounting never fails on a missing price).
    """

    prices: dict[str, TokenPrice] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    est_cost: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def record(self, llm_name: str, *, input_tokens: int = 0, output_tokens: int = 0) -> float:
        """Record one call's usage and return the incremental cost it added."""
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("token counts must be non-negative")
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        price = self.prices.get(llm_name, TokenPrice())
        increment = (
            input_tokens / 1000 * price.input_per_1k + output_tokens / 1000 * price.output_per_1k
        )
        self.est_cost += increment
        return increment

    def over_budget(self, max_tokens: int) -> bool:
        """Whether the accumulated token total has reached/exceeded ``max_tokens``."""
        return max_tokens > 0 and self.total_tokens >= max_tokens


__all__ = ["CostTracker", "TokenPrice"]
