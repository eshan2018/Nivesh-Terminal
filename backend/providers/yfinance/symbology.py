"""Symbology for the yfinance adapter — internal id ↔ vendor vocabulary.

Two translations, both of which exist so that vendor vocabulary stops here (doc 06 /
ADR-0005):

* **`to_vendor_symbol`** — `InstrumentId` → the vendor's ticker (`RELIANCE.NS`).
* **`mic_for_vendor_exchange`** — the vendor's venue code (`NSI`) → the ISO 10383 **MIC**
  the canonical model speaks (`XNSE`). Without this, verifying that a payload came from
  the venue we claim would mean teaching the domain to read Yahoo's codes.

The mapping itself is data (`symbology.json`) for the same reason the canonical seed is:
adding an instrument must not be a code change (doc 15, sequencing principle 4).
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.platform.identifiers import InstrumentId
from backend.providers.ports.errors import NotAvailable

_SYMBOLOGY_PATH = Path(__file__).with_name("symbology.json")

# Internal id -> vendor symbol.
_SYMBOLOGY: dict[str, str] = json.loads(_SYMBOLOGY_PATH.read_text())["symbols"]

#: The instruments this adapter can address, as a stable public tuple.
SEEDED_INSTRUMENTS: tuple[InstrumentId, ...] = tuple(InstrumentId(key) for key in _SYMBOLOGY)

#: Vendor venue code -> MIC. Yahoo reports a proprietary short code (`NSI` for the
#: National Stock Exchange of India); the canonical model only ever sees the MIC.
#: Unlisted codes resolve to `None` rather than a guess — an unrecognized venue is
#: something to report, not to interpret.
_VENDOR_EXCHANGE_TO_MIC: dict[str, str] = {
    "NSI": "XNSE",  # National Stock Exchange of India
    "BSE": "XBOM",  # BSE Limited
    "BOM": "XBOM",
    "NMS": "XNAS",  # Nasdaq Global Select
    "NGM": "XNAS",  # Nasdaq Global Market
    "NCM": "XNAS",  # Nasdaq Capital Market
    "NYQ": "XNYS",  # New York Stock Exchange
}


def to_vendor_symbol(instrument_id: InstrumentId) -> str:
    """Resolve an internal id to its vendor symbol, or raise `NotAvailable`."""
    try:
        return _SYMBOLOGY[instrument_id.value]
    except KeyError:
        raise NotAvailable(
            f"instrument '{instrument_id.value}' has no yfinance symbol"
        ) from None


def mapped_instrument_ids() -> tuple[str, ...]:
    """Every internal id this adapter holds a symbol for."""
    return tuple(_SYMBOLOGY)


def mic_for_vendor_exchange(vendor_exchange: str) -> str | None:
    """Translate a vendor venue code to its MIC, or `None` if we do not know it."""
    return _VENDOR_EXCHANGE_TO_MIC.get(vendor_exchange)
