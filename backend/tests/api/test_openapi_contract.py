"""The OpenAPI contract is an artifact, not a side effect (doc 10, doc 11).

Doc 10 requires "a machine-readable schema (OpenAPI) is the source of truth, enabling
generated clients/types for the Next.js frontend and contract tests". FastAPI can
generate one on demand, but a spec that only exists at runtime cannot be reviewed in a
diff, cannot be published to a client team, and changes silently.

So the spec is committed at `backend/api/openapi.json`, and this test fails when the
code and the artifact disagree. A contract change then has to be an intentional, visible
line in a pull request — which is what "contract-first" means in practice for a repo
that generates its spec from typed models.

Regenerate deliberately with:

    python -m backend.api.export_openapi
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from backend.api.export_openapi import SPEC_PATH, current_spec

ROUTE = "/v1/instruments/{instrument_id}/metrics/one-year-return"


def test_the_committed_spec_matches_the_code() -> None:
    committed = json.loads(Path(SPEC_PATH).read_text())
    assert current_spec() == committed, (
        "The OpenAPI artifact is stale. If this change to the contract is intended, "
        "run `python -m backend.api.export_openapi` and commit the result."
    )


def test_the_contract_exposes_exactly_one_route() -> None:
    """The Phase 0.5 fence, asserted rather than trusted."""
    assert list(current_spec()["paths"]) == [ROUTE]


def test_the_route_documents_both_outcomes() -> None:
    operation = current_spec()["paths"][ROUTE]["get"]
    assert set(operation["responses"]) >= {"200", "404"}


def test_the_response_schema_allows_a_null_value_but_not_a_missing_one() -> None:
    """A client must be able to see "we don't know" in the type, not just at runtime."""
    schemas = current_spec()["components"]["schemas"]
    value = schemas["MetricDTO"]["properties"]["value"]
    assert {"type": "number"} in value["anyOf"]
    assert {"type": "null"} in value["anyOf"]


def test_the_spec_names_no_vendor_and_no_storage_concept() -> None:
    """The published contract is what clients couple to — it must outlive a provider."""
    text = json.dumps(current_spec()).lower()
    for leak in ("yfinance", "sqlite", "postgres", "raw_object_key", "select "):
        assert leak not in text


def test_the_spec_is_deterministic() -> None:
    assert current_spec() == current_spec()


def test_export_writes_what_the_test_compares(tmp_path: Path) -> None:
    """Guards the regeneration path itself, so the documented fix actually works."""
    from backend.api.export_openapi import write_spec

    destination = tmp_path / "openapi.json"
    write_spec(destination)
    assert json.loads(destination.read_text()) == current_spec()
    assert destination.read_text().endswith("\n")


def test_the_spec_does_not_depend_on_the_injected_service() -> None:
    """The contract describes the shape, not the data behind it."""
    from backend.api.app import create_app

    def refusing_service(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the spec must not invoke the service")

    app = create_app(refusing_service, clock=lambda: datetime(2025, 1, 1, tzinfo=UTC))  # type: ignore[arg-type]
    assert app.openapi()["paths"].keys() == current_spec()["paths"].keys()
