"""
Shared cost math for the metrics layer — the single source of truth used by
the Stage 1 and Stage 2 calculators and the terminal renderer.

Keeping every cost formula here guarantees the terminal, the API, and the UI
report identical numbers for the same project. Pricing tiers live in config.py
(Anthropic USD-per-million-token rates); Groq model names map to a tier via
MODEL_TIER so the report shows what the same calls would cost in production.
"""

from dataclasses import dataclass, replace

from config import MODEL_TIER, PRICING

# Free-form prose output runs ~40% longer than schema-constrained JSON. Used by
# the naive baselines to model an Opus pipeline that narrates instead of filling
# a strict JSON schema.
PROSE_OUTPUT_MULTIPLIER: float = 1.4


@dataclass(frozen=True)
class UsageTotals:
    """Accumulated token usage across one or more LLM calls in a pipeline step."""

    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    calls: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.thinking_tokens

    def add(self, input_tokens: int, output_tokens: int, thinking_tokens: int) -> "UsageTotals":
        """Return a NEW UsageTotals with one call's usage folded in (immutable)."""
        return replace(
            self,
            input_tokens=self.input_tokens + input_tokens,
            output_tokens=self.output_tokens + output_tokens,
            thinking_tokens=self.thinking_tokens + thinking_tokens,
            calls=self.calls + 1,
        )

    def merge(self, other: "UsageTotals") -> "UsageTotals":
        """Return a NEW UsageTotals combining two accumulators."""
        return UsageTotals(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            thinking_tokens=self.thinking_tokens + other.thinking_tokens,
            calls=self.calls + other.calls,
        )


def tier_for_model(model_name: str) -> str:
    """Map a Groq/Anthropic model name to its pricing tier. Unknown → sonnet."""
    return MODEL_TIER.get(model_name, "sonnet")


def step_cost(input_tokens: int, output_tokens: int, tier: str) -> float:
    """Cost in USD of a call's tokens at the given tier's rates."""
    p = PRICING[tier]
    return (input_tokens / 1_000_000) * p["input"] + (output_tokens / 1_000_000) * p["output"]


def opus_reprice(input_tokens: int, output_tokens: int) -> float:
    """Cost of the SAME token counts priced at Opus rates.

    This is the per-step 'what if we'd used the premium model for this exact work'
    comparison — isolates the cost delta of model choice alone (no architecture change).
    """
    return step_cost(input_tokens, output_tokens, "opus")


def opus_multiplier(actual_cost: float, opus_cost: float) -> float:
    """How many times more the Opus-equivalent costs than the actual call. 0 if actual is 0."""
    if actual_cost <= 0:
        return 0.0
    return round(opus_cost / actual_cost, 1)
