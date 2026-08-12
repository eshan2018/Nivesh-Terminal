"""Wire DTOs for the one-year-return endpoint (L9, doc 10).

**The API is a projection of the domain, not a dump of it.** These models are shaped
for a client reading a number and asking "why?", and are deliberately decoupled from
both the storage schema (doc 07) and the internal envelope. An internal refactor must
not force a client change, which is the entire reason this file exists rather than
serializing `AnalyticResult` directly.

Three rules the shapes enforce:

* **No storage or vendor field reaches the wire.** Raw object keys appear as opaque
  strings for lineage resolution; no table, column, or SQL concept is expressed.
* **`value` is `null`, never `0`, when the metric is unavailable** — the envelope's
  never-fabricate invariant carried through to JSON (principle 13).
* **Units are explicit.** The metric is a unitless ratio and says so, rather than
  leaving a client to guess whether `0.12` means 12% or ₹0.12 (doc 04 / doc 10).

Money never appears here — a return is a ratio. When an endpoint does serve money it
must serialize as a string, because JSON numbers are IEEE-754 doubles and would silently
undo ADR-0016; that decision belongs to the milestone that first needs it.
"""
from __future__ import annotations

import hashlib
from datetime import datetime

from pydantic import BaseModel, Field

from backend.domain.model.analytics import AnalyticResult, ResultStatus


class InstrumentDTO(BaseModel):
    """The instrument the metric describes, in canonical terms only."""

    id: str = Field(description="Nivesh's internal instrument identifier — never a vendor symbol.")
    name: str
    type: str = Field(description="EQUITY or INDEX.")


class MetricDTO(BaseModel):
    """The number, or an explicit account of why there isn't one."""

    id: str = Field(description="Stable metric identifier, e.g. `one_year_return`.")
    formula_version: str = Field(
        description="The methodology version that produced this value. A formula change "
        "is a new version, never a silent edit."
    )
    unit: str = Field(description="`ratio` — unitless. 0.12 means +12%, not a currency amount.")
    status: ResultStatus
    value: float | None = Field(
        default=None,
        description="The value, or null when status is UNAVAILABLE. Never 0 as a stand-in "
        "for a missing input.",
    )
    unavailable_reason: str | None = Field(
        default=None,
        description="Why no value could be produced. Present exactly when status is UNAVAILABLE.",
    )


class FreshnessDTO(BaseModel):
    """When this was true and when it was computed (doc 10: freshness is mandatory)."""

    as_of: datetime = Field(description="Knowledge cutoff: nothing learned after this was used.")
    computed_at: datetime
    quality_flags: list[str] = Field(
        default_factory=list,
        description="Opaque tags describing data conditions, e.g. `reference-version-drift`. "
        "Test membership; do not parse.",
    )
    diagnostics: dict[str, float] = Field(
        default_factory=dict,
        description="Typed numeric facts about how the value was reached, e.g. "
        "`anchor_offset_days: -3` meaning the anchor bar sat 3 days before the target.",
    )


def source_ref(raw_object_key: str) -> str:
    """An opaque, stable handle for a raw payload.

    The internal key is `raw/v1/{provider}/{dataset}/{window}/{instrument}/{sha}.json`
    — a storage address that names the vendor. Doc 10 forbids both from reaching a DTO
    ("storage schemas or vendor fields must not leak"), and principle 7 requires that
    no API code or payload name a provider: a client that learns the vendor from a
    lineage string couples to it, and swapping providers becomes a breaking change.

    Hashing keeps what a lineage handle is actually for — a stable identifier the same
    payload always maps to, resolvable by a future lineage endpoint — while discarding
    what the client must not see. Deterministic, so it is still a valid cache key and
    still equal across requests.
    """
    return hashlib.sha256(raw_object_key.encode()).hexdigest()[:16]


class ObservationRefDTO(BaseModel):
    """One canonical observation that contributed to the value."""

    event_time: datetime = Field(description="The bar's own timestamp.")
    knowledge_time: datetime = Field(description="When the platform learned it.")
    source_ref: str = Field(
        description="Opaque, stable handle for the immutable raw payload behind this "
        "observation. Not a storage path; resolve it via the lineage API."
    )


class LineageDTO(BaseModel):
    """The "why?" panel's raw material (doc 10: lineage is a first-class capability).

    `contributing` names the observations that actually determined the value —
    typically two — while `scanned_count` reports how many the feature supplied. That
    split keeps the response proportional to the answer instead of to the history
    behind it, without hiding how much data was considered.
    """

    feature_id: str
    feature_version: str
    parameters: dict[str, str] = Field(
        default_factory=dict, description="The arguments the feature was invoked with."
    )
    reference_version: str = Field(
        description="The pinned reference-data snapshot in force at compute time."
    )
    contributing: list[ObservationRefDTO] = Field(default_factory=list)
    scanned_count: int = Field(
        description="How many observations the feature supplied, contributing or not."
    )
    source_refs: list[str] = Field(
        default_factory=list,
        description="Opaque handles for every raw payload this value derives from.",
    )


