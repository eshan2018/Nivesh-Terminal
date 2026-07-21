"""The REST API (L9, doc 10) — one endpoint, contract-first.

**Dependencies arrive by injection (ED-011).** `create_app` takes the metric service
and the clock; this module imports neither a repository nor the feature layer, and the
architecture lint refuses both. That is what lets L9 obey doc 03's "L9 depends on L7"
literally while still serving data that ultimately comes from L5: the composition is
performed by whoever builds the app, not by the layer that consumes it.

**Time enters here and is then explicit everywhere below.** The clock is read once per
request at this boundary and passed downward as a value, so nothing beneath L9 reads an
ambient clock (principle 11). Injecting it also makes responses deterministic under
test, which is why it is a parameter rather than a call to `datetime.now`.

**Status codes carry meaning:**
* `404` — no such instrument. The reference registry has never heard of it.
* `200` + `status: UNAVAILABLE` — the instrument exists; we cannot compute the metric,
  and the response says why. The request succeeded; the answer is "we don't know".

Collapsing those two into one code would reintroduce exactly the ambiguity the L6
`UnknownInstrument` fix removed.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException

from backend.api.dto import OneYearReturnResponse
from backend.domain.model.analytics import AnalyticResult
from backend.domain.model.instruments import UnknownInstrument, reference_for
from backend.platform.identifiers import InstrumentId

API_VERSION = "v1"
TITLE = "Nivesh Terminal API"

#: What L9 needs from L7: an instrument and the current instant, in; a traced result,
#: out. Deliberately not typed as "the engine" — the API depends on the shape of the
#: service, not on which engine happens to satisfy it.
type MetricService = Callable[[InstrumentId, datetime], AnalyticResult]

#: Reads the current instant. Injected so tests are deterministic and so the ambient
#: clock is confined to this one boundary.
type Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def create_app(metric_service: MetricService, *, clock: Clock = _utc_now) -> FastAPI:
    """Build the ASGI application around an injected metric service.

    There is no module-level `app` singleton on purpose: constructing one would force
    this module to choose a repository, which is both an architecture violation and a
    deployment decision that belongs to whoever runs the process.
    """
    app = FastAPI(
        title=TITLE,
        version=API_VERSION,
        description=(
            "Read-only market analytics. Every derived value is served with its "
            "lineage and freshness, so any number can be traced to the raw records "
            "and the formula version that produced it."
        ),
    )

    @app.get(
        f"/{API_VERSION}/instruments/{{instrument_id}}/metrics/one-year-return",
        response_model=OneYearReturnResponse,
        summary="One-year total return for an instrument",
        response_description=(
            "The metric with its lineage and freshness. A 200 with "
            "`status: UNAVAILABLE` means the instrument is known but the metric "
            "could not be computed; `unavailable_reason` says why."
        ),
        responses={404: {"description": "No instrument with this identifier exists."}},
        tags=["metrics"],
    )
    def one_year_return_endpoint(instrument_id: str) -> OneYearReturnResponse:
        identifier = InstrumentId(instrument_id)
        try:
            reference = reference_for(identifier)
        except UnknownInstrument as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        result = metric_service(identifier, clock())
        return OneYearReturnResponse.project(
            result, name=reference.name, instrument_type=str(reference.type)
        )

    return app
