"""Hermetic tests for the universe verifier's comparison logic (M6b-1).

The tool itself touches the network; its *judgement* must not, or the evidence report
would be produced by untested code. `compare` is pure, so every outcome — including the
ones that are hard to provoke live, like a vendor disagreeing about the exchange — is
exercised here against synthetic vendor answers.

The vendor facts below are shaped from the real ones recorded in
`docs/implementation/05-provider-observations.md` finding 9.
"""
from __future__ import annotations

from dataclasses import replace

from backend.domain.model.instruments import InstrumentReference, InstrumentType
from backend.domain.model.quantities import Currency
from backend.platform.identifiers import InstrumentId
from tools.verify_universe import (
    AGREES,
    CANDIDATE,
    DISAGREES,
    REVIEW,
    UNCORROBORATED,
    VendorFacts,
    compare,
    names_agree,
    verdict,
)

EQUITY = InstrumentReference(
    InstrumentId("reliance"),
    "Reliance Industries Limited",
    InstrumentType.EQUITY,
    Currency.INR,
    "XNSE",
    aliases=("RIL",),
)
ETF = InstrumentReference(
    InstrumentId("nippon-nifty-bees"),
    "Nippon India ETF Nifty 50 BeES",
    InstrumentType.ETF,
    Currency.INR,
    "XNSE",
)
INDEX = InstrumentReference(
    InstrumentId("nifty-50"), "Nifty 50", InstrumentType.INDEX, None, "XNSE"
)

HEALTHY = VendorFacts(
    currency="INR",
    exchange="NSI",
    quote_type="EQUITY",
    long_name="Reliance Industries Limited",
    isin="INE002A01018",
    bar_count=5,
)


def _status(checks, attribute: str) -> str:
    return next(check.status for check in checks if check.attribute == attribute)


def test_a_fully_corroborated_equity_passes() -> None:
    checks = compare(EQUITY, HEALTHY, expected_mic="XNSE")
    assert _status(checks, "currency") == AGREES
    assert _status(checks, "exchange") == AGREES
    assert _status(checks, "type") == AGREES
    assert _status(checks, "name") == AGREES
    assert verdict(checks) == "OK"


def test_an_empty_payload_fails_rather_than_passing_quietly() -> None:
    """Doc 05 finding 5: a wrong or delisted symbol returns no bars and no error.

    This is the silence that would otherwise cost a portfolio a holding, so it must be
    the loudest outcome the tool produces.
    """
    checks = compare(EQUITY, replace(HEALTHY, bar_count=0), expected_mic="XNSE")
    assert _status(checks, "price_history") == DISAGREES
    assert verdict(checks) == "FAILED"


def test_a_wrong_venue_is_caught() -> None:
    facts = replace(HEALTHY, exchange="BSE")
    checks = compare(EQUITY, facts, expected_mic="XBOM")
    assert _status(checks, "exchange") == DISAGREES
    assert verdict(checks) == "FAILED"


def test_an_unknown_vendor_venue_is_uncorroborated_not_a_pass() -> None:
    facts = replace(HEALTHY, exchange="MYSTERY")
    checks = compare(EQUITY, facts, expected_mic=None)
    assert _status(checks, "exchange") == UNCORROBORATED
    assert verdict(checks) == "OK"  # not knowing is not the same as disagreeing


def test_currency_disagreement_is_caught() -> None:
    facts = replace(HEALTHY, currency="USD")
    assert _status(compare(EQUITY, facts, expected_mic="XNSE"), "currency") == DISAGREES


def test_an_etf_is_uncorroborated_on_exactly_the_two_attributes_the_vendor_cannot_serve() -> None:
    facts = VendorFacts(
        currency="INR",
        exchange="NSI",
        quote_type="EQUITY",       # the vendor cannot tell an ETF from an equity
        long_name="Nippon India ETF Nifty 50 BeES",
        isin="-",                  # nor does it hold an ISIN for one
        bar_count=5,
    )
    checks = compare(ETF, facts, expected_mic="XNSE")
    assert _status(checks, "type") == UNCORROBORATED
    assert _status(checks, "isin") == UNCORROBORATED
    # Everything the vendor *can* speak to still has to agree.
    assert _status(checks, "currency") == AGREES
    assert verdict(checks) == "OK"


def test_an_index_claims_no_currency_and_is_recognised_as_an_index() -> None:
    facts = VendorFacts(
        currency="INR", exchange="NSI", quote_type="INDEX", long_name="NIFTY 50", bar_count=5
    )
    checks = compare(INDEX, facts, expected_mic="XNSE")
    assert _status(checks, "currency") == UNCORROBORATED
    assert _status(checks, "type") == AGREES


def test_an_equity_the_vendor_calls_an_index_disagrees() -> None:
    facts = replace(HEALTHY, quote_type="INDEX")
    assert _status(compare(EQUITY, facts, expected_mic="XNSE"), "type") == DISAGREES


def test_an_unclaimed_isin_is_a_candidate_never_an_adopted_fact() -> None:
    """The seed holds no ISIN; the vendor offers one. That is a lead, not evidence.

    Adopting it would make the next run verify the vendor against itself.
    """
    checks = compare(EQUITY, HEALTHY, expected_mic="XNSE")
    isin_check = next(check for check in checks if check.attribute == "isin")
    assert isin_check.status == CANDIDATE
    assert "INE002A01018" in isin_check.detail
    assert "authoritative" in isin_check.detail


def test_a_vendor_isin_that_fails_its_check_digit_is_not_even_a_candidate() -> None:
    facts = replace(HEALTHY, isin="INE002A01019")
    assert _status(compare(EQUITY, facts, expected_mic="XNSE"), "isin") == UNCORROBORATED


def test_a_claimed_isin_that_disagrees_with_the_vendor_fails() -> None:
    claimed = InstrumentReference(
        InstrumentId("larsen-toubro"),
        "Larsen & Toubro Limited",
        InstrumentType.EQUITY,
        Currency.INR,
        "XNSE",
        isin="INE018A01030",
    )
    facts = replace(HEALTHY, isin="INE214T01019", long_name="Larsen & Toubro Limited")
    checks = compare(claimed, facts, expected_mic="XNSE")
    assert _status(checks, "isin") == DISAGREES
    assert verdict(checks) == "FAILED"


# ── Name comparison ───────────────────────────────────────────────────────────

def test_names_ignore_corporate_form_and_punctuation() -> None:
    assert names_agree("Larsen & Toubro Limited", "Larsen & Toubro Ltd")
    assert names_agree("Infosys", "Infosys Limited")
    assert names_agree("ITC Limited", "ITC Ltd.")


def test_names_that_merely_share_a_word_do_not_agree() -> None:
    """The Bajaj pair is the reason this is a prefix rule and not token overlap."""
    assert not names_agree("Bajaj Finance Limited", "Bajaj Finserv Limited")
    assert not names_agree("HDFC Bank Limited", "HDFC Asset Management Company Limited")
    assert not names_agree("Tata Motors Limited", "Tata Consultancy Services Limited")


def test_a_soft_name_mismatch_asks_for_review_rather_than_failing() -> None:
    facts = replace(HEALTHY, long_name="Reliance Power Limited")
    checks = compare(EQUITY, facts, expected_mic="XNSE")
    assert _status(checks, "name") == REVIEW
    assert verdict(checks) == "REVIEW"
