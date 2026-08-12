"""`POST /v1/portfolio/analysis` — the judgement on the wire (M6c).

Hermetic: the app is composed the way `backend/main.py` composes it, over a temporary
SQLite database, with an injected clock. No server, no socket, no network.
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.analytics.one_year_return import one_year_return_for
from backend.analytics.portfolio_volatility_vs_reference import (
    CONFIDENCE_LABEL,
    portfolio_volatility_vs_reference_for,
)
from backend.api.app import PortfolioReferenceFrame, create_app
from backend.domain.market_data.sqlite_repository import SqliteMarketDataRepository
from backend.domain.model.observations import AuthorityTier, PriceObservation, Provenance
from backend.domain.model.quantities import Currency, IndexLevel, Money
from backend.features.portfolio_returns import (
    aligned_reference_provider,
    portfolio_matrix_provider,
)
from backend.features.returns import close_price_series_provider
from backend.ingestion.validation import VALIDATION_VERSION
from backend.platform.identifiers import InstrumentId

ROUTE = "/v1/portfolio/analysis"
NIFTY = InstrumentId("nifty-50")
START = datetime(2024, 1, 1, tzinfo=UTC)
NOW = datetime(2026, 8, 10, 9, 30, tzinfo=UTC)
PROVENANCE = Provenance(
    raw_object_key="raw/v1/yfinance/price-history/2024-01/x/abc.json",
    provider="yfinance",
    raw_contract_version="yfinance-ohlcv/v1",
    reference_version="instrument-reference/v2",
    validation_version=VALIDATION_VERSION,
)


def _prices(amplitude: float, count: int = 300) -> list[float]:
    return [round(1000.0 + amplitude * ((day * 7) % 11 - 5), 4) for day in range(count)]


def _observations(instrument: InstrumentId, amplitude: float, count: int = 300):
    index = instrument == NIFTY
    for day, close in enumerate(_prices(amplitude, count)):
        price = IndexLevel(Decimal(str(close))) if index else Money(
            Decimal(str(close)), Currency.INR
        )
        event_time = START + timedelta(days=day)
        yield PriceObservation(
            instrument_id=instrument, event_time=event_time, knowledge_time=event_time,
            interval="1d", open=price, high=price, low=price, close=price,
            volume=Decimal("1000"), authority=AuthorityTier.AUTHORITATIVE,
            quality_flags=(), provenance=PROVENANCE,
        )


def _client(**amplitudes: float) -> Iterator[TestClient]:
    with SqliteMarketDataRepository() as repository:
        for slug, amplitude in amplitudes.items():
            repository.save_observations(
                list(_observations(InstrumentId(slug.replace("_", "-")), amplitude))
            )
        matrix_provider = portfolio_matrix_provider(repository)
        reference_provider = aligned_reference_provider(repository)
        series_provider = close_price_series_provider(repository)

        def metric_service(instrument_id, now):
            return one_year_return_for(instrument_id, series_provider, as_of=now, computed_at=now)

        def portfolio_service(holdings, now):
            return portfolio_volatility_vs_reference_for(
                holdings, matrix_provider, reference_provider,
                reference_id=NIFTY, as_of=now, computed_at=now,
            )

        yield TestClient(create_app(
            metric_service,
            portfolio_service=portfolio_service,
            reference_frame=PortfolioReferenceFrame(
                instrument_id=NIFTY.value, confidence_level=CONFIDENCE_LABEL
            ),
            clock=lambda: NOW,
        ))


@pytest.fixture()
def volatile_client() -> Iterator[TestClient]:
    yield from _client(reliance=6.0, tcs=6.0, **{"nifty_50": 1.0})


def _body(*holdings: tuple[str, float]) -> dict:
    return {"holdings": [{"instrument_id": i, "weight": w} for i, w in holdings]}


# ── The happy path ────────────────────────────────────────────────────────────

def test_a_portfolio_receives_a_verdict_with_the_ratio_behind_it(
    volatile_client: TestClient,
) -> None:
    response = volatile_client.post(ROUTE, json=_body(("reliance", 0.5), ("tcs", 0.5)))

    assert response.status_code == 200
    judgement = response.json()["judgement"]
    assert judgement["status"] == "AVAILABLE"
    assert judgement["verdict"] == "HIGHER_REALIZED_VOLATILITY"
    assert judgement["volatility_ratio"] > 1.0
    assert judgement["formula_version"] == "portfolio-volatility-vs-reference/v1"


def test_the_reference_frame_is_disclosed_in_every_response(
    volatile_client: TestClient,
) -> None:
    """A comparison is meaningless without saying what it compared against, at what level."""
    judgement = volatile_client.post(
        ROUTE, json=_body(("reliance", 1.0))
    ).json()["judgement"]

    assert judgement["reference_instrument"] == "nifty-50"
    assert judgement["confidence_level"] == "95%"


def test_the_response_states_what_the_judgement_does_not_claim(
    volatile_client: TestClient,
) -> None:
    """The claim is about realized volatility, never about total risk."""
    scope = volatile_client.post(
        ROUTE, json=_body(("reliance", 1.0))
    ).json()["judgement"]["claim_scope"]

    assert "realized volatility" in scope
    assert "not a statement about total risk" in scope


def test_confidence_travels_with_the_verdict(volatile_client: TestClient) -> None:
    diagnostics = volatile_client.post(
        ROUTE, json=_body(("reliance", 0.5), ("tcs", 0.5))
    ).json()["freshness"]["diagnostics"]

    assert diagnostics["volatility_ratio_ci_low"] < diagnostics["volatility_ratio"]
    assert diagnostics["volatility_ratio_ci_high"] > diagnostics["volatility_ratio"]
    assert diagnostics["portfolio_observations"] == diagnostics["reference_observations"]
    assert "z_statistic" in diagnostics


def test_lineage_reaches_raw_objects_and_names_the_reference_feature(
    volatile_client: TestClient,
) -> None:
    lineage = volatile_client.post(
        ROUTE, json=_body(("reliance", 0.5), ("tcs", 0.5))
    ).json()["lineage"]

    versions = {entry["feature_version"] for entry in lineage}
    assert "aligned-reference-return-series/v1" in versions
    assert all(entry["source_refs"] for entry in lineage)
    # Opaque handles only — no storage path, no vendor name (doc 10).
    for entry in lineage:
        for ref in entry["source_refs"]:
            assert "yfinance" not in ref and "/" not in ref


def test_holdings_order_does_not_change_the_response(volatile_client: TestClient) -> None:
    one = volatile_client.post(ROUTE, json=_body(("reliance", 0.6), ("tcs", 0.4))).json()
    other = volatile_client.post(ROUTE, json=_body(("tcs", 0.4), ("reliance", 0.6))).json()

    assert one["judgement"] == other["judgement"]


def test_the_same_body_twice_gives_the_same_answer(volatile_client: TestClient) -> None:
    """A POST that reads: safe to retry, no state, no drift."""
    body = _body(("reliance", 0.5), ("tcs", 0.5))
    assert volatile_client.post(ROUTE, json=body).json() == volatile_client.post(
        ROUTE, json=body
    ).json()


# ── Absence and errors ────────────────────────────────────────────────────────

def test_an_unknown_instrument_is_404_not_an_unavailable_verdict(
    volatile_client: TestClient,
) -> None:
    """"No such instrument" and "no answer for this instrument" are different answers."""
    response = volatile_client.post(ROUTE, json=_body(("not-a-thing", 1.0)))
    assert response.status_code == 404


def test_a_malformed_body_is_422(volatile_client: TestClient) -> None:
    assert volatile_client.post(ROUTE, json={"holdings": []}).status_code == 422
    assert volatile_client.post(
        ROUTE, json=_body(("reliance", 0.0))
    ).status_code == 422


def test_an_unavailable_judgement_never_carries_a_verdict() -> None:
    """The most dangerous path: absent evidence becoming a directional answer."""
    with SqliteMarketDataRepository() as repository:
        repository.save_observations(list(_observations(InstrumentId("reliance"), 5.0, count=10)))
        repository.save_observations(list(_observations(NIFTY, 2.0, count=10)))
        matrix_provider = portfolio_matrix_provider(repository)
        reference_provider = aligned_reference_provider(repository)

        def portfolio_service(holdings, now):
            return portfolio_volatility_vs_reference_for(
                holdings, matrix_provider, reference_provider,
                reference_id=NIFTY, as_of=now, computed_at=now,
            )

        client = TestClient(create_app(
            lambda i, n: None,
            portfolio_service=portfolio_service,
            reference_frame=PortfolioReferenceFrame(
                instrument_id=NIFTY.value, confidence_level=CONFIDENCE_LABEL
            ),
            clock=lambda: NOW,
        ))
        judgement = client.post(ROUTE, json=_body(("reliance", 1.0))).json()["judgement"]

    assert judgement["status"] == "UNAVAILABLE"
    assert judgement["verdict"] is None
    assert judgement["volatility_ratio"] is None
    assert judgement["unavailable_reason"]
    # Still discloses what it would have compared against.
    assert judgement["reference_instrument"] == "nifty-50"


def test_the_client_cannot_choose_the_reference_frame(volatile_client: TestClient) -> None:
    """Extra fields are ignored, so a caller cannot move the goalposts.

    A client-chosen index or confidence level would make the same screenshot mean
    different things to different readers.
    """
    response = volatile_client.post(
        ROUTE,
        json={
            **_body(("reliance", 1.0)),
            "reference_instrument": "apple",
            "confidence_level": "50%",
        },
    )

    judgement = response.json()["judgement"]
    assert judgement["reference_instrument"] == "nifty-50"
    assert judgement["confidence_level"] == "95%"
