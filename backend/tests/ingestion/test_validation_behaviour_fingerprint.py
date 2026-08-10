"""What `price-validation/v1` actually decides — the behaviour the version names.

**This is the test that makes `VALIDATION_VERSION` mean something.** Asserting that the
constant equals a string proves only that someone typed it; it fails when the version is
*bumped*, which is the opposite of the invariant. The invariant we need is:

    changing what the gate decides REQUIRES changing VALIDATION_VERSION

so this file fingerprints the gate's observable verdicts — accept or reject, with which
flags and which class of reason — across every implemented rule and, critically, across
each threshold's boundary. Change any rule and a row flips; the failure message says the
change is a policy change and names the two edits it requires.

Verified to bite: relaxing the finiteness rule, and moving `JUMP_THRESHOLD` from 0.5 to
0.4, both fail here. The second one passed the entire rest of the suite green.

**Adding a new rule means adding a case.** A rule with no case here is a rule this
fingerprint cannot notice, which is the one way the invariant can still be evaded.

Doc 11 governs this as a golden: the fingerprint was captured from code whose behaviour
the rule-level tests in `test_validation.py` already prove correct — it guards drift, it
does not define correctness.
"""
from __future__ import annotations

from datetime import UTC, datetime

from backend.domain.model.instruments import reference_for
from backend.ingestion.validation import VALIDATION_VERSION, validate_price_history
from backend.platform.identifiers import InstrumentId
from backend.providers.ports.price_history import (
    FetchMetadata,
    RawBar,
    RawPriceResponse,
)

REFERENCE = reference_for(InstrumentId("reliance"))

#: Reason strings are prose meant for a human triaging data; the fingerprint keys on the
#: rule *class* instead, so rewording a message is not a policy change.
_REASON_CLASSES = (
    ("finite", "non-finite"),
    ("must be > 0", "non-positive"),
    ("non-negative", "negative-volume"),
    ("below", "ohlc-ordering"),
    ("above", "ohlc-ordering"),
    ("missing required", "missing-field"),
    ("unparseable", "bad-timestamp"),
    ("duplicate", "duplicate-bar"),
)


def _bar(day: int, **overrides: object) -> RawBar:
    values: dict[str, object] = {
        "timestamp": f"2026-07-{day:02d}T00:00:00",
        "open": 100.0, "high": 110.0, "low": 90.0, "close": 100.0, "volume": 1000.0,
    }
    values.update(overrides)
    return RawBar(**values)  # type: ignore[arg-type]


def _response(*bars: RawBar) -> RawPriceResponse:
    return RawPriceResponse(
        instrument_id=InstrumentId("reliance"),
        bars=bars,
        fetch=FetchMetadata(
            provider="yfinance", vendor_symbol="RELIANCE.NS", interval="1d",
            fetched_at=datetime(2026, 7, 30, tzinfo=UTC),
            raw_contract_version="yfinance-ohlcv/v1",
        ),
    )


def _classify(reason: str) -> str:
    for needle, label in _REASON_CLASSES:
        if needle in reason:
            return label
    return f"UNCLASSIFIED:{reason}"


def _verdicts(*bars: RawBar) -> tuple[str, ...]:
    """The gate's decision for each input bar, plus any series-level flags.

    Keyed by object identity rather than timestamp: the duplicate-bar case submits two
    bars sharing a timestamp and they receive *different* verdicts, which a
    timestamp-keyed lookup would silently collapse into one.
    """
    outcome = validate_price_history(_response(*bars), REFERENCE)
    decided: dict[int, str] = {}
    for accepted in outcome.accepted:
        flags = ",".join(sorted(accepted.quality_flags))
        decided[id(accepted.bar)] = f"accept[{flags}]" if flags else "accept"
    for rejected in outcome.quarantined:
        classes = ",".join(sorted({_classify(r) for r in rejected.reasons}))
        decided[id(rejected.bar)] = f"reject[{classes}]"
    per_bar = tuple(decided[id(bar)] for bar in bars)
    return (*per_bar, f"series[{','.join(sorted(outcome.series_flags))}]")


