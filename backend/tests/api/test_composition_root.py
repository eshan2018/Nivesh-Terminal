"""The production entry point actually serves (ED-011, M4b).

M4a shipped the endpoint with composition performed in test fixtures, which meant
"the API works" honestly only meant "the API works under test". This closes that gap:
the app built by `backend.main.build_app` — the same function `uvicorn backend.main:app`
loads — is driven against a real on-disk SQLite database through the real feature and
engine layers.

Still hermetic: a temporary database file, no network, no server process, no ambient
clock beyond the one the app itself reads.
"""
from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.domain.market_data.sqlite_repository import SqliteMarketDataRepository
from backend.domain.model.observations import AuthorityTier, PriceObservation, Provenance
from backend.domain.model.quantities import Currency, Money
from backend.main import DATABASE_ENV, DEFAULT_DATABASE, build_app, create_app
from backend.platform.identifiers import InstrumentId

RELIANCE = InstrumentId("reliance")
START = datetime(2024, 1, 1, tzinfo=UTC)
ROUTE = "/v1/instruments/reliance/metrics/one-year-return"
ROUTE_TEMPLATE = "/v1/instruments/{instrument_id}/metrics/one-year-return"
PROVENANCE = Provenance(
    raw_object_key="raw/v1/yfinance/price-history/2024-01/reliance/abc.json",
    provider="yfinance",
    raw_contract_version="yfinance-ohlcv/v1",
    reference_version="skeleton-reference/v1",
)


def _seed(database: Path, bars: int) -> None:
    """Write real rows through the real repository — no fixture shortcut."""
    with SqliteMarketDataRepository(database) as repository:
        repository.save_observations(
            [
                PriceObservation(
                    instrument_id=RELIANCE,
                    event_time=START + timedelta(days=day),
                    knowledge_time=START + timedelta(days=day),
                    interval="1d",
                    open=Money(Decimal(1000 + day), Currency.INR),
                    high=Money(Decimal(1000 + day), Currency.INR),
                    low=Money(Decimal(1000 + day), Currency.INR),
                    close=Money(Decimal(1000 + day), Currency.INR),
                    volume=Decimal("1000"),
                    authority=AuthorityTier.AUTHORITATIVE,
                    quality_flags=(),
                    provenance=PROVENANCE,
                )
                for day in range(bars)
            ]
        )


@pytest.fixture()
def database(tmp_path: Path) -> Path:
    path = tmp_path / "nivesh.sqlite3"
    _seed(path, bars=500)
    return path


def test_the_entry_point_serves_a_real_request_from_a_real_database(
    database: Path,
) -> None:
    """The whole stack, composed the way production composes it."""
    client = TestClient(build_app(str(database)))

    response = client.get(ROUTE)

    assert response.status_code == 200
    body = response.json()
    assert body["metric"]["status"] == "AVAILABLE"
    assert body["metric"]["value"] == pytest.approx(1499 / 1134 - 1, rel=1e-12)
    assert body["lineage"]["scanned_count"] == 500


def test_the_entry_point_reports_absence_rather_than_failing(tmp_path: Path) -> None:
    """An empty database is a data condition, not a crash.

    A freshly provisioned deployment has no rows yet. It must answer "we don't know
    and here is why", not 500.
    """
    empty = tmp_path / "empty.sqlite3"
    _seed(empty, bars=0)

    response = TestClient(build_app(str(empty))).get(ROUTE)

    assert response.status_code == 200
    assert response.json()["metric"]["status"] == "UNAVAILABLE"
    assert response.json()["metric"]["value"] is None


def test_the_entry_point_creates_its_schema_on_first_start(tmp_path: Path) -> None:
    """Pointing at a path that does not exist yet must not require a manual step."""
    fresh = tmp_path / "does-not-exist-yet.sqlite3"
    assert not fresh.exists()

    response = TestClient(build_app(str(fresh))).get(ROUTE)

    assert fresh.exists()
    assert response.status_code == 200


def test_the_factory_is_the_one_a_server_loads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`uvicorn --factory backend.main:create_app` must produce a working application."""
    monkeypatch.setenv(DATABASE_ENV, str(tmp_path / "from-env.sqlite3"))

    app = create_app()

    assert app.title == "Nivesh Terminal API"
    assert any(getattr(route, "path", None) == ROUTE_TEMPLATE for route in app.routes)


def test_importing_the_entry_point_has_no_side_effects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Importing must not provision anything.

    With a module-level `app = build_app(...)`, merely importing this module — to read a
    constant, collect tests, or generate the OpenAPI spec — created a database file in
    the working directory. A factory defers all of that to the call.
    """
    monkeypatch.chdir(tmp_path)
    importlib.reload(importlib.import_module("backend.main"))

    assert list(tmp_path.iterdir()) == []


def test_the_factory_reads_the_database_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Configuration is environment, not code — and the factory is where it is read."""
    configured = tmp_path / "configured.sqlite3"
    monkeypatch.setenv(DATABASE_ENV, str(configured))

    create_app()

    assert configured.exists()


def test_the_database_location_is_configurable_and_defaulted() -> None:
    """Configuration is environment, not code — but a default keeps `make serve` trivial."""
    assert DATABASE_ENV == "NIVESH_DATABASE"
    assert DEFAULT_DATABASE.endswith(".sqlite3")
