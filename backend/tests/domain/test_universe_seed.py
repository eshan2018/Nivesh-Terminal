"""Consistency tests for the committed universe seed (M6b-1, ED-017).

These are hermetic and offline by design (doc 11): they check the seed's *internal*
coherence — the properties that must hold whatever the vendor says. Whether a row
describes the real company is a different question, answered by the deliberate live run
of `tools/verify_universe.py` and its committed report.

The distinction matters. These tests catch the errors we can catch for free on every
commit; the report catches the ones only the outside world can settle.
"""
from __future__ import annotations

from backend.domain.model.instruments import (
    InstrumentType,
    isin_check_digit_valid,
    known_instruments,
)


def test_seed_is_the_agreed_size() -> None:
    # ~15-20 commonly held securities: breadth is explicitly not the goal, so a seed
    # that quietly grew into a screener's universe should fail this and be discussed.
    assert 15 <= len(known_instruments()) <= 20


def test_instrument_ids_are_permanent_readable_slugs() -> None:
    for reference in known_instruments():
        slug = reference.instrument_id.value
        assert slug == slug.lower()
        assert slug.replace("-", "").isalnum(), slug
        assert not slug.startswith("-") and not slug.endswith("-"), slug


def test_instrument_ids_are_unique() -> None:
    slugs = [reference.instrument_id.value for reference in known_instruments()]
    assert len(slugs) == len(set(slugs))


def test_every_instrument_claims_a_venue_and_the_right_units() -> None:
    for reference in known_instruments():
        assert len(reference.exchange) == 4 and reference.exchange.isupper()
        if reference.type is InstrumentType.INDEX:
            assert reference.currency is None
        else:
            assert reference.currency is not None


def test_seeded_isins_are_self_validating_where_present() -> None:
    # Absent is a legitimate state — "not yet claimed from an authoritative source",
    # which is honest — but a *present* ISIN must survive its own check digit.
    for reference in known_instruments():
        if reference.isin is not None:
            assert isin_check_digit_valid(reference.isin), reference.instrument_id.value


def test_aliases_are_unambiguous_across_the_universe() -> None:
    """No alias may point at two instruments.

    India makes this easy to get wrong — 'HDFC' alone once meant HDFC Ltd and now
    reasonably means HDFC Bank; 'Bajaj' means either Finance or Finserv. A duplicated
    alias would hand a future search two answers to one question, so the ambiguity is
    refused in the data rather than resolved in the machinery.
    """
    seen: dict[str, str] = {}
    for reference in known_instruments():
        for alias in reference.aliases:
            assert alias.strip() == alias and alias, reference.instrument_id.value
            key = alias.casefold()
            clash = seen.get(key)
            assert clash is None, f"alias {alias!r}: {clash} vs {reference.instrument_id.value}"
            seen[key] = reference.instrument_id.value


def test_aliases_are_not_identifiers() -> None:
    """Aliases are fuzzy human affordances; identifiers are exact cross-references.

    Keeping an ISIN or a vendor ticker out of `aliases` is what stops a later search
    from treating 'RIL' as identity (ED-017).
    """
    for reference in known_instruments():
        for alias in reference.aliases:
            assert not isin_check_digit_valid(alias)
            assert not alias.endswith((".NS", ".BO"))


def test_the_confusion_pairs_the_milestone_exists_for_are_present() -> None:
    """The seed must actually contain the identity traps, or it proves nothing.

    A universe of unambiguous names would pass every check and demonstrate none of the
    failure modes M6b-1 was built to catch.
    """
    slugs = {reference.instrument_id.value for reference in known_instruments()}
    assert "hdfc-bank" in slugs                      # the merged entity
    assert {"bajaj-finance", "bajaj-finserv"} <= slugs  # the near-identical pair
    assert "larsen-toubro" in slugs                  # the open name/ISIN question


def test_etfs_are_present_and_carry_no_vendor_corroboration() -> None:
    etfs = [r for r in known_instruments() if r.type is InstrumentType.ETF]
    assert len(etfs) >= 2
    for etf in etfs:
        # The vendor reports ETFs as EQUITY and gives them no ISIN, so this attribute is
        # ours alone. Recorded here so the absence of a verification is deliberate.
        assert etf.isin is None
