"""Endpoint behaviour for the one-year-return route (L9).

Hermetic: `TestClient` drives the ASGI app in-process against a fixture-backed
repository. No server, no socket, no network — and an injected clock, so `computed_at`
is asserted rather than tolerated.

The app is composed here the way a process entry point will compose it later
(repository → feature provider → engine service). That wiring is deployment work,
deferred with M4b/M5; assembling it in a fixture is what lets M4a ship complete
without one.
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.analytics.one_year_return import one_year_return_for
from backend.api.app import create_app
from backend.api.dto import source_ref
from backend.domain.market_data.sqlite_repository import SqliteMarketDataRepository
from backend.domain.model.instruments import REFERENCE_VERSION
from backend.domain.model.observations import AuthorityTier, PriceObservation, Provenance
from backend.domain.model.quantities import Currency, Money
from backend.features.returns import close_price_series_provider
from backend.platform.identifiers import InstrumentId

RELIANCE = InstrumentId("reliance")
START = datetime(2024, 1, 1, tzinfo=UTC)
NOW = datetime(2025, 6, 1, 9, 30, tzinfo=UTC)
ROUTE = "/v1/instruments/reliance/metrics/one-year-return"
PROVENANCE = Provenance(
    raw_object_key="raw/v1/yfinance/price-history/2025-01/reliance/abc.json",
    provider="yfinance",
    raw_contract_version="yfinance-ohlcv/v1",
    reference_version=REFERENCE_VERSION,
)


def _observations(count: int, *, start: datetime = START) -> list[PriceObservation]:
    """`count` consecutive daily bars, rising by ₹1 a day from ₹1000."""
    bars = []
    for day in range(count):
        price = Money(Decimal(1000 + day), Currency.INR)
        event_time = start + timedelta(days=day)
        bars.append(
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
    return bars


def _app_over(observations: list[PriceObservation]) -> Iterator[FastAPI]:
    """Compose the app the way a real entry point will: repo → provider → service."""
    with SqliteMarketDataRepository() as repository:
        repository.save_observations(observations)
        provider = close_price_series_provider(repository)

        def service(instrument_id: InstrumentId, now: datetime):
            return one_year_return_for(
                instrument_id, provider, as_of=now, computed_at=now
            )

        yield create_app(service, clock=lambda: NOW)


@pytest.fixture()
def client_with_history() -> Iterator[TestClient]:
    """500 bars — long enough that a one-year anchor exists."""
    for app in _app_over(_observations(500)):
        yield TestClient(app)


@pytest.fixture()
def client_without_history() -> Iterator[TestClient]:
    """Three bars — the instrument is known, the metric is not computable."""
    for app in _app_over(_observations(3)):
        yield TestClient(app)


# ── The happy path ────────────────────────────────────────────────────────────


def test_returns_the_metric_with_lineage_and_freshness(client_with_history: TestClient) -> None:
    response = client_with_history.get(ROUTE)
    assert response.status_code == 200
    body = response.json()

    assert body["instrument"] == {"id": "reliance", "name": "Reliance Industries", "type": "EQUITY"}
    assert body["metric"]["id"] == "one_year_return"
    assert body["metric"]["formula_version"] == "one-year-total-return/v1"
    assert body["metric"]["status"] == "AVAILABLE"
    assert body["metric"]["unit"] == "ratio"
    assert body["metric"]["unavailable_reason"] is None
    assert isinstance(body["metric"]["value"], float)


def test_the_value_matches_the_engine_rather_than_being_reshaped(
    client_with_history: TestClient,
) -> None:
    """The API projects; it does not compute, round, or rescale.

    Bars rise ₹1/day from ₹1000. The last of 500 is day 499 (₹1499); the anchor is
    365 days earlier, day 134 (₹1134). So the return is 1499/1134 - 1.
    """
    value = client_with_history.get(ROUTE).json()["metric"]["value"]
    assert value == pytest.approx(1499 / 1134 - 1, rel=1e-12)


def test_freshness_reports_the_injected_clock(client_with_history: TestClient) -> None:
    freshness = client_with_history.get(ROUTE).json()["freshness"]
    assert datetime.fromisoformat(freshness["as_of"]) == NOW
    assert datetime.fromisoformat(freshness["computed_at"]) == NOW


def test_diagnostics_carry_the_anchor_offset_as_a_number(
    client_with_history: TestClient,
) -> None:
    """Decision 2 on the wire: a number, not a string to be parsed out of a flag."""
    freshness = client_with_history.get(ROUTE).json()["freshness"]
    assert freshness["diagnostics"]["anchor_offset_days"] == 0.0
    assert isinstance(freshness["diagnostics"]["anchor_offset_days"], float)
    assert freshness["quality_flags"] == []


def test_lineage_carries_contributors_not_the_whole_series(
    client_with_history: TestClient,
) -> None:
    """Decision 1 on the wire: proportional to the answer, not to the history."""
    lineage = client_with_history.get(ROUTE).json()["lineage"]

    assert lineage["scanned_count"] == 500
    assert len(lineage["contributing"]) == 2
    assert lineage["feature_id"] == "close_price_series"
    assert lineage["feature_version"] == "close-price-series/v1"
    assert lineage["parameters"] == {"interval": "1d"}
    assert lineage["reference_version"] == REFERENCE_VERSION
    assert lineage["source_refs"] == [source_ref(PROVENANCE.raw_object_key)]

    for ref in lineage["contributing"]:
        assert ref["source_ref"] == source_ref(PROVENANCE.raw_object_key)
        assert ref["event_time"] and ref["knowledge_time"]


# ── Absence and errors ────────────────────────────────────────────────────────


def test_an_uncomputable_metric_is_200_with_a_reason_and_a_null_value(
    client_without_history: TestClient,
) -> None:
    """The request succeeded; the answer is "we don't know", and why.

    A 404 here would conflate "no such instrument" with "no answer for this
    instrument" — the exact ambiguity the L6 UnknownInstrument fix removed.
    """
    response = client_without_history.get(ROUTE)
    assert response.status_code == 200

    metric = response.json()["metric"]
    assert metric["status"] == "UNAVAILABLE"
    assert metric["value"] is None
    assert metric["unavailable_reason"] == "insufficient-history-for-a-one-year-window"


def test_a_null_value_is_never_serialized_as_zero(client_without_history: TestClient) -> None:
    """The never-fabricate invariant, asserted on the wire and not just in the envelope."""
    assert '"value":null' in client_without_history.get(ROUTE).text.replace(" ", "")


def test_an_unavailable_result_still_carries_lineage(
    client_without_history: TestClient,
) -> None:
    """Absence is auditable too — you can still ask which versions produced it."""
    lineage = client_without_history.get(ROUTE).json()["lineage"]
    assert lineage["feature_version"] == "close-price-series/v1"
    assert lineage["contributing"] == []
    assert lineage["scanned_count"] == 3


def test_an_unknown_instrument_is_404(client_with_history: TestClient) -> None:
    response = client_with_history.get("/v1/instruments/not-an-instrument/metrics/one-year-return")
    assert response.status_code == 404


# ── Projection purity and determinism ─────────────────────────────────────────


@pytest.mark.parametrize(
    "leak",
    ["sqlite", "SELECT", "yfinance", "observations", "Decimal", "market_data", "RELIANCE.NS"],
    ids=["storage-engine", "sql", "vendor", "table", "python-type", "schema", "vendor-symbol"],
)
def test_no_storage_or_vendor_detail_reaches_the_wire(
    client_with_history: TestClient, leak: str
) -> None:
    """Doc 10: DTOs are decoupled from storage schemas, and no vendor name lives above L1.

    Asserted structurally rather than by inspection, because this is the property that
    keeps internal refactors from becoming breaking client changes.
    """
    assert leak not in client_with_history.get(ROUTE).text


def test_the_response_is_byte_identical_across_requests(
    client_with_history: TestClient,
) -> None:
    """Same inputs and versions, same bytes — determinism visible at the edge."""
    first = client_with_history.get(ROUTE)
    second = client_with_history.get(ROUTE)
    assert first.content == second.content
