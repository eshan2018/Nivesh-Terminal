# Nivesh Terminal — developer entry points.
# `make check` runs the full guardrail + test gate (the same gate CI runs).
PY ?= python

.PHONY: install lint-arch lint test check skeleton serve openapi

install:  ## Install the backend and dev tooling into the active environment.
	$(PY) -m pip install -e ".[dev]"

lint-arch:  ## Architecture guardrails: dependency-direction, no-vendor-above-L1, module-schema isolation.
	$(PY) -m tools.ci.check

lint:  ## Style/lint (ruff).
	$(PY) -m ruff check backend tools

test:  ## Unit/integration tests.
	$(PY) -m pytest

check: lint-arch lint test  ## The full gate. Run before every commit.

skeleton:  ## Live Walking Skeleton status board + a real end-to-end trace.
	$(PY) -m tools.skeleton_status

serve:  ## Run the API locally (needs the `serve` extra: pip install -e ".[dev,serve]").
	@echo "NIVESH_DATABASE=$${NIVESH_DATABASE:-nivesh.sqlite3}"
	$(PY) -m uvicorn --factory backend.main:create_app --reload --port 8000

openapi:  ## Regenerate the committed OpenAPI contract artifact.
	$(PY) -m backend.api.export_openapi
