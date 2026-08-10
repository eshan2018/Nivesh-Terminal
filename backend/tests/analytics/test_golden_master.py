"""Golden master for `one-year-total-return/v1` (doc 11, B10 — governed provenance).

**Seeding provenance.** A golden captured from first-write code enshrines that code's
bugs as the specification, so doc 11 permits the first golden for an engine only after
the engine has passed its property tests and parity with an independent reference
implementation. That order was followed: `test_one_year_return.py` (27 tests — six
properties, parity over generated series, parity on the irregular cases) was green
before this file existed, and the values below were generated from the code that
passed it. The procedure is recorded in the methodology catalog entry.

**What it guards.** Not correctness — the tests above own that — but *unintended
methodology drift*. If a refactor silently changes the anchor rule, the tolerance, the
tie-break, or the envelope's shape, this fails. Changing it deliberately requires a
`formula_version` bump and review; editing the numbers to match new output without one
is the failure mode the rule exists to prevent.

The comparison is exact, not approximate: same inputs and same versions must produce a
bit-identical result (doc 08 determinism).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from backend.analytics.one_year_return import one_year_return
from backend.domain.model.analytics import ResultStatus
from backend.domain.model.instruments import REFERENCE_VERSION
from backend.domain.model.observations import AuthorityTier, PriceObservation, Provenance
from backend.domain.model.quantities import Currency, Money
from backend.features.returns import build_close_price_series
from backend.platform.identifiers import InstrumentId
from backend.tests.analytics.fakes import FakeRepository

GOLDEN = Path(__file__).parent / "golden" / "one_year_return_v1.json"

RELIANCE = InstrumentId("reliance")
START = datetime(2024, 1, 1, tzinfo=UTC)
AS_OF = datetime(2026, 1, 1, tzinfo=UTC)
COMPUTED_AT = datetime(2026, 1, 1, 6, 30, tzinfo=UTC)
PROVENANCE = Provenance(
    raw_object_key="raw/v1/yfinance/price-history/2025-01/reliance/golden.json",
    provider="yfinance",
    raw_contract_version="yfinance-ohlcv/v1",
    reference_version=REFERENCE_VERSION,
)


def _fixture_series() -> tuple[PriceObservation, ...]:
    """A fixed, deterministic 400-bar series. No randomness, no clock, no fixtures on
    disk — the input is reproducible from this function alone."""
    observations = []
    for day in range(400):
        # A deterministic sawtooth around 1500: varied enough that an off-by-one in the
        # anchor search changes the answer, which is what makes the golden load-bearing.
        amount = Decimal(1500) + Decimal((day * 37) % 211) - Decimal((day * 13) % 97)
        price = Money(amount.quantize(Decimal("0.01")), Currency.INR)
        event_time = START + timedelta(days=day)
        observations.append(
            PriceObservation(
                instrument_id=RELIANCE,
                event_time=event_time,
                knowledge_time=event_time,
                interval="1d",
                open=price,
                high=price,
                low=price,
                close=price,
                volume=Decimal("1000"),
                authority=AuthorityTier.AUTHORITATIVE,
                quality_flags=(),
                provenance=PROVENANCE,
            )
        )
    return tuple(observations)


def _result():
    series = build_close_price_series(
        FakeRepository(_fixture_series()),  # type: ignore[arg-type]
        RELIANCE,
        as_of=AS_OF,
    )
    return one_year_return(series, computed_at=COMPUTED_AT)


def _actual() -> dict[str, object]:
    result = _result()
    assert result.status is ResultStatus.AVAILABLE
    assert result.value is not None
    return {
        "metric_id": result.metric_id,
        "instrument_id": result.instrument_id.value,
        "status": str(result.status),
        # repr, not round(): the golden asserts the exact double, so any change in the
        # order of operations is caught rather than rounded away.
        "value": repr(result.value.value),
        "formula_version": result.formula_version,
        "as_of": result.as_of.isoformat(),
        "computed_at": result.computed_at.isoformat(),
        "quality_flags": list(result.quality_flags),
        "feature_id": result.lineage.features[0].feature_id,
        "feature_version": result.lineage.features[0].feature_version,
        "input_count": len(result.lineage.features[0].inputs),
        "raw_object_keys": list(result.lineage.raw_object_keys()),
    }


def test_the_engine_matches_its_golden_master() -> None:
    assert _actual() == json.loads(GOLDEN.read_text())


def test_the_result_pins_the_current_reference_state() -> None:
    """`reference_version` is asserted against the live constant, not frozen in the golden.

    A golden master guards *methodology* drift (doc 11): if the formula, the ordering or
    the anchor search changed, `value` moves and this test fails. Which reference state
    the run used is lineage, not methodology — and freezing it would mean every seed
    edit re-blessed two goldens, making "widening the universe is a data-ops task"
    (doc 15, principle 4) false in practice.
    """
    assert _result().reference_version == REFERENCE_VERSION
