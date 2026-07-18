"""The yfinance price-history adapter (L1).

This is the ONLY package where vendor (`yfinance`) code may appear (ADR-0005); the
guardrail in tools/ci enforces that. The adapter:

  1. resolves the canonical `InstrumentId` to a vendor symbol (symbology),
  2. fetches the raw payload via an injectable fetcher (default = live yfinance),
  3. checks the payload against a versioned raw contract (drift -> MalformedPayload),
  4. wraps the result in the vendor-neutral `RawPriceResponse`.

The live fetch (`_default_fetch`) lazily imports `yfinance`/`pandas` so that this
module — and its hermetic contract tests — need neither package installed. Those
dependencies are added when the live path is first exercised (a later milestone);
until then the adapter is proven against recorded fixtures (doc 11 contract tier).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from backend.providers.ports.errors import MalformedPayload, TransientError
from backend.providers.ports.price_history import (
    FetchMetadata,
    PriceHistoryRequest,
    RawBar,
    RawPriceResponse,
)
from backend.providers.yfinance.symbology import to_vendor_symbol

PROVIDER_NAME = "yfinance"

# The raw payload shape this adapter is written against. Bump the version if the
# expected shape changes; unexpected shapes are rejected as drift, not silently used.
RAW_CONTRACT_VERSION = "yfinance-ohlcv/v1"
EXPECTED_COLUMNS: tuple[str, ...] = ("Open", "High", "Low", "Close", "Volume")


@dataclass(frozen=True, slots=True)
class RawFetch:
    """The vendor-seam payload: the columns present and the raw rows.

    `rows` are dicts keyed by the vendor's column names plus a "timestamp" ISO string.
    """

    columns: tuple[str, ...]
    rows: tuple[dict[str, object], ...]


# A fetcher takes (vendor_symbol, lookback_days, interval) and returns a RawFetch.
Fetcher = Callable[[str, int, str], RawFetch]


def validate_columns(columns: tuple[str, ...]) -> None:
    """Raise `MalformedPayload` if any expected OHLCV column is missing (drift)."""
    missing = [c for c in EXPECTED_COLUMNS if c not in columns]
    if missing:
        raise MalformedPayload(
            f"payload missing expected columns {missing} "
            f"(contract {RAW_CONTRACT_VERSION}, got {list(columns)})"
        )


class YFinanceAdapter:
    """A `PriceHistoryPort` backed by yfinance."""

    def __init__(self, fetcher: Fetcher | None = None) -> None:
        self._fetch = fetcher if fetcher is not None else _default_fetch

    def fetch(self, request: PriceHistoryRequest) -> RawPriceResponse:
        symbol = to_vendor_symbol(request.instrument_id)
        raw = self._fetch(symbol, request.lookback_days, request.interval)
        validate_columns(raw.columns)
        bars = tuple(_to_bar(row) for row in raw.rows)
        meta = FetchMetadata(
            provider=PROVIDER_NAME,
            vendor_symbol=symbol,
            interval=request.interval,
            fetched_at=datetime.now(UTC),
            raw_contract_version=RAW_CONTRACT_VERSION,
        )
        return RawPriceResponse(instrument_id=request.instrument_id, bars=bars, fetch=meta)


def _to_bar(row: dict[str, object]) -> RawBar:
    def num(key: str) -> float | None:
        value = row.get(key)
        return None if value is None else float(value)  # type: ignore[arg-type]

    return RawBar(
        timestamp=str(row["timestamp"]),
        open=num("Open"),
        high=num("High"),
        low=num("Low"),
        close=num("Close"),
        volume=num("Volume"),
    )


def _default_fetch(vendor_symbol: str, lookback_days: int, interval: str) -> RawFetch:
    """Live fetch via yfinance. Imported lazily; not exercised by hermetic tests."""
    import yfinance  # noqa: PLC0415  (lazy: keeps the module importable without the dep)

    period = f"{max(lookback_days, 1)}d"
    try:
        frame = yfinance.download(
            vendor_symbol,
            period=period,
            interval=interval,
            auto_adjust=True,
            progress=False,
            threads=False,
        )
    except Exception as exc:  # network / vendor failure -> common taxonomy
        raise TransientError(f"yfinance fetch failed for {vendor_symbol!r}: {exc}") from exc

    if frame is None or getattr(frame, "empty", True):
        # No rows: report an empty-but-well-formed payload; validation happens upstream.
        return RawFetch(columns=EXPECTED_COLUMNS, rows=())

    if hasattr(frame.columns, "get_level_values"):  # yfinance MultiIndex -> flat field names
        frame = frame.copy()
        frame.columns = frame.columns.get_level_values(0)

    columns = tuple(str(c) for c in frame.columns)
    rows: list[dict[str, object]] = []
    for index, record in zip(frame.index, frame.to_dict(orient="records"), strict=True):
        rows.append({"timestamp": index.isoformat(), **record})
    return RawFetch(columns=columns, rows=tuple(rows))
