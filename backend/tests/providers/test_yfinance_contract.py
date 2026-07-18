"""Contract tests for the yfinance adapter (doc 11 · contract tier).

Hermetic: the vendor fetch is replaced by a recorded fixture through the adapter's
fetcher seam, so these tests need no network and neither `yfinance` nor `pandas`.
They prove the adapter satisfies `PriceHistoryPort`, resolves symbology, wraps a
vendor-neutral response, and rejects payload drift.
"""
from __future__ import annotations

import pytest

from backend.platform.identifiers import InstrumentId
from backend.providers.ports.errors import MalformedPayload, NotAvailable
from backend.providers.ports.price_history import PriceHistoryPort, PriceHistoryRequest
from backend.providers.yfinance import adapter as yf
from backend.providers.yfinance.adapter import RawFetch, YFinanceAdapter, validate_columns
from backend.providers.yfinance.symbology import SKELETON_INSTRUMENTS, to_vendor_symbol

# A recorded, well-formed two-bar payload (vendor column names preserved).
_GOOD_ROWS = (
    {"timestamp": "2025-07-01T00:00:00", "Open": 100.0, "High": 101.0,
     "Low": 99.0, "Close": 100.5, "Volume": 1000.0},
    {"timestamp": "2025-07-02T00:00:00", "Open": 100.5, "High": 102.0,
     "Low": 100.0, "Close": 101.5, "Volume": 1200.0},
)


def _good_fetcher(symbol: str, lookback_days: int, interval: str) -> RawFetch:
    return RawFetch(columns=yf.EXPECTED_COLUMNS, rows=_GOOD_ROWS)


def _drifted_fetcher(symbol: str, lookback_days: int, interval: str) -> RawFetch:
    # "Close" has been dropped — a vendor payload change the adapter must reject.
    rows = tuple({k: v for k, v in row.items() if k != "Close"} for row in _GOOD_ROWS)
    return RawFetch(columns=("Open", "High", "Low", "Volume"), rows=rows)


def test_adapter_satisfies_port() -> None:
    assert isinstance(YFinanceAdapter(fetcher=_good_fetcher), PriceHistoryPort)


@pytest.mark.parametrize("instrument", SKELETON_INSTRUMENTS, ids=lambda i: i.value)
def test_fetch_returns_neutral_response(instrument: InstrumentId) -> None:
    adapter = YFinanceAdapter(fetcher=_good_fetcher)
    response = adapter.fetch(PriceHistoryRequest(instrument, lookback_days=365))

    assert response.instrument_id == instrument
    assert len(response.bars) == 2
    assert response.bars[0].close == 100.5
    assert response.fetch.provider == "yfinance"
    assert response.fetch.vendor_symbol == to_vendor_symbol(instrument)
    assert response.fetch.raw_contract_version == yf.RAW_CONTRACT_VERSION
    assert response.fetch.fetched_at.tzinfo is not None  # timezone-aware provenance


def test_unknown_instrument_raises_not_available() -> None:
    adapter = YFinanceAdapter(fetcher=_good_fetcher)
    with pytest.raises(NotAvailable):
        adapter.fetch(PriceHistoryRequest(InstrumentId("does-not-exist"), lookback_days=30))


def test_payload_drift_raises_malformed() -> None:
    adapter = YFinanceAdapter(fetcher=_drifted_fetcher)
    with pytest.raises(MalformedPayload):
        adapter.fetch(PriceHistoryRequest(InstrumentId("apple"), lookback_days=30))


def test_validate_columns_directly() -> None:
    validate_columns(yf.EXPECTED_COLUMNS)  # no raise
    with pytest.raises(MalformedPayload):
        validate_columns(("Open", "High", "Low", "Volume"))


def test_symbology_covers_five_including_index_and_usd() -> None:
    symbols = {i.value: to_vendor_symbol(i) for i in SKELETON_INSTRUMENTS}
    assert symbols == {
        "reliance": "RELIANCE.NS",
        "tcs": "TCS.NS",
        "infosys": "INFY.NS",
        "nifty-50": "^NSEI",  # an index — L4 must not FX-convert it
        "apple": "AAPL",  # a USD equity — L4 exercises the FX path
    }


def test_request_validates_inputs() -> None:
    with pytest.raises(ValueError):
        PriceHistoryRequest(InstrumentId("apple"), lookback_days=0)
    with pytest.raises(ValueError):
        PriceHistoryRequest(InstrumentId("apple"), lookback_days=30, interval="5m")
