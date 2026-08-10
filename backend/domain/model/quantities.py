"""Canonical quantity value types (doc 04, ADR-0016).

Two rules are enforced *structurally*, not by convention:

* **Money is never a float.** `Money.amount` must be a `Decimal`; passing a float
  raises. Binary floating point cannot represent money exactly, so the type makes
  float-money unrepresentable rather than merely discouraged.
* **Index levels are unitless points and cannot be FX-converted.** `IndexLevel`
  has no currency field at all, so there is no currency to convert — the prototype's
  index-inflation bug is type-impossible here, exactly as doc 04 requires.
* **A quantity is always a number.** `Decimal("NaN")` and `Decimal("Infinity")` are
  perfectly valid decimals, so "it is a Decimal" was never the same as "it is a
  quantity". A non-finite price is refused at construction (M6b-2).

  The gate at L3 is what *handles* a non-finite vendor value — it quarantines the bar
  with a reason, which is the correct, retainable outcome for bad input data. This guard
  is the backstop beneath it: it makes any path that bypasses the gate fail loudly
  instead of writing a number-shaped non-number into the canonical model.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class Currency(StrEnum):
    """Currencies the skeleton handles. Extended as markets are added."""

    INR = "INR"
    USD = "USD"


def to_decimal(value: float | int | str | Decimal) -> Decimal:
    """Convert a raw provider numeric into an exact `Decimal`.

    This is the sanctioned raw→canonical numeric boundary (L4). Floats are routed
    through `str()` so the decimal matches the vendor's printed representation
    rather than the binary-float artifact (`Decimal(0.1)` would be
    `0.1000000000000000055511151231257827`).

    Note this is *not* the C3 decimal→float seam: that seam is money→float at
    feature-layer ingress (L6) for statistics, and converting those statistical
    floats back into money is forbidden.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):  # bool is an int subclass; never a quantity
        raise TypeError("bool is not a valid quantity value")
    converted = Decimal(str(value))
    if not converted.is_finite():
        raise ValueError(f"quantity must be a finite number, got {value!r}")
    return converted


@dataclass(frozen=True, slots=True)
class Money:
    """An exact monetary amount in an explicit currency."""

    amount: Decimal
    currency: Currency

    def __post_init__(self) -> None:
        if isinstance(self.amount, bool) or not isinstance(self.amount, Decimal):
            raise TypeError(
                f"Money.amount must be a Decimal, got {type(self.amount).__name__} "
                "(money is never a float — ADR-0016)"
            )
        if not isinstance(self.currency, Currency):
            raise TypeError("Money.currency must be a Currency")
        if not self.amount.is_finite():
            raise ValueError(f"Money.amount must be finite, got {self.amount}")


@dataclass(frozen=True, slots=True)
class Ratio:
    """A unitless statistical quantity — a return, a volatility, a Sharpe ratio.

    Deliberately a `float`, and deliberately *not* money. ADR-0016 permits binary
    floating point for statistical quantities precisely because they are not
    monetary: a ratio has no currency to be exact in. The type exists so a bare
    number never crosses a layer boundary (doc 04) and so that a ratio can never be
    mistaken for — or converted back into — money, which C3 forbids.
    """

    value: float

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, float):
            raise TypeError(
                f"Ratio.value must be a float, got {type(self.value).__name__} "
                "(ratios are statistical quantities, not money — ADR-0016)"
            )
        # A NaN ratio is how "we could not compute this" disguises itself as an answer.
        # Absence is expressed by `AnalyticResult.unavailable`, never by a non-number.
        if not math.isfinite(self.value):
            raise ValueError(
                f"Ratio.value must be finite, got {self.value} — an incomputable result "
                "is Unavailable with a reason, never a number-shaped non-number"
            )


@dataclass(frozen=True, slots=True)
class IndexLevel:
    """An index level in unitless points. Deliberately carries no currency."""

    points: Decimal

    def __post_init__(self) -> None:
        if isinstance(self.points, bool) or not isinstance(self.points, Decimal):
            raise TypeError(
                f"IndexLevel.points must be a Decimal, got {type(self.points).__name__}"
            )
        if not self.points.is_finite():
            raise ValueError(f"IndexLevel.points must be finite, got {self.points}")


# The value a price can take. An index price can never be treated as money.
PriceValue = Money | IndexLevel
