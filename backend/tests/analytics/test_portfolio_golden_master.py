"""Golden master for `portfolio-risk-return/v1` (doc 11, B10 — governed provenance).

**Seeding provenance.** Doc 11 permits an engine's first golden only after property
tests and reference-implementation parity pass, so a golden can never enshrine a
first-write bug as the specification. That order was followed: `make check` was green at
282 tests — including five properties and parity over generated price paths — with no
golden present, and the values below were generated from the code that had passed.

**What it guards.** Not correctness; the tests above own that. This catches *unintended
methodology drift* — a changed annualization, a switched variance convention, a
reordered weighting, a renamed diagnostic. Changing it deliberately requires a
`formula_version` bump and review. Editing the numbers to match new output without one
is the failure mode B10 exists to prevent.

Comparison is exact: same inputs and versions must produce a bit-identical envelope.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from backend.analytics.portfolio_risk_return import Holding, portfolio_risk_return
from backend.domain.market_data.sqlite_repository import SqliteMarketDataRepository
from backend.domain.model.analytics import ResultStatus
from backend.domain.model.instruments import REFERENCE_VERSION, reference_for
from backend.domain.model.observations import AuthorityTier, PriceObservation, Provenance
from backend.domain.model.quantities import Currency, Money
from backend.features.portfolio_returns import build_aligned_return_matrix
from backend.ingestion.validation import VALIDATION_VERSION
from backend.platform.identifiers import InstrumentId

GOLDEN = Path(__file__).parent / "golden" / "portfolio_risk_return_v1.json"

RELIANCE, TCS = InstrumentId("reliance"), InstrumentId("tcs")
START = datetime(2024, 1, 1, tzinfo=UTC)
AS_OF = datetime(2030, 1, 1, tzinfo=UTC)
COMPUTED_AT = datetime(2026, 7, 22, 12, tzinfo=UTC)
RISK_FREE_RATE = 0.07
PROVENANCE = Provenance(
    raw_object_key="raw/v1/yfinance/price-history/2024-01/portfolio/golden.json",
    provider="yfinance",
    raw_contract_version="yfinance-ohlcv/v1",
    reference_version=REFERENCE_VERSION,
    validation_version=VALIDATION_VERSION,
)


def _prices(seed: int, count: int = 300) -> list[float]:
    """A fixed, deterministic price path. No randomness, no clock, no fixture file.

    Two different sawtooth phases give the holdings genuinely different — and partly
    offsetting — paths, so the portfolio's volatility is not simply either holding's:
    an error in the weighting or covariance path changes the answer.
    """
    return [
        round(1000.0 + ((day * seed) % 47) - ((day * 13) % 29) * 0.5, 4)
        for day in range(count)
    ]


@pytest.fixture()
def repository() -> Iterator[SqliteMarketDataRepository]:
    with SqliteMarketDataRepository() as repo:
        for instrument, seed in ((RELIANCE, 7), (TCS, 11)):
            repo.save_observations([
                _observation(instrument, day, price)
                for day, price in enumerate(_prices(seed))
            ])
        yield repo


def _observation(instrument: InstrumentId, day: int, close: float) -> PriceObservation:
    price = Money(Decimal(str(close)), Currency.INR)
    event_time = START + timedelta(days=day)
    return PriceObservation(
        instrument_id=instrument,
        event_time=event_time,
        knowledge_time=event_time,
        interval="1d",
        open=price, high=price, low=price, close=price,
        volume=Decimal("1000"),
        authority=AuthorityTier.AUTHORITATIVE,
        quality_flags=(),
        provenance=PROVENANCE,
    )


def _result(repository: SqliteMarketDataRepository):
    holdings = [Holding(RELIANCE, 0.6), Holding(TCS, 0.4)]
    matrix = build_aligned_return_matrix(repository, [RELIANCE, TCS], as_of=AS_OF)
    return portfolio_risk_return(
        matrix,
        holdings,
        [reference_for(RELIANCE), reference_for(TCS)],
        risk_free_rate=RISK_FREE_RATE,
        computed_at=COMPUTED_AT,
    )


def _actual(repository: SqliteMarketDataRepository) -> dict[str, object]:
    result = _result(repository)
    assert result.status is ResultStatus.AVAILABLE
    assert result.value is not None
    return {
        "metric_id": result.metric_id,
        "formula_version": result.formula_version,
        "status": str(result.status),
        # repr, not round(): the golden asserts the exact double, so a change in the
        # order of operations is caught rather than rounded away.
        "value": repr(result.value.value),
        "diagnostics": {name: repr(number) for name, number in result.diagnostics},
        "quality_flags": list(result.quality_flags),
        "lineage_parameters": dict(result.lineage.parameters),
        "feature_versions": sorted(f.feature_version for f in result.lineage.features),
        "as_of": result.as_of.isoformat(),
        "computed_at": result.computed_at.isoformat(),
    }


def test_the_engine_matches_its_golden_master(
    repository: SqliteMarketDataRepository,
) -> None:
    assert _actual(repository) == json.loads(GOLDEN.read_text())


def test_the_result_pins_the_current_reference_state(
    repository: SqliteMarketDataRepository,
) -> None:
    """Lineage, not methodology — see the note in `test_golden_master.py`."""
    assert _result(repository).reference_version == REFERENCE_VERSION
