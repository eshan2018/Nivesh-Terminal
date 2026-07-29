"""The adapter's symbology must agree with the canonical seed (M6b-1).

The mapping lives inside the adapter (vendor vocabulary stays at L1) and the reference
state lives in the domain, so the two are separate files that could silently disagree.
At five instruments that was a theoretical risk; at twenty it is the realistic one, and
it is exactly the class of error M6b-1 exists to prevent — an instrument the platform
believes it has, quietly unfetchable, or a symbol fetched for an instrument nobody
declared.

Note which direction each invariant runs. "No orphan mappings" is permanent: a symbol
for an unknown instrument is always a mistake. "Full coverage" is a property of *this*
universe with *one* provider — doc 06 has adapters declare capabilities, so a future
provider that legitimately cannot serve some instrument would relax the second rule
without touching the first.
"""
from __future__ import annotations

import pytest

from backend.domain.model.instruments import known_instruments
from backend.platform.identifiers import InstrumentId
from backend.providers.ports.errors import NotAvailable
from backend.providers.yfinance.symbology import (
    SEEDED_INSTRUMENTS,
    mapped_instrument_ids,
    mic_for_vendor_exchange,
    to_vendor_symbol,
)


def test_no_mapping_names_an_unknown_instrument() -> None:
    known = {reference.instrument_id.value for reference in known_instruments()}
    orphans = set(mapped_instrument_ids()) - known
    assert not orphans, f"symbology maps instruments the seed does not declare: {sorted(orphans)}"


def test_every_seeded_instrument_is_fetchable() -> None:
    unmapped = {reference.instrument_id.value for reference in known_instruments()} - set(
        mapped_instrument_ids()
    )
    assert not unmapped, f"seeded but unfetchable: {sorted(unmapped)}"


def test_vendor_symbols_are_unique() -> None:
    symbols = [to_vendor_symbol(instrument) for instrument in SEEDED_INSTRUMENTS]
    assert len(symbols) == len(set(symbols))


def test_indian_listings_carry_the_exchange_suffix_the_venue_implies() -> None:
    """`.NS` vs `.BO` silently switches exchange, so the suffix must match the MIC.

    A seed claiming XNSE against a `.BO` symbol would produce correct, fully traced
    numbers from the wrong venue.
    """
    for reference in known_instruments():
        symbol = to_vendor_symbol(reference.instrument_id)
        if symbol.startswith("^"):  # an index quote, not a listing
            continue
        if reference.exchange == "XNSE":
            assert symbol.endswith(".NS"), symbol
        elif reference.exchange == "XBOM":
            assert symbol.endswith(".BO"), symbol


def test_vendor_venue_codes_translate_to_the_mics_the_seed_uses() -> None:
    assert mic_for_vendor_exchange("NSI") == "XNSE"
    assert mic_for_vendor_exchange("BSE") == "XBOM"
    # An unrecognized venue resolves to None rather than a guess: reporting "we do not
    # know this venue" is verification; inventing a MIC would defeat it.
    assert mic_for_vendor_exchange("WHATEVER") is None

    translatable = {mic_for_vendor_exchange(code) for code in ("NSI", "BSE", "NMS", "NYQ")}
    seeded = {reference.exchange for reference in known_instruments()}
    assert seeded <= translatable, f"no vendor venue code maps to {sorted(seeded - translatable)}"


def test_an_unmapped_instrument_raises_rather_than_guessing() -> None:
    with pytest.raises(NotAvailable):
        to_vendor_symbol(InstrumentId("not-a-thing"))