# ── The fingerprint ───────────────────────────────────────────────────────────

#: Every case the rule set is expected to decide, and how it decides it. Captured from
#: behaviour the rule-level tests already prove correct (doc 11 golden provenance).
FINGERPRINT: dict[str, tuple[str, ...]] = {
    "clean bar": ("accept", "series[]"),
    "close is NaN": ("reject[non-finite]", "series[]"),
    "open is +inf": ("reject[non-finite]", "series[]"),
    "close is -inf": ("reject[non-finite]", "series[]"),
    "volume is NaN": ("reject[non-finite]", "series[]"),
    "close is zero": ("reject[non-positive]", "series[]"),
    "close is negative": ("reject[non-positive,ohlc-ordering]", "series[]"),
    "volume is negative": ("reject[negative-volume]", "series[]"),
    "high below low": ("reject[ohlc-ordering]", "series[]"),
    "close missing": ("reject[missing-field]", "series[]"),
    "timestamp unparseable": ("reject[bad-timestamp]", "series[]"),
    "duplicate timestamp": ("accept", "reject[duplicate-bar]", "series[]"),
    # Threshold boundaries — these pin the *value* of JUMP_THRESHOLD, not just the rule.
    "jump just under threshold": ("accept", "accept", "series[]"),
    "jump just over threshold": ("accept", "accept[unexplained-jump]", "series[]"),
    "unchanged series": ("accept", "accept", "series[stale-series]"),
}

CASES: dict[str, tuple[RawBar, ...]] = {
    "clean bar": (_bar(1),),
    "close is NaN": (_bar(1, close=float("nan")),),
    "open is +inf": (_bar(1, open=float("inf")),),
    "close is -inf": (_bar(1, close=float("-inf")),),
    "volume is NaN": (_bar(1, volume=float("nan")),),
    "close is zero": (_bar(1, close=0.0, low=0.0),),
    "close is negative": (_bar(1, close=-5.0),),
    "volume is negative": (_bar(1, volume=-1.0),),
    "high below low": (_bar(1, high=80.0, low=95.0, open=85.0, close=85.0),),
    "close missing": (_bar(1, close=None),),
    "timestamp unparseable": (_bar(1, timestamp="not-a-date"),),
    "duplicate timestamp": (_bar(1), _bar(1)),
    # 100 -> 145 is +45%, below the 50% threshold; 100 -> 155 is +55%, above it.
    "jump just under threshold": (_bar(1), _bar(2, close=145.0, high=160.0)),
    "jump just over threshold": (_bar(1), _bar(2, close=155.0, high=160.0)),
    "unchanged series": (_bar(1), _bar(2)),
}


def test_the_gate_decides_exactly_what_this_version_says_it_decides() -> None:
    """A behaviour change here is a policy change, and policy changes are versioned.

    If this fails, the gate now decides something different from what
    `price-validation/v1` named. That is not a test to "fix": either the change was
    unintended and should be reverted, or it was intended — in which case **bump
    `VALIDATION_VERSION` and update this fingerprint in the same commit**, so every fact
    stamped afterwards is attributable to the new rules.
    """
    actual = {name: _verdicts(*bars) for name, bars in CASES.items()}

    assert actual == FINGERPRINT, (
        f"the validation gate's behaviour changed while VALIDATION_VERSION is still "
        f"{VALIDATION_VERSION!r} — bump the version and update this fingerprint together"
    )


def test_every_case_is_fingerprinted_and_every_fingerprint_has_a_case() -> None:
    """Guards the one way the invariant can still be evaded: an unfingerprinted rule."""
    assert set(CASES) == set(FINGERPRINT)


def test_no_reason_escapes_classification() -> None:
    """An unclassified reason would silently weaken the fingerprint into a pass."""
    for bars in CASES.values():
        assert not any("UNCLASSIFIED" in verdict for verdict in _verdicts(*bars))