class OneYearReturnResponse(BaseModel):
    """The endpoint's response — one metric, fully traced."""

    instrument: InstrumentDTO
    metric: MetricDTO
    freshness: FreshnessDTO
    lineage: LineageDTO

    @classmethod
    def project(
        cls, result: AnalyticResult, *, name: str, instrument_type: str
    ) -> OneYearReturnResponse:
        """Project an `AnalyticResult` onto the wire.

        Pure translation — no computation, no defaulting, no business rule. Anything
        resembling logic here would be analytics leaking into the API (doc 10).
        """
        (feature,) = result.lineage.features
        return cls(
            instrument=InstrumentDTO(
                id=result.instrument_id.value, name=name, type=instrument_type
            ),
            metric=MetricDTO(
                id=result.metric_id,
                formula_version=result.formula_version,
                unit="ratio",
                status=result.status,
                # `value` is a Ratio for this metric; the envelope guarantees it is
                # None exactly when the status is UNAVAILABLE.
                value=None if result.value is None else result.value.value,
                unavailable_reason=result.unavailable_reason,
            ),
            freshness=FreshnessDTO(
                as_of=result.as_of,
                computed_at=result.computed_at,
                quality_flags=list(result.quality_flags),
                diagnostics=dict(result.diagnostics),
            ),
            lineage=LineageDTO(
                feature_id=feature.feature_id,
                feature_version=feature.feature_version,
                parameters=dict(feature.parameters),
                reference_version=result.reference_version,
                contributing=[
                    ObservationRefDTO(
                        event_time=ref.event_time,
                        knowledge_time=ref.knowledge_time,
                        source_ref=source_ref(ref.provenance.raw_object_key),
                    )
                    for ref in result.lineage.contributing
                ],
                scanned_count=result.lineage.scanned_count(),
                source_refs=[source_ref(key) for key in result.lineage.raw_object_keys()],
            ),
        )


# ── Portfolio analysis (M6c) ──────────────────────────────────────────────────


class HoldingDTO(BaseModel):
    """One position in a portfolio the caller is asking about."""

    instrument_id: str = Field(description="Internal instrument id, e.g. `hdfc-bank`.")
    weight: float = Field(
        gt=0.0, le=1.0,
        description="Fraction of the portfolio. Weights must sum to 1 — they are never "
        "renormalized, because normalizing silently would analyse a portfolio the "
        "caller did not describe.",
    )


class PortfolioAnalysisRequest(BaseModel):
    """The portfolio to analyse.

    **A body, not a query string.** Holdings are personal financial data, and a query
    string lands in server logs, browser history, referrer headers and proxy caches. A
    body does not. Nothing here is persisted (Product principle 5: stateless before
    accounts).

    **The reference frame is not a parameter.** Which index the comparison uses, and at
    what confidence, are server-controlled — otherwise the same screenshot could mean
    different things to different readers, and no number in it would be verifiable.
    """

    holdings: list[HoldingDTO] = Field(min_length=1)


class JudgementDTO(BaseModel):
    """A deterministic judgement (ED-021) — the verdict and the quantity behind it.

    The verdict is produced by transparent rules over evidence, never by a model. The
    value it judged travels with it so a reader can always check one against the other.
    """

    id: str = Field(description="Stable judgement identifier.")
    formula_version: str
    status: ResultStatus
    verdict: str | None = Field(
        default=None,
        description="`HIGHER_REALIZED_VOLATILITY`, `NOT_DISTINGUISHABLE` or "
        "`LOWER_REALIZED_VOLATILITY`. Null exactly when status is UNAVAILABLE — absent "
        "evidence cannot support a judgement.",
    )
    volatility_ratio: float | None = Field(
        default=None,
        description="Portfolio realized volatility divided by the reference's over the "
        "same dates. 1.2 means the portfolio moved about 1.2x as much.",
    )
    unavailable_reason: str | None = None
    reference_instrument: str = Field(
        description="What the portfolio was compared against."
    )
    confidence_level: str = Field(
        description="The level at which a difference is called. A stated convention, "
        "not a property of the data."
    )
    claim_scope: str = Field(
        default=(
            "This compares realized volatility only. It is not a statement about total "
            "risk, which also includes concentration, liquidity, drawdown depth and "
            "single-stock events."
        ),
        description="What this judgement does and does not claim.",
    )


class PortfolioAnalysisResponse(BaseModel):
    """The judgement, the evidence beneath it, and the path back to raw records."""

    judgement: JudgementDTO
    freshness: FreshnessDTO
    lineage: list[LineageDTO]

    @classmethod
    def project(
        cls, result: AnalyticResult, *, reference_instrument: str, confidence_level: str
    ) -> PortfolioAnalysisResponse:
        """Project the judgement envelope onto the wire. Pure translation."""
        diagnostics = dict(result.diagnostics)
        return cls(
            judgement=JudgementDTO(
                id=result.metric_id,
                formula_version=result.formula_version,
                status=result.status,
                verdict=None if result.verdict is None else str(result.verdict),
                volatility_ratio=None if result.value is None else result.value.value,
                unavailable_reason=result.unavailable_reason,
                reference_instrument=reference_instrument,
                confidence_level=confidence_level,
            ),
            freshness=FreshnessDTO(
                as_of=result.as_of,
                computed_at=result.computed_at,
                quality_flags=list(result.quality_flags),
                diagnostics=diagnostics,
            ),
            lineage=[
                LineageDTO(
                    feature_id=feature.feature_id,
                    feature_version=feature.feature_version,
                    parameters=dict(feature.parameters),
                    reference_version=result.reference_version,
                    contributing=[],
                    scanned_count=len(feature.inputs),
                    # De-duplicated: one handle per raw object, not one per observation.
                    # A 250-bar feature derives from a handful of payloads, and repeating
                    # each 250 times is the payload growth ED-012 removed.
                    source_refs=sorted(
                        {source_ref(ref.provenance.raw_object_key) for ref in feature.inputs}
                    ),
                )
                for feature in result.lineage.features
            ],
        )
