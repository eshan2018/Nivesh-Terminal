"""The validation gate (L3, doc 05).

**Fail-closed (principle 13).** A bar failing a *hard* check is quarantined with a
reason and does not proceed to normalization — analytics see absence, never bad
data. A bar failing a *soft* check proceeds carrying a quality flag that travels
with it. Nothing is ever silently dropped or silently repaired: every input bar
appears in exactly one of `accepted` or `quarantined`.

Checks implemented (doc 05 validation policy):

* **Schema** — required OHLC fields present; timestamp parseable.
* **Range & sanity** — prices > 0, volume non-negative, OHLC internally consistent,
  and the instrument's type/currency invariant holds (an index must be unitless
  points, so it can never be FX-converted).
* **Continuity** — duplicate bars are hard failures; a stale (unchanged) series and
  unexplained jumps raise soft quality flags. Jumps are soft here because no
  `CorporateAction` data exists yet to explain them (that arrives with corporate
  actions); the flag travels with the data rather than discarding it.

Cross-source corroboration is not implemented: it requires a second provider, which
the architecture defers to Phase 5.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from backend.domain.model.instruments import InstrumentReference, InstrumentType
from backend.providers.ports.price_history import RawBar, RawPriceResponse

# Soft quality flags (travel with accepted data).
FLAG_STALE_SERIES = "stale-series"
FLAG_UNEXPLAINED_JUMP = "unexplained-jump"

# A close-to-close move beyond this is flagged as unexplained (no corporate actions yet).
JUMP_THRESHOLD = 0.5


@dataclass(frozen=True, slots=True)
class ValidatedBar:
    """A bar that passed the gate, with any soft quality flags it earned."""

    bar: RawBar
    event_time: datetime
    quality_flags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class QuarantinedBar:
    """A bar rejected by a hard check, retained with its reasons for data-ops triage."""

    bar: RawBar
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ValidationOutcome:
    accepted: tuple[ValidatedBar, ...]
    quarantined: tuple[QuarantinedBar, ...]
    series_flags: tuple[str, ...]


def validate_price_history(
    response: RawPriceResponse, reference: InstrumentReference
) -> ValidationOutcome:
    """Apply the gate to a raw price-history response."""
    _assert_reference_invariant(reference)

    accepted: list[ValidatedBar] = []
    quarantined: list[QuarantinedBar] = []
    seen_timestamps: set[datetime] = set()

    for bar in response.bars:
        reasons: list[str] = []

        event_time = _parse_timestamp(bar.timestamp, reasons)
        _check_required_fields(bar, reasons)
        _check_ranges(bar, reasons)
        _check_ohlc_consistency(bar, reasons)

        if event_time is not None:
            if event_time in seen_timestamps:
                reasons.append(f"duplicate bar for timestamp {bar.timestamp}")
            else:
                seen_timestamps.add(event_time)

        if reasons:
            quarantined.append(QuarantinedBar(bar=bar, reasons=tuple(reasons)))
            continue

        assert event_time is not None  # no reasons => timestamp parsed
        accepted.append(ValidatedBar(bar=bar, event_time=event_time, quality_flags=()))

    accepted = _flag_unexplained_jumps(accepted)
    series_flags = _series_flags(accepted)

    return ValidationOutcome(
        accepted=tuple(accepted),
        quarantined=tuple(quarantined),
        series_flags=series_flags,
    )


def _assert_reference_invariant(reference: InstrumentReference) -> None:
    """An index must be unitless points; a currency on it would permit FX conversion."""
    if reference.type is InstrumentType.INDEX and reference.currency is not None:
        raise ValueError(
            f"{reference.instrument_id} is an INDEX but carries a currency — "
            "index levels must never be FX-converted (doc 05 range checks)"
        )


def _parse_timestamp(raw: str, reasons: list[str]) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        reasons.append(f"unparseable timestamp {raw!r}")
        return None
    if parsed.tzinfo is None:
        from datetime import UTC

        parsed = parsed.replace(tzinfo=UTC)  # bar dates are UTC-dated by the adapter
    return parsed


def _check_required_fields(bar: RawBar, reasons: list[str]) -> None:
    for field in ("open", "high", "low", "close"):
        if getattr(bar, field) is None:
            reasons.append(f"missing required field {field!r}")


def _check_ranges(bar: RawBar, reasons: list[str]) -> None:
    """Range and finiteness checks.

    **Finiteness is checked first, and explicitly, because comparison cannot do it.**
    Every comparison against NaN is False — `nan <= 0`, `nan < low`, `nan > high` — so a
    NaN price passes a gate built from comparisons without tripping a single one. That is
    not a hypothetical: the vendor returns a NaN-valued bar for the current, still-open
    session, and before this check those bars reached the canonical store, flowed through
    the C3 float seam and produced an `AVAILABLE` metric whose value was NaN (M6b-2).

    A number-shaped non-number is the worst possible result for this platform: it is
    fully traced, passes every downstream type, and renders to an investor as if it were
    a measurement. Fail-closed means it quarantines with a reason (principle 13).
    """
    for field in ("open", "high", "low", "close", "volume"):
        value = getattr(bar, field)
        if value is not None and not math.isfinite(value):
            reasons.append(f"{field} is not a finite number, got {value}")

    for field in ("open", "high", "low", "close"):
        value = getattr(bar, field)
        if value is not None and math.isfinite(value) and value <= 0:
            reasons.append(f"{field} must be > 0, got {value}")
    if bar.volume is not None and math.isfinite(bar.volume) and bar.volume < 0:
        reasons.append(f"volume must be non-negative, got {bar.volume}")


def _check_ohlc_consistency(bar: RawBar, reasons: list[str]) -> None:
    values = (bar.open, bar.high, bar.low, bar.close)
    if None in values:
        return  # already reported as missing
    if not all(math.isfinite(value) for value in values):
        return  # already reported as non-finite; ordering is meaningless against NaN
    assert bar.high is not None and bar.low is not None
    assert bar.open is not None and bar.close is not None
    if bar.high < bar.low:
        reasons.append(f"high {bar.high} is below low {bar.low}")
    if bar.high < max(bar.open, bar.close):
        reasons.append(f"high {bar.high} is below open/close")
    if bar.low > min(bar.open, bar.close):
        reasons.append(f"low {bar.low} is above open/close")


def _flag_unexplained_jumps(accepted: list[ValidatedBar]) -> list[ValidatedBar]:
    """Flag (never drop) close-to-close moves no corporate action can yet explain."""
    ordered = sorted(accepted, key=lambda v: v.event_time)
    flagged: list[ValidatedBar] = []
    previous: float | None = None
    for item in ordered:
        close = item.bar.close
        flags = item.quality_flags
        if previous is not None and close is not None and previous > 0:
            if abs(close / previous - 1.0) > JUMP_THRESHOLD:
                flags = (*flags, FLAG_UNEXPLAINED_JUMP)
        flagged.append(
            ValidatedBar(bar=item.bar, event_time=item.event_time, quality_flags=flags)
        )
        previous = close if close is not None else previous
    return flagged


def _series_flags(accepted: list[ValidatedBar]) -> tuple[str, ...]:
    closes = [v.bar.close for v in accepted if v.bar.close is not None]
    if len(closes) > 1 and len(set(closes)) == 1:
        return (FLAG_STALE_SERIES,)
    return ()
