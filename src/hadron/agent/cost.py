"""Model cost constants and computation helpers."""

from __future__ import annotations

# Per-model cost per million tokens: (input, output).
# Use register_model_cost() to add entries at runtime without modifying source.
_MODEL_COSTS: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (0.80, 4.00),
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-20250514": (15.00, 75.00),
    "claude-opus-4-6": (15.00, 75.00),
}
# Fallback for unknown models (use Sonnet pricing)
_DEFAULT_COST = (3.00, 15.00)


def register_model_cost(model: str, input_cost: float, output_cost: float) -> None:
    """Register per-million-token costs for a model.

    Allows adding new models at startup (e.g. from database config)
    without modifying source code.
    """
    _MODEL_COSTS[model] = (input_cost, output_cost)


def _compute_model_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Compute USD cost for a given model and token counts.

    Cache pricing: writes cost 25% more than base input, reads cost 90% less.
    """
    cost_in, cost_out = _MODEL_COSTS.get(model, _DEFAULT_COST)
    cache_write_cost = cost_in * 1.25
    cache_read_cost = cost_in * 0.10
    return (
        input_tokens * cost_in
        + output_tokens * cost_out
        + cache_creation_tokens * cache_write_cost
        + cache_read_tokens * cache_read_cost
    ) / 1_000_000
