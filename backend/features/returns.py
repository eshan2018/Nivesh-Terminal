"""The close-price series feature (L6, doc 08).

This module is the platform's **single decimal→float seam (audit clarification C3)**.
Money and index levels are exact `Decimal` at rest, in the domain, and at the API; a
feature that feeds statistics converts them to `float` exactly once, here, on the way
in. Nothing converts back: a statistical float never becomes money again. Having one
declared boundary rather than many ad-hoc ones is what gives the parity tests
(doc 11) something specific to test.

Three further properties this layer owns:

* **Repository access lives here and only here** (doc 08 / ADR-0014). Engines consume
  the series this module returns; if an engine needs canonical data, that need *is* a
  feature. The CI dependency lint makes the alternative a build failure.
* **Lookahead-freedom is enforced by the framework, not by engine authors.** The
  series admits an observation only if both its `event_time` and its `knowledge_time`
  are at or before `as_of`. The `knowledge_time` half is the one that matters: it is
  what stops a later correction from leaking into a backtest of an earlier date.
  `as_of` is an explicit input — never an ambient clock (principle 11).
* **Versioned and lineage-carrying.** The series pins `FEATURE_VERSION` and the
  reference state in force, and carries a `FeatureRef` naming every observation it
  consumed, so a downstream `AnalyticResult` can resolve to raw records.

**Adjustment (assumption, recorded in the methodology catalog).** `close` is the
adjusted close: the provider is fetched with `auto_adjust=True`, so splits and
dividends are already reflected. The platform does not yet compute its own
adjustment — `CorporateAction` is not an ingested data class in the skeleton — so
this feature *inherits* the vendor's adjustment rather than verifying it.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from backend.domain.market_data.repository import MarketDataRepository
from backend.domain.model.analytics import FeatureRef, ObservationRef
from backend.domain.model.instruments import REFERENCE_VERSION, reference_for
from backend.domain.model.observations import PriceObservation
from backend.domain.model.quantities import IndexLevel, Money, PriceValue
from backend.platform.identifiers import InstrumentId

#: L6's published contract for this feature: instrument + knowledge cutoff -> series.
#: Named so L7 can depend on the *shape* of the feature without importing a repository.
type ClosePriceSeriesProvider = Callable[[InstrumentId, datetime], ClosePriceSeries]

FEATURE_ID = "close_price_series"
FEATURE_VERSION = "close-price-series/v1"

#: The observations behind the series ran under a different pinned reference state
#: than the one in force now, so the value is reproducible but not bit-reproducible
#: against today's reference data (ADR-0017 tiers).
REFERENCE_DRIFT_FLAG = "reference-version-drift"


@dataclass(frozen=True, slots=True)
class PricePoint:
    """One (time, price) pair. `price` is past the C3 seam and therefore a float."""

    event_time: datetime
    price: float


@dataclass(frozen=True, slots=True)
class ClosePriceSeries:
    """A versioned, lineage-carrying close-price series for one instrument.

    Points are ordered by `event_time`, ascending, and contain no observation the
    platform did not know about at `as_of`.

    **Index invariant:** `points[i]` and `lineage.inputs[i]` describe the same
    observation. An engine that identifies a point by position can therefore name the
    canonical fact behind it — which is how a result reports its *contributing* inputs
    rather than its whole scanned set. `input_for` is the supported way to make that
    crossing; a test pins the invariant so it cannot rot silently.
    """

    instrument_id: InstrumentId
    interval: str
    as_of: datetime
    points: tuple[PricePoint, ...]
    quality_flags: tuple[str, ...]
    reference_version: str
    lineage: FeatureRef

    @property
    def feature_id(self) -> str:
        return self.lineage.feature_id

    @property
    def feature_version(self) -> str:
        return self.lineage.feature_version

    def input_for(self, index: int) -> ObservationRef:
        """The canonical observation behind `points[index]` (see the index invariant)."""
        return self.lineage.inputs[index]


def build_close_price_series(
    repository: MarketDataRepository,
    instrument_id: InstrumentId,
    *,
    as_of: datetime,
    interval: str = "1d",
) -> ClosePriceSeries:
    """Build the close-price series an engine consumes.

    `as_of` is the knowledge cutoff *and* the event cutoff: nothing the platform
    learned after `as_of`, and no bar dated after it, enters the series.
    """
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")

    # Resolve reference data first. An instrument the reference state has never heard
    # of is a caller error, not a data condition, and must not be reported as "no data
    # available" — those are different answers to "why is this blank?". Raising here
    # also means the REFERENCE_VERSION pinned below reflects a registry actually
    # consulted, rather than a version asserted without reading anything.
    reference_for(instrument_id)

    observations = _visible_at(
        repository.get_observations(instrument_id, interval=interval), as_of
    )

    points: list[PricePoint] = []
    inputs: list[ObservationRef] = []
    flags: set[str] = set()
    for observation in observations:
        points.append(
            PricePoint(event_time=observation.event_time, price=to_float(observation.close))
        )
        inputs.append(ObservationRef.of(observation))
        flags.update(observation.quality_flags)
        if observation.provenance.reference_version != REFERENCE_VERSION:
            flags.add(REFERENCE_DRIFT_FLAG)

    return ClosePriceSeries(
        instrument_id=instrument_id,
        interval=interval,
        as_of=as_of,
        points=tuple(points),
        quality_flags=tuple(sorted(flags)),
        reference_version=REFERENCE_VERSION,
        lineage=FeatureRef(
            feature_id=FEATURE_ID,
            feature_version=FEATURE_VERSION,
            inputs=tuple(inputs),
            # The call is pinned, not just its inputs: a daily and a weekly series over
            # the same instrument are different features of the same data.
            parameters=(("interval", interval),),
        ),
    )


def close_price_series_provider(
    repository: MarketDataRepository, *, interval: str = "1d"
) -> ClosePriceSeriesProvider:
    """Bind this feature to a repository, yielding a repository-free callable.

    The result is L6's published contract in the form an engine can consume: give it an
    instrument and a knowledge cutoff, get the versioned series. The repository is
    captured here, in the only layer permitted to hold one (doc 08) — so L7 and L9 can
    invoke the feature without ever seeing, importing, or being able to reach a
    repository. Constructor injection, which is how every other seam in this codebase
    already works (ED-011).
    """

    def provide(instrument_id: InstrumentId, as_of: datetime) -> ClosePriceSeries:
        return build_close_price_series(
            repository, instrument_id, as_of=as_of, interval=interval
        )

    return provide


def to_float(price: PriceValue) -> float:
    """**The C3 seam.** The one sanctioned decimal→float conversion, one-way.

    Exposed by name so the boundary is greppable and testable, and so no other layer
    needs to invent its own. There is deliberately no inverse: converting a
    statistical float back into money is forbidden (doc 04 / ADR-0016).
    """
    if isinstance(price, Money):
        return float(price.amount)
    if isinstance(price, IndexLevel):
        return float(price.points)
    raise TypeError(f"not a price quantity: {type(price).__name__}")


def _visible_at(
    observations: tuple[PriceObservation, ...], as_of: datetime
) -> tuple[PriceObservation, ...]:
    """Filter to what was known at `as_of`, ordered by event time.

    The repository deliberately has no as-of query — that machinery is Phase 6 work
    (doc 04) — so the cutoff is applied here, where the feature layer's contract
    already requires it. When the repository gains as-of reads this filter becomes
    redundant rather than wrong.

    **Known limitation of filtering above a latest-version read.** The repository
    returns the *latest* version of each bar. If a bar was later corrected, this sees
    only the correction; when that correction's `knowledge_time` is after `as_of` the
    bar is dropped entirely rather than falling back to the version we did know then.
    That is fail-closed — absence, not a value we could not have seen (principle 13) —
    but it is narrower than a true as-of read, and it resolves when Phase 6 lands.
    """
    visible = [
        observation
        for observation in observations
        if observation.event_time <= as_of and observation.knowledge_time <= as_of
    ]
    return tuple(sorted(visible, key=lambda o: o.event_time))
