"""Tests for the canonical model's structural guarantees (doc 04, ADR-0016)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.model.instruments import (
    REFERENCE_VERSION,
    InstrumentReference,
    InstrumentType,
    UnknownInstrument,
    isin_check_digit_valid,
    known_instruments,
    reference_for,
)
from backend.domain.model.quantities import (
    Currency,
    IndexLevel,
    Money,
    Ratio,
    to_decimal,
)
from backend.platform.identifiers import InstrumentId

# ── Money is never a float ────────────────────────────────────────────────────

def test_money_requires_decimal_and_rejects_float() -> None:
    assert Money(Decimal("100.50"), Currency.INR).amount == Decimal("100.50")
    with pytest.raises(TypeError):
        Money(100.50, Currency.INR)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        IndexLevel(24_500.75)  # type: ignore[arg-type]


def test_to_decimal_avoids_binary_float_artifacts() -> None:
    # Decimal(0.1) would be 0.1000000000000000055511151231257827
    assert to_decimal(0.1) == Decimal("0.1")
    assert to_decimal("100.50") == Decimal("100.50")
    assert to_decimal(Decimal("7")) == Decimal("7")
    with pytest.raises(TypeError):
        to_decimal(True)  # bool is not a quantity


# ── An index can never be FX-converted ────────────────────────────────────────

def test_index_level_has_no_currency_field() -> None:
    level = IndexLevel(Decimal("24500.75"))
    assert not hasattr(level, "currency")


def test_index_reference_may_not_carry_a_currency() -> None:
    with pytest.raises(ValueError, match="INDEX"):
        InstrumentReference(
            InstrumentId("bad-index"), "Bad", InstrumentType.INDEX, Currency.INR, "XNSE"
        )


def test_equity_reference_requires_a_currency() -> None:
    with pytest.raises(ValueError, match="EQUITY"):
        InstrumentReference(InstrumentId("bad-equity"), "Bad", InstrumentType.EQUITY, None, "XNSE")


# ── Identity attributes are checkable, not merely stored (ED-017) ─────────────

def test_exchange_must_be_a_mic_not_a_vendor_venue_code() -> None:
    # "NSI" is Yahoo's code for the NSE. Letting it in here would mean vendor
    # vocabulary had risen above L1 (doc 06) — so the shape is refused.
    for bad in ("NSI", "nse", "XNSEX", ""):
        with pytest.raises(ValueError, match="MIC"):
            InstrumentReference(
                InstrumentId("x"), "X", InstrumentType.EQUITY, Currency.INR, bad
            )


def test_isin_check_digit_accepts_valid_and_rejects_corrupted() -> None:
    assert isin_check_digit_valid("INE002A01018")  # Reliance Industries
    assert isin_check_digit_valid("US0378331005")  # Apple Inc.
    # A single transposed character must fail — that is the whole point of the digit.
    assert not isin_check_digit_valid("INE002A01019")
    assert not isin_check_digit_valid("INE020A01018")
    # Shapes the vendor actually returns for ETFs (doc 05 finding 9).
    assert not isin_check_digit_valid("-")
    assert not isin_check_digit_valid("")


def test_reference_rejects_an_isin_that_fails_its_check_digit() -> None:
    with pytest.raises(ValueError, match="ISIN"):
        InstrumentReference(
            InstrumentId("x"), "X", InstrumentType.EQUITY, Currency.INR, "XNSE", isin="INE002A01019"
        )


# ── Seeded reference state ────────────────────────────────────────────────────

def test_registry_carries_the_skeleton_instruments_forward() -> None:
    refs = {r.instrument_id.value: r for r in known_instruments()}
    # The skeleton's five are kept, not replaced: nifty-50 is the index that must never
    # be FX-converted or held, and apple is the USD holding that makes the portfolio
    # engine's mixed-currency refusal reachable. Dropping them would delete coverage.
    assert {"reliance", "tcs", "infosys", "nifty-50", "apple"} <= set(refs)
    assert refs["nifty-50"].type is InstrumentType.INDEX
    assert refs["nifty-50"].currency is None
    assert refs["apple"].currency is Currency.USD
    assert refs["apple"].exchange == "XNAS"
    assert refs["reliance"].currency is Currency.INR
    assert refs["reliance"].exchange == "XNSE"


def test_reference_version_is_pinned() -> None:
    assert REFERENCE_VERSION == "instrument-reference/v2"


def test_unknown_instrument_raises() -> None:
    with pytest.raises(UnknownInstrument):
        reference_for(InstrumentId("not-a-thing"))


# ── A quantity is always a number (M6b-2 backstop) ────────────────────────────

def test_money_and_index_levels_must_be_finite() -> None:
    """`Decimal("NaN")` is a valid Decimal — which is why the type check was not enough.

    The L3 gate is what *handles* a non-finite vendor value (it quarantines the bar with
    a reason). This is the backstop beneath it: any path that bypasses the gate fails
    loudly rather than writing a number-shaped non-number into the canonical model.
    """
    for bad in ("NaN", "Infinity", "-Infinity"):
        with pytest.raises(ValueError, match="finite"):
            Money(Decimal(bad), Currency.INR)
        with pytest.raises(ValueError, match="finite"):
            IndexLevel(Decimal(bad))
    assert Money(Decimal("1.5"), Currency.INR).amount == Decimal("1.5")


def test_to_decimal_refuses_non_finite_inputs() -> None:
    for bad in (float("nan"), float("inf"), float("-inf"), "NaN"):
        with pytest.raises(ValueError, match="finite"):
            to_decimal(bad)


def test_a_ratio_is_never_nan() -> None:
    """An incomputable result is `Unavailable` with a reason, never a NaN value.

    A NaN ratio would travel as an AVAILABLE metric, fully traced, and render to an
    investor as though it were a measurement.
    """
    with pytest.raises(ValueError, match="finite"):
        Ratio(float("nan"))
    with pytest.raises(ValueError, match="finite"):
        Ratio(float("inf"))
    assert Ratio(0.05).value == 0.05
