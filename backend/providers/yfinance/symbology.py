"""Provisional symbology for the Walking Skeleton's 5 instruments.

Maps Nivesh internal `InstrumentId` -> vendor symbol (ADR-0006: identity is
internal; the vendor symbol is a cross-reference). This is a hand-held provisional
table for the skeleton only; Phase 1 moves symbology into the domain reference/master
(doc 04). The five are chosen to stress identity, currency, and type:

    reliance / tcs / infosys : INR equities
    nifty-50                 : an INDEX (must never be FX-converted, at L4)
    apple                    : a USD equity (exercises the FX path, at L4)
"""
from __future__ import annotations

from backend.platform.identifiers import InstrumentId
from backend.providers.ports.errors import NotAvailable

# Internal id -> vendor symbol.
_SYMBOLOGY: dict[str, str] = {
    "reliance": "RELIANCE.NS",
    "tcs": "TCS.NS",
    "infosys": "INFY.NS",
    "nifty-50": "^NSEI",
    "apple": "AAPL",
}

# The instruments the skeleton knows about, as a stable public tuple.
SKELETON_INSTRUMENTS: tuple[InstrumentId, ...] = tuple(
    InstrumentId(key) for key in _SYMBOLOGY
)


def to_vendor_symbol(instrument_id: InstrumentId) -> str:
    """Resolve an internal id to its vendor symbol, or raise `NotAvailable`."""
    try:
        return _SYMBOLOGY[instrument_id.value]
    except KeyError:
        raise NotAvailable(
            f"instrument '{instrument_id.value}' is not in the skeleton symbology"
        ) from None
