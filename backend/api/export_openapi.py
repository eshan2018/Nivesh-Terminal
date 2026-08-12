"""Export the OpenAPI contract as a reviewable artifact (doc 10).

    python -m backend.api.export_openapi

The spec is generated from the typed DTOs and committed to the repository, so a change
to the public contract shows up as a diff in a pull request rather than appearing
silently at runtime. `test_openapi_contract.py` fails when the two drift apart.

The spec describes the *shape* of the API, which does not depend on where the data
comes from — so a stub service is enough to produce it, and generating the contract
needs no database, no repository, and no deployment decisions.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.api.app import PortfolioReferenceFrame, create_app
from backend.domain.model.analytics import AnalyticResult
from backend.platform.identifiers import InstrumentId

SPEC_PATH = Path(__file__).parent / "openapi.json"


def _unused_service(instrument_id: InstrumentId, now: datetime) -> AnalyticResult:
    """Never called: generating a schema does not execute a route."""
    raise AssertionError("the OpenAPI schema must not invoke the metric service")


def _unused_portfolio_service(holdings: Any, now: datetime) -> AnalyticResult:
    """Never called, and supplied for a reason.

    The portfolio route only registers when a service is injected, so exporting without
    one would silently publish a contract missing an endpoint the API actually serves —
    the exact drift this artifact exists to prevent.
    """
    raise AssertionError("the OpenAPI schema must not invoke the portfolio service")


def current_spec() -> dict[str, Any]:
    """The spec the current code describes."""
    app = create_app(
        _unused_service,
        portfolio_service=_unused_portfolio_service,
        reference_frame=PortfolioReferenceFrame(
            instrument_id="nifty-50", confidence_level="95%"
        ),
        clock=lambda: datetime(1970, 1, 1, tzinfo=UTC),
    )
    return app.openapi()


def write_spec(destination: Path = SPEC_PATH) -> Path:
    """Write the spec, sorted and newline-terminated so diffs stay readable."""
    destination.write_text(json.dumps(current_spec(), indent=2, sort_keys=True) + "\n")
    return destination


if __name__ == "__main__":  # pragma: no cover - a one-line developer entry point
    print(f"wrote {write_spec()}")
