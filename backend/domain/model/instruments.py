"""Instrument reference data (doc 04).

`InstrumentType` is what makes units and valid analytics knowable — in particular
that index levels are unitless points and must never be FX-converted. The type and
currency invariant is enforced in the constructor, so an index carrying a currency
cannot be constructed at all.

**Identity is what this module now claims, and claims are checkable.** Doc 04 states
market context explicitly: an instrument is not a bare string but (Instrument,
Exchange, Currency). So a reference carries a **MIC** exchange code, an optional
**ISIN**, and human **aliases** (ED-017). Two of those are machine-checkable and are
checked here — the MIC's shape, and the ISIN's ISO 6166 check digit, which is what
turns a mistyped identifier into a construction error instead of a plausible wrong
company.

**The registry is data, not code** (`universe.json`, loaded once at import). Doc 15's
fourth sequencing principle is that widening the universe is a data-ops task; if adding
an instrument required editing Python, the architecture would have failed its own test.
The file also carries `reference_version`, so the version and the state it pins travel
together and cannot drift apart.

Phase 1's effective-dated reference/master store (doc 07) is still ahead of this. A
committed seed is the smallest implementation that satisfies the model today; the
*version* concept survives that move unchanged, which is the part that was expensive
to add later.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from backend.domain.model.quantities import Currency
from backend.platform.identifiers import InstrumentId

_SEED_PATH = Path(__file__).with_name("universe.json")


class InstrumentType(StrEnum):
    """What kind of thing this is, which determines its units and valid analytics.

    Doc 04 enumerates the instrument kinds the model must eventually carry — "equity,
    ETF, index, FX pair, bond, rate". Only the kinds the platform actually ingests are
    declared here; the rest arrive with the data classes that need them.
    """

    EQUITY = "EQUITY"
    #: An exchange-traded fund. Priced and traded like an equity, and — decisively for
    #: analytics — it has the same continuous, ownable, total-return price series. A
    #: holder owns units with a market value, which an index level is not.
    #:
    #: **This classification is our own canonical knowledge, not a vendor fact.** The
    #: provider reports `quoteType: EQUITY` for NIFTYBEES (doc 05 finding 9), so no
    #: verification against it is possible and none is claimed (ED-017).
    ETF = "ETF"
    INDEX = "INDEX"


#: Kinds denominated in a currency. An index is the deliberate exception: its levels are
#: unitless points, which is what makes FX-converting one type-impossible (doc 04).
_CURRENCY_DENOMINATED: frozenset[InstrumentType] = frozenset(
    {InstrumentType.EQUITY, InstrumentType.ETF}
)


class UnknownInstrument(LookupError):
    """No reference data exists for the requested instrument."""


def isin_check_digit_valid(isin: str) -> bool:
    """Whether `isin` satisfies the ISO 6166 check digit.

    Twelve characters: a two-letter country prefix, nine alphanumerics, one check
    digit. Letters expand to two-digit numbers (A=10 … Z=35) and the result is
    validated by the Luhn algorithm.

    This is the reason ISIN is worth carrying at all: it is the only identifier in the
    model that is globally unique *and* self-validating, so a transcription error
    becomes a hard failure rather than a number attributed to the wrong company.
    """
    if len(isin) != 12 or not isin[:2].isalpha() or not isin.isalnum() or not isin.isupper():
        return False
    expanded = "".join(
        character if character.isdigit() else str(ord(character) - 55) for character in isin[:11]
    )
    total = 0
    # Double every second digit counting from the right, i.e. the position the check
    # digit would occupy is index 0 of this walk.
    for position, character in enumerate(reversed(expanded)):
        digit = int(character)
        if position % 2 == 0:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return (10 - total % 10) % 10 == int(isin[11])


@dataclass(frozen=True, slots=True)
class InstrumentReference:
    """Canonical attributes of an instrument (vendor-neutral).

    `exchange` is a **MIC** (ISO 10383: `XNSE`, `XBOM`, `XNAS`) — never a vendor venue
    code. Yahoo's `NSI` is translated inside the adapter, because vendor vocabulary does
    not rise above L1 (doc 06 / ADR-0005).

    `isin` is optional: the current provider returns none for ETFs, and absence is an
    honest "not claimed" rather than a claim of absence.

    `aliases` are **fuzzy human search affordances**, deliberately a different thing
    from identifiers. ISIN and the vendor symbol are exact-match cross-references;
    "RIL" is not. Keeping them apart is what stops a later search implementation from
    treating an abbreviation as an identity (ED-017). They are data only — no search
    machinery exists or is implied.
    """

    instrument_id: InstrumentId
    name: str
    type: InstrumentType
    currency: Currency | None
    exchange: str
    isin: str | None = None
    aliases: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        # Stated as a rule over kinds rather than a chain of per-kind branches, so a new
        # instrument kind declares its units once instead of being forgotten here.
        if self.type in _CURRENCY_DENOMINATED and self.currency is None:
            raise ValueError(
                f"{self.instrument_id} is a {self.type.value} and must have a currency"
            )
        if self.type not in _CURRENCY_DENOMINATED and self.currency is not None:
            raise ValueError(
                f"{self.instrument_id} is a {self.type.value}: its levels are unitless "
                "points and must not carry a currency (doc 04 — FX conversion must be "
                "type-impossible)"
            )
        if len(self.exchange) != 4 or not self.exchange.isalnum() or not self.exchange.isupper():
            raise ValueError(
                f"{self.instrument_id}: exchange must be a 4-character MIC "
                f"(ISO 10383), got {self.exchange!r}"
            )
        if self.isin is not None and not isin_check_digit_valid(self.isin):
            raise ValueError(
                f"{self.instrument_id}: {self.isin!r} is not a valid ISIN "
                "(ISO 6166 check digit failed)"
            )


def _load_seed(path: Path) -> tuple[str, dict[str, InstrumentReference]]:
    """Read the committed seed into the in-memory reference state.

    Failures here are startup failures on purpose: a reference state that half-loaded
    would let every layer above compute confidently against a universe that is not the
    one we published.
    """
    document = json.loads(path.read_text())
    registry: dict[str, InstrumentReference] = {}
    for row in document["instruments"]:
        currency = row["currency"]
        reference = InstrumentReference(
            instrument_id=InstrumentId(row["instrument_id"]),
            name=row["name"],
            type=InstrumentType(row["type"]),
            currency=None if currency is None else Currency(currency),
            exchange=row["exchange"],
            isin=row["isin"],
            aliases=tuple(row["aliases"]),
        )
        if reference.instrument_id.value in registry:
            raise ValueError(f"duplicate instrument_id in seed: {reference.instrument_id.value}")
        registry[reference.instrument_id.value] = reference
    return document["reference_version"], registry


#: The pinned version of this reference state (review B1 / lineage tiers). Read from the
#: seed rather than declared here, so the version cannot drift from the data it pins.
REFERENCE_VERSION, _REGISTRY = _load_seed(_SEED_PATH)


def reference_for(instrument_id: InstrumentId) -> InstrumentReference:
    """Return reference data for `instrument_id`, or raise `UnknownInstrument`."""
    try:
        return _REGISTRY[instrument_id.value]
    except KeyError:
        raise UnknownInstrument(
            f"no reference data for instrument {instrument_id.value!r} "
            f"(reference {REFERENCE_VERSION})"
        ) from None


def known_instruments() -> tuple[InstrumentReference, ...]:
    """Every instrument in the current reference state."""
    return tuple(_REGISTRY.values())
