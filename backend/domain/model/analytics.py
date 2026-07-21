"""The `AnalyticResult` envelope and its lineage structure (doc 04).

**Ownership.** Doc 04 owns this shape as a canonical entity; doc 08 owns how engines
*produce* it and may not alter it (the v2.0 co-ownership resolution). It lives beside
the other canonical vocabulary — as `Money` and `IndexLevel` do — rather than in the
kernel, so doc 04's entities stay in one package.

Three rules are enforced *structurally* here, not by engine-author discipline:

* **No engine returns a bare number** (ADR-0014). The value is a typed Quantity and
  it always arrives wrapped in this envelope.
* **A missing input is `Unavailable` with a reason, never zero** (principle 13). An
  `UNAVAILABLE` result cannot carry a value and an `AVAILABLE` result cannot carry a
  reason — the constructor refuses both, so "return 0.0 when we don't know" is
  unrepresentable rather than merely discouraged.
* **Lineage is a stored structure, not a log** (ADR-0017). `LineageHandle` resolves a
  derived value to the features it consumed, the canonical observations behind them,
  and — through each observation's `Provenance` — the raw object, the provider, and
  the pinned reference version. With `formula_version` on the envelope, that is the
  full chain doc 00 §B5 requires, at the *recomputable* guarantee tier.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from backend.domain.model.observations import PriceObservation, Provenance
from backend.domain.model.quantities import IndexLevel, Money, Ratio
from backend.platform.identifiers import InstrumentId

# Anything an analytic may report as a value. Money and IndexLevel stay decimal;
# Ratio is the statistical float (ADR-0016).
AnalyticValue = Ratio | Money | IndexLevel


class ResultStatus(StrEnum):
    """Whether an analytic produced a value or declined to."""

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class ObservationRef:
    """A canonical observation a feature consumed, and the raw record behind it.

    Both times are carried because both are load-bearing: `event_time` says which bar
    this is, `knowledge_time` says when we learned it — which is what makes the
    lookahead-free claim auditable after the fact rather than merely asserted.
    """

    instrument_id: InstrumentId
    event_time: datetime
    knowledge_time: datetime
    provenance: Provenance

    @classmethod
    def of(cls, observation: PriceObservation) -> ObservationRef:
        """Reference an observation without copying its payload."""
        return cls(
            instrument_id=observation.instrument_id,
            event_time=observation.event_time,
            knowledge_time=observation.knowledge_time,
            provenance=observation.provenance,
        )


@dataclass(frozen=True, slots=True)
class FeatureRef:
    """A feature an analytic consumed, pinned to the version that produced it.

    `parameters` records the arguments the feature was invoked with — interval,
    window length, any future knob. Without them the lineage names the inputs but not
    the *call*, so a reader cannot tell a daily series from a weekly one and cannot
    re-invoke the feature to check the input set was the right one. Kept as sorted
    name/value pairs rather than typed fields so a new feature with different
    parameters needs no change here (ADR-0017's recomputable tier).
    """

    feature_id: str
    feature_version: str
    inputs: tuple[ObservationRef, ...]
    parameters: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class LineageHandle:
    """The resolvable chain from a derived value back to raw records (ADR-0017).

    `features` names everything the engine was *given*; `contributing` names the
    observations that actually determined the value. For a one-year return that is two
    bars out of a multi-hundred-bar series — so the distinction is what keeps a served
    response proportional to the answer rather than to the history behind it
    (PROJECT_CONTEXT §11, Decision 1). Recomputability is unaffected: feature version,
    feature parameters and raw object keys are all still pinned, so the full series can
    be rebuilt and the result re-derived.
    """

    features: tuple[FeatureRef, ...]
    contributing: tuple[ObservationRef, ...] = ()

    def scanned_count(self) -> int:
        """How many observations the features supplied, contributing or not."""
        return sum(len(feature.inputs) for feature in self.features)

    def raw_object_keys(self) -> tuple[str, ...]:
        """Every raw object this value derives from, de-duplicated and ordered.

        The last hop of the lineage chain: these keys address immutable payloads in
        the raw store, which is what makes the value recomputable rather than only
        traceable.
        """
        keys = {
            ref.provenance.raw_object_key
            for feature in self.features
            for ref in feature.inputs
        }
        return tuple(sorted(keys))


@dataclass(frozen=True, slots=True)
class AnalyticResult:
    """The envelope every analytics engine emits — the only thing an engine returns.

    Construct via `available()` or `unavailable()`; the invariants below are what
    make a fabricated zero unrepresentable.
    """

    metric_id: str
    instrument_id: InstrumentId
    status: ResultStatus
    value: AnalyticValue | None
    unavailable_reason: str | None
    formula_version: str
    reference_version: str
    as_of: datetime
    computed_at: datetime
    quality_flags: tuple[str, ...]
    lineage: LineageHandle
    diagnostics: tuple[tuple[str, float], ...] = ()
    """Typed numeric facts about how the value was reached — e.g. how far the anchor
    bar sat from the requested date.

    Separate from `quality_flags` on purpose (PROJECT_CONTEXT §11, Decision 2): a flag
    is an opaque tag you test membership in, and encoding a number inside one forces
    every consumer to string-parse it. Sorted pairs rather than a dict so the envelope
    stays hashable and comparison stays deterministic.
    """

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None or self.computed_at.tzinfo is None:
            raise ValueError("as_of and computed_at must be timezone-aware")
        if self.status is ResultStatus.AVAILABLE:
            if self.value is None:
                raise ValueError("an AVAILABLE result must carry a value")
            if self.unavailable_reason is not None:
                raise ValueError("an AVAILABLE result must not carry an unavailable reason")
        else:
            if self.value is not None:
                raise ValueError(
                    "an UNAVAILABLE result must not carry a value — a missing input is "
                    "absence, never zero (principle 13)"
                )
            if not self.unavailable_reason:
                raise ValueError("an UNAVAILABLE result must state why")

    @classmethod
    def available(
        cls,
        *,
        metric_id: str,
        instrument_id: InstrumentId,
        value: AnalyticValue,
        formula_version: str,
        reference_version: str,
        as_of: datetime,
        computed_at: datetime,
        quality_flags: tuple[str, ...] = (),
        diagnostics: tuple[tuple[str, float], ...] = (),
        lineage: LineageHandle,
    ) -> AnalyticResult:
        """A computed value, with the versions and inputs that produced it."""
        return cls(
            metric_id=metric_id,
            instrument_id=instrument_id,
            status=ResultStatus.AVAILABLE,
            value=value,
            unavailable_reason=None,
            formula_version=formula_version,
            reference_version=reference_version,
            as_of=as_of,
            computed_at=computed_at,
            quality_flags=quality_flags,
            lineage=lineage,
            diagnostics=diagnostics,
        )

    @classmethod
    def unavailable(
        cls,
        *,
        metric_id: str,
        instrument_id: InstrumentId,
        reason: str,
        formula_version: str,
        reference_version: str,
        as_of: datetime,
        computed_at: datetime,
        quality_flags: tuple[str, ...] = (),
        lineage: LineageHandle,
    ) -> AnalyticResult:
        """A declined computation. Still fully traced — absence is auditable too."""
        return cls(
            metric_id=metric_id,
            instrument_id=instrument_id,
            status=ResultStatus.UNAVAILABLE,
            value=None,
            unavailable_reason=reason,
            formula_version=formula_version,
            reference_version=reference_version,
            as_of=as_of,
            computed_at=computed_at,
            quality_flags=quality_flags,
            lineage=lineage,
        )
