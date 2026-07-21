"""The composition root — the one place concrete implementations are wired (ED-011).

    uvicorn --factory backend.main:create_app

This is the production entry point M4a deferred. It is the only module in `backend/`
that sits outside the layer graph, declared as such in `tools/ci/architecture_map.py`
and pinned by a guardrail test. The exemption is narrow and load-bearing:

**It may import across layers. It must contain no logic.** Everything here is
construction and wiring — pick a repository, bind it into the feature provider, hand
the provider to the engine service, hand the service to the app. No domain rule, no
analytics, no serving behaviour. If a line here decides *what a number means*, it is in
the wrong file.

That is what keeps the dependency rule honest above it: `backend/api/` still imports
neither the feature layer nor a repository, and the lint still refuses both. The layers
depend on contracts; only this file knows which implementations satisfy them.

**Configuration is environment, not code.** The database path comes from
`NIVESH_DATABASE`. Defaults are development defaults and are stated as such — a
production deployment sets them explicitly.

**A factory, not a module-level app.** Importing this module has no side effects: it
opens no database, creates no file, and reads no environment. Everything happens when
`create_app()` is called. An import-time `app = build_app(...)` would mean that merely
importing the entry point — to read a constant, to collect tests, to generate the
OpenAPI spec — provisions a database as a side effect, which is both surprising and
untestable. ASGI servers support this directly (`--factory`).
"""
from __future__ import annotations

import os
from datetime import UTC, datetime

from fastapi import FastAPI

from backend.analytics.one_year_return import one_year_return_for
from backend.api.app import create_app as create_api_app
from backend.domain.market_data.sqlite_repository import SqliteMarketDataRepository
from backend.domain.model.analytics import AnalyticResult
from backend.features.returns import close_price_series_provider
from backend.platform.identifiers import InstrumentId

#: Where the domain store lives. SQLite is the development/CI backend (ED-003);
#: PostgreSQL is the production system of record (ADR-0008) and replaces this line,
#: not the layers above it.
DATABASE_ENV = "NIVESH_DATABASE"
DEFAULT_DATABASE = "nivesh.sqlite3"


def build_app(database: str) -> FastAPI:
    """Compose the application over a concrete repository.

    Takes the database explicitly rather than reading the environment itself, so the
    only environment lookup happens once, at module scope, where it is visible. That
    also lets a test compose the real application over a temporary database without
    mutating global state.

    The repository is deliberately long-lived: it owns one connection, serialized
    internally (ED-003), and the serving plane is read-mostly. A pooled Postgres
    repository swaps in here without touching any layer above.
    """
    repository = SqliteMarketDataRepository(database)
    provider = close_price_series_provider(repository)

    def metric_service(instrument_id: InstrumentId, now: datetime) -> AnalyticResult:
        # `now` is supplied by the API boundary and passed down explicitly, so nothing
        # beneath L9 reads an ambient clock (principle 11). as_of and computed_at are
        # the same instant for a live read; they diverge once results are materialized.
        return one_year_return_for(instrument_id, provider, as_of=now, computed_at=now)

    return create_api_app(metric_service, clock=lambda: datetime.now(UTC))


def create_app() -> FastAPI:
    """The ASGI application factory — what `uvicorn --factory` calls.

    The single place the environment is read. Kept separate from `build_app` so tests
    and tooling can compose over an explicit database without setting environment
    variables, and so importing this module stays free of side effects.
    """
    return build_app(os.environ.get(DATABASE_ENV, DEFAULT_DATABASE))
