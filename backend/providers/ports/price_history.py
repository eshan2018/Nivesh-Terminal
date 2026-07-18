"""The `PriceHistoryPort` contract (doc 06).

Inputs are canonical requests (an `InstrumentId` — never a vendor symbol; the
adapter resolves symbology). Outputs are a vendor-neutral raw response: verbatim
bars plus fetch metadata, ready for L2 raw capture and L3/L4 validation and
normalization. No vendor DTO ever crosses this boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from backend.platform.identifiers import InstrumentId


@dataclass(frozen=True, slots=True)
class PriceHistoryRequest:
    """A canonical request for an instrument's price history."""

    instrument_id: InstrumentId
    lookback_days: int
    interval: str = "1d"  # "1d" (daily) or "1wk" (weekly)

    _INTERVALS = ("1d", "1wk")

    def __post_init__(self) -> None:
        if self.lookback_days <= 0:
            raise ValueError("lookback_days must be positive")
        if self.interval not in self._INTERVALS:
            raise ValueError(f"interval must be one of {self._INTERVALS}")


@dataclass(frozen=True, slots=True)
class RawBar:
    """One raw OHLCV bar as delivered by the provider (pre-validation, pre-normalization).

    Values are kept as the provider gave them; units/currency/decimals are assigned
    later, at normalization (L4). `timestamp` is the bar's ISO-8601 date/time.
    """

    timestamp: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None


@dataclass(frozen=True, slots=True)
class FetchMetadata:
    """Provenance for a fetch — the seed of every lineage chain (doc 05)."""

    provider: str
    vendor_symbol: str
    interval: str
    fetched_at: datetime
    raw_contract_version: str


@dataclass(frozen=True, slots=True)
class RawPriceResponse:
    """A provider-neutral price-history response for one instrument."""

    instrument_id: InstrumentId
    bars: tuple[RawBar, ...]
    fetch: FetchMetadata


@runtime_checkable
class PriceHistoryPort(Protocol):
    """The interface every price-history provider adapter must satisfy."""

    def fetch(self, request: PriceHistoryRequest) -> RawPriceResponse:
        """Fetch price history for `request`, or raise a `ProviderError` (see errors)."""
        ...
