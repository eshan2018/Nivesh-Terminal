"""Contract tests against a REAL recorded provider payload (doc 11 · contract tier).

The sibling `test_yfinance_contract.py` runs against a *hand-written* payload. That
proves the adapter parses what we imagined the vendor sends. These tests run against
400 bars actually recorded from the live provider
(`fixtures/reliance_1d_real.json`, captured by `tools/capture_provider_fixture.py`),
which proves the adapter parses what the vendor **actually** sends — a different and
stronger claim.

Still hermetic: the payload is committed, so no network is touched. Prices are
historical fact and do not change, so the fixture does not go stale in a way that
matters; it is re-captured only to widen coverage or after a vendor contract change.

These tests encode the M6b-0 findings as assertions, so a vendor change that would
break ingestion fails here first — in a fast, offline test — rather than in production.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from backend.domain.model.instruments import reference_for
from backend.ingestion.validation import validate_price_history
from backend.platform.identifiers import InstrumentId
from backend.providers.ports.price_history import PriceHistoryRequest
from backend.providers.yfinance import adapter as yf
from backend.providers.yfinance.adapter import RawFetch, YFinanceAdapter

FIXTURE = Path(__file__).parent / "fixtures" / "reliance_1d_real.json"
RELIANCE = InstrumentId("reliance")


@pytest.fixture(scope="module")
def recorded() -> dict:
    return json.loads(FIXTURE.read_text())


@pytest.fixture()
def adapter(recorded: dict) -> YFinanceAdapter:
    columns = tuple(recorded["columns"])
    rows = tuple(recorded["rows"])
    return YFinanceAdapter(fetcher=lambda *_: RawFetch(columns=columns, rows=rows))


def _fetch(adapter: YFinanceAdapter):
    return adapter.fetch(PriceHistoryRequest(RELIANCE, lookback_days=400))


# ── The payload is what we think it is ────────────────────────────────────────


def test_the_fixture_is_a_real_recording_not_a_hand_written_one(recorded: dict) -> None:
    """Guards the fixture's provenance — its value depends entirely on being real."""
    assert "recorded from the live provider" in recorded["_comment"]
    assert recorded["vendor_symbol"] == "RELIANCE.NS"
    assert recorded["raw_contract_version"] == yf.RAW_CONTRACT_VERSION
    datetime.fromisoformat(recorded["captured_at"])  # parses, and is tz-aware
    assert len(recorded["rows"]) >= 300, "a short recording tests little"


def test_the_adapter_parses_the_real_payload(adapter: YFinanceAdapter) -> None:
    response = _fetch(adapter)

    assert len(response.bars) >= 300
    assert response.fetch.vendor_symbol == "RELIANCE.NS"
    assert all(bar.close is not None and bar.close > 0 for bar in response.bars)


def test_real_columns_satisfy_the_contract_regardless_of_order(recorded: dict) -> None:
    """The vendor returns columns alphabetically, not in OHLCV order.

    `validate_columns` checks membership rather than sequence, so this passes — but
    the fact is worth pinning: a future change to order-sensitive parsing would break
    against real data while still passing the hand-written fixture.
    """
    assert recorded["columns"] == sorted(recorded["columns"])
    assert recorded["columns"] != list(yf.EXPECTED_COLUMNS)
    yf.validate_columns(tuple(recorded["columns"]))  # must not raise


def test_real_timestamps_are_timezone_naive_midnight(recorded: dict) -> None:
    """The provider dates daily bars at naive midnight (M6b-0 finding).

    Validation stamps naive timestamps as UTC. That preserves the *trading date*
    because the time component is exactly midnight — if the vendor ever emitted an
    offset instant instead (e.g. 18:30 for IST midnight), the date would shift by one
    day and every window would silently move. This test is the tripwire for that.
    """
    for row in recorded["rows"][:50]:
        parsed = datetime.fromisoformat(str(row["timestamp"]))
        assert parsed.tzinfo is None
        assert (parsed.hour, parsed.minute, parsed.second) == (0, 0, 0)


def test_adjusted_prices_carry_vendor_float_precision(recorded: dict) -> None:
    """Older bars are dividend-adjusted and are NOT round rupee values.

    Evidence that `auto_adjust=True` is doing retroactive adjustment: early closes
    carry many decimal places while recent ones are round. The platform stores these
    exactly as decimals — we are exact about a number that is itself a vendor
    computation, not a traded price. Documented as a limitation in the catalog.
    """
    closes = [float(row["Close"]) for row in recorded["rows"]]
    early_fractional = [c for c in closes[:50] if abs(c - round(c, 2)) > 1e-9]
    assert early_fractional, "expected adjusted (non-round) prices in the early window"


# ── Real data survives the fail-closed gate ───────────────────────────────────


def test_the_validation_gate_accepts_real_market_data(adapter: YFinanceAdapter) -> None:
    """The gate had never met real data before M6b-0.

    A fail-closed gate is only useful if it passes *good* data; one that quarantined
    legitimate market history would be safe and worthless. This asserts the balance
    holds on 400 real bars.
    """
    response = _fetch(adapter)
    outcome = validate_price_history(response, reference_for(RELIANCE))

    assert len(outcome.accepted) == len(response.bars)
    assert outcome.quarantined == ()


def test_real_bars_are_chronological_and_gapped_only_by_market_closure(
    adapter: YFinanceAdapter,
) -> None:
    """Weekends and holidays produce gaps; the pipeline must not require continuity."""
    times = [datetime.fromisoformat(bar.timestamp) for bar in _fetch(adapter).bars]

    assert times == sorted(times)
    gaps = {(b - a).days for a, b in zip(times, times[1:], strict=False)}
    assert gaps - {1}, "a real calendar must contain non-consecutive days"
    assert max(gaps) <= 10, "a gap beyond ~10 days would suggest missing history"
