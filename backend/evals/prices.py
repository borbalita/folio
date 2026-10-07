"""USD per million tokens, for estimating eval run cost from returned token usage.

Third-party listings checked 2026-10-06 (OpenAI's own page wasn't consulted). Reports keep
token counts, so cost can be recomputed when prices change.
"""

from __future__ import annotations

from dataclasses import dataclass

PRICES_CHECKED = "2026-10-06"


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    """Reasoning tokens are billed as output."""


PRICES: dict[str, Price] = {
    "gpt-5.5": Price(input=5.00, output=30.00),
    "gpt-5.4-mini": Price(input=0.75, output=4.50),
    "gpt-5.4-nano": Price(input=0.20, output=1.25),
    "gpt-5.6-luna": Price(input=0.20, output=1.20),
    # Checked 2026-10-07, also third-party listings.
    "gpt-6-astra": Price(input=10.00, output=50.00),
    "gpt-6.1-sol": Price(input=2.00, output=10.00),
    "gpt-6-luna": Price(input=0.10, output=0.50),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """None when the model has no listed price."""
    price = PRICES.get(model)
    if price is None:
        return None
    return (input_tokens * price.input + output_tokens * price.output) / 1_000_000
