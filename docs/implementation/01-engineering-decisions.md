# Implementation · 01 · Engineering Decision Log (ED)

| | |
|---|---|
| **Status** | Living — implementation tier (not part of the frozen architecture set) |
| **Owner** | Implementing engineer / Chief Software Architect |
| **Governed by** | Architecture v2.0 (`docs/architecture/`, APPROVED & FROZEN 2026-07-17) |
| **Complements** | [ADR registry — doc 18](../architecture/18-architecture-decision-records.md). **This log does not replace it.** |

## Purpose
Record **implementation-level decisions that do not meet the ADR threshold** — the concrete
technologies, versions, frameworks, libraries, hosted services, and tooling that *realize* the
approved architecture without changing it. These are the decisions Architecture v2.0 deliberately
left to implementation.

## The ADR / ED boundary (the classification rule)
A decision is an **ADR** (goes in [doc 18](../architecture/18-architecture-decision-records.md)) if it changes the system architecture,
architectural boundaries, public contracts, long-term maintainability, or deployment model — or
would require a *migration of the architecture* if reversed.

A decision is an **Engineering Decision (ED)** (goes here) if it is an implementation detail —
language version, framework, library, tooling, testing framework, hosted-service/vendor
selection, package choice — that does **not** alter the approved architecture. Reversing an ED
is a *re-implementation of the same architecture*, not a migration of it.

> **Litmus used throughout:** in each domain below, the *architectural* decision is already
> owned by an ADR or an architecture document (e.g. PostgreSQL-as-engine = ADR-0008; REST-as-
> contract = ADR-0012; orchestration-model = doc 16; single-cloud-stance = doc 12). Each ED
> records only the residual *realization* under that already-made architectural decision. If a
> proposal instead **replaced** the architectural decision (e.g. "use a non-Postgres engine"),
> it would require an ADR that supersedes the relevant one — not an ED.

## ED lifecycle
`Proposed` → `Accepted` → (`Superseded by ED-NNN` | `Deprecated`).
EDs are **mutable** in a way ADRs are not: because they don't bind the architecture, an ED may
be revised in place for non-material corrections, and superseded (new ID) for a material change
of selection. An ED is **never promoted to an ADR**; if a reversal turns out to require an
architectural change, that is a *new ADR*, and the ED is marked `Superseded`/`Deprecated`.

## ED template
```markdown
### ED-NNN · <Title>
- **Status:** Proposed | Accepted | Superseded by ED-MMM | Deprecated
- **Context:** the need and the constraints from the architecture.
- **Decision:** the concrete selection.
- **Alternatives Considered:** options weighed and not chosen.
- **Consequences:** what follows; reversal cost; what stays swappable.
- **Configuration Source:** the file(s) that are the authoritative, enforceable record.
- **Related Architecture Documents:** the ADR/doc whose decision this ED realizes.
```

## Rules
1. **One selection per ED.** Split bundled choices.
2. **An ED never contradicts the architecture.** If it seems to, the architecture wins and the
   ED is wrong.
3. **The Configuration Source is authoritative for reproducibility.** The prose here explains
   *why*; the config file is the *what* that CI/deploys actually consume.
4. **No duplication with ADRs.** An ED cites the ADR it realizes; it does not re-decide it.
5. **IDs are permanent and never reused;** next id is **ED-015**.

---

## ED Index
| ID | Title | Status | Realizes |
|----|-------|--------|----------|
| [ED-001](#ed-001--backend-language--runtime) | Backend language & runtime — Python 3.12 | Accepted | ADR-0014/0016, doc 12 |
| [ED-002](#ed-002--api-framework) | API framework — FastAPI + Pydantic | Accepted | ADR-0012, doc 10 |
| [ED-003](#ed-003--postgresql-deployment-realization) | PostgreSQL realization — `MarketDataRepository` port; SQLite dev backend, Postgres in prod | Accepted (rev. 2026-07-19) | ADR-0008, doc 07/12 |
| [ED-004](#ed-004--object-storage-realization) | Object-storage realization — `RawStore` port; filesystem dev backend, S3 in prod | Accepted (rev. 2026-07-17) | ADR-0009, doc 07/17 |
| [ED-005](#ed-005--orchestrator-product) | Orchestrator product | Proposed | doc 16, ADR-0010 |
| [ED-006](#ed-006--backend-cloud-vendor) | Backend cloud vendor | Proposed | doc 12 |
| [ED-007](#ed-007--test-framework) | Test framework — pytest | Accepted | doc 11 |
| [ED-008](#ed-008--architecture-guardrail-implementation) | Architecture guardrail lints — custom AST checks | Accepted | doc 03/06, ADR-0002/0003/0005 |
| [ED-009](#ed-009--linterformatter) | Linter/formatter — ruff | Accepted | doc 11 |
| [ED-010](#ed-010--property-based-testing-library) | Property-based testing — hypothesis (dev-only) | Accepted | doc 11 (B10) |
| [ED-011](#ed-011--application-composition-by-constructor-injection) | Application composition by constructor injection | Accepted | doc 02 (principle 5), doc 03, ADR-0005 |
| [ED-012](#ed-012--lineage-granularity-in-a-served-result) | Lineage granularity — contributing inputs + scanned count | Accepted | doc 04, ADR-0014/0017 |
| [ED-013](#ed-013--typed-diagnostics-on-the-analyticresult-envelope) | Typed diagnostics on the envelope | Accepted | doc 04, ADR-0014 |
| [ED-014](#ed-014--strangler-seam--server-side-proxy-rather-than-cors) | Strangler seam — server-side proxy, not CORS | Accepted | ADR-0020, doc 10/13 |

---

### ED-001 · Backend language & runtime
- **Status:** Accepted
- **Context:** The backend (L1–L9) needs a primary language. The prototype's proven analytics
  math lives in `shared/calculations.py` (pure pandas/NumPy); the domain requires exact decimal
  money ([ADR-0016](../architecture/18-architecture-decision-records.md#adr-0016--decimal-arithmetic-for-money)). The architecture is language-agnostic at its boundaries, so this is a
  realization choice, not an architectural one.
- **Decision:** **Python 3.12** as the single primary backend language.
- **Alternatives Considered:** *TypeScript/Node* (unifies with the frontend, but forces
  re-implementing proven math and has weaker decimal/numeric ergonomics); *Go/Rust* (performance
  the current scale does not need, at the cost of discarding the math and slowing iteration);
  *Java/Kotlin* (heavier ecosystem, no benefit here).
- **Consequences:** The prototype's math is *ported behind* the engine contract, not lifted
  verbatim ([ADR-0014](../architecture/18-architecture-decision-records.md#adr-0014--analytics-as-uniform-versioned-traced-engines)); money uses `decimal.Decimal` ([ADR-0016](../architecture/18-architecture-decision-records.md#adr-0016--decimal-arithmetic-for-money)). The frontend stays TypeScript
  (separate concern). Reversal is a full re-implementation of the *same* architecture — expensive
  but not an architectural migration (no boundary/contract/schema changes), which is precisely
  why this is an ED and not an ADR.
- **Configuration Source:** `.python-version`, `pyproject.toml` (`requires-python = ">=3.12"`).
- **Related Architecture Documents:** [ADR-0016](../architecture/18-architecture-decision-records.md#adr-0016--decimal-arithmetic-for-money), [ADR-0014](../architecture/18-architecture-decision-records.md#adr-0014--analytics-as-uniform-versioned-traced-engines), [doc 12](../architecture/12-deployment-strategy.md).

### ED-002 · API framework
- **Status:** Accepted
- **Context:** [ADR-0012](../architecture/18-architecture-decision-records.md#adr-0012--rest-first-api-as-the-single-client-contract) fixes the public contract as versioned, contract-first REST with typed
  DTOs. A Python framework must realize that contract; the framework itself is interchangeable
  behind it.
- **Decision:** **FastAPI (ASGI) + Pydantic v2** — typed DTOs, generated OpenAPI, native async.
- **Alternatives Considered:** *Flask* (mature but manual validation/OpenAPI); *Django REST
  Framework* (heavy, ORM-centric — tension with module-owned repositories, [ADR-0003](../architecture/18-architecture-decision-records.md#adr-0003--modular-monolith-with-module-owned-schemas)); *Litestar*
  (a viable equivalent, smaller ecosystem).
- **Consequences:** OpenAPI is generated (satisfies contract-first, [doc 10](../architecture/10-api-design.md)); DTOs are Pydantic
  projections of the domain, decoupled from storage; async supports doc 10's async-heavy-analytics
  rule. The framework is swappable behind the REST/OpenAPI contract without client impact.
- **Configuration Source:** `pyproject.toml` dependencies; the OpenAPI spec artifact.
- **Related Architecture Documents:** [ADR-0012](../architecture/18-architecture-decision-records.md#adr-0012--rest-first-api-as-the-single-client-contract), [doc 10](../architecture/10-api-design.md).

### ED-003 · PostgreSQL deployment realization
- **Status:** Accepted *(revised 2026-07-17; production vendor finalized at first deploy)*
- **Context:** [ADR-0008](../architecture/18-architecture-decision-records.md#adr-0008--postgresql-as-the-primary-system-of-record) fixes **PostgreSQL as the primary system of record** — architectural and
  unchanged. This ED records the *interface* and the *per-environment backend*. As with
  [ED-004](#ed-004--object-storage-realization), doc 12 provides distinct local/dev, staging and production environments, and
  standing up a database service to persist five instruments locally is disproportionate for a
  1–3 person team.
- **Decision:** A **`MarketDataRepository` port** is the interface — application code never
  touches a driver (doc 07 portability rule). Backends: **dev/CI = SQLite** via the Python
  **standard library** (`sqlite3`: zero dependencies, no service, no Docker);
  **production = managed PostgreSQL 16**, partition-capable, single vendor selected at deploy
  (Neon, Supabase, RDS/Aurora, Cloud SQL) per managed-first. The **schema shape is identical
  across both** (`backend/domain/market_data/schema.py`): module-owned tables, the
  `knowledge_time` version axis in the primary key, and a `CHECK` constraint making an
  index-level-with-a-currency unstorable. Money is stored as **exact text** in SQLite and as
  `NUMERIC` in PostgreSQL — never as a binary float in either.
- **Alternatives Considered:** *Postgres via docker-compose now* (literal compliance and
  exercises the real engine, but adds Docker + a service + a driver dependency and makes CI
  non-hermetic — disproportionate at this scale); *an in-memory repository* (smallest, but
  defers the substantive work — schema, DDL, exact round-trip, durability — and would prove
  nothing about persistence); *a non-Postgres engine in production* (out of scope — that would
  **supersede ADR-0008** and require an ADR, not an ED).
- **Consequences:** Zero new dependencies; CI stays hermetic and fast; real DDL, a real schema
  and real durability are exercised now. The port keeps Postgres a drop-in — a second
  implementation, not an application change. **Accepted costs:** SQL dialect differences must be
  absorbed by the Postgres implementation (notably `TEXT`→`NUMERIC` for money and native
  partitioning, neither exercised until deploy), and Postgres-specific behaviour (concurrency,
  connection pooling, partition pruning) is unproven until then. Escalation to a dedicated TSDB
  remains gated (ADR-0008).
- **Configuration Source:** `backend/domain/market_data/repository.py` (the port),
  `backend/domain/market_data/sqlite_repository.py` (dev/CI backend),
  `backend/domain/market_data/schema.py` (the schema); IaC/Terraform + secret store for the
  production instance, added at deploy.
- **Related Architecture Documents:** [ADR-0008](../architecture/18-architecture-decision-records.md#adr-0008--postgresql-as-the-primary-system-of-record), [ADR-0003](../architecture/18-architecture-decision-records.md#adr-0003--modular-monolith-with-module-owned-schemas), [doc 04](../architecture/04-canonical-domain-model.md), [doc 07](../architecture/07-database-design.md), [doc 12](../architecture/12-deployment-strategy.md).

> **Revision 2026-07-19 (M4a) — concurrency.** M2d built this backend for a single-threaded
> batch pipeline and documented it as not thread-safe. M4's serving plane invalidated that:
> a threaded ASGI worker calls the repository from arbitrary threads, and SQLite connections
> are thread-affine. The backend now opens with `check_same_thread=False` and serializes every
> statement through a lock (pinned by `backend/tests/domain/test_repository_concurrency.py`).
>
> **This is deliberately a development implementation choice, not a scalability strategy.**
> The lock makes one connection *safe*; it does not make the backend *concurrent* — every read
> and write is serialized, so throughput is single-threaded by construction. That is the right
> trade for a dev/CI backend whose job is exercising real DDL, real schema and exact decimal
> round-trips, and it is why SQLite could not serve production traffic with or without the lock.
>
> **It does not become a permanent bottleneck, because it does not travel.** The lock lives in
> `SqliteMarketDataRepository` — one of two implementations of the `MarketDataRepository` port.
> PostgreSQL (ADR-0008) uses a connection pool and no application-level lock. The port, the
> feature layer and the API hold no lock of their own and are unchanged by the swap.
>
> **Additional accepted cost:** concurrency behaviour is now also unproven until deploy.
> Serving-plane load characteristics measured against SQLite will not transfer to Postgres, so
> the doc 11 load tier and the Phase 0.5 recompute-RTO number must be re-measured against the
> real backend rather than extrapolated from local runs.


### ED-004 · Object-storage realization
- **Status:** Accepted *(revised 2026-07-17; production vendor finalized at first deploy)*
- **Context:** [ADR-0009](../architecture/18-architecture-decision-records.md#adr-0009--object-storage-for-immutable-raw-capture-and-deep-history) fixes **object storage for immutable raw capture** — raw is never in the
  hot relational store and never discarded. That is architectural and unchanged. This ED records
  the *interface* and the *per-environment backend*. Standing up MinIO/Docker/boto3 to capture
  five instruments locally is disproportionate for a 1–3 person team, and doc 12 explicitly
  provides distinct local/dev, staging and production environments with environment-injected
  backing services.
- **Decision:** A provider-neutral **`RawStore` port** (append-only, immutable objects, portable
  keys, prefix listing) is the interface — *not* a vendor SDK. Backends:
  **dev/CI = `FilesystemObjectStore`**, a first-class reference implementation of that port;
  **production = a managed S3-compatible object store** (ADR-0009), added as a second
  implementation at first deploy. The **object-key layout is backend-independent** and maps 1:1
  onto S3 keys — `raw/v1/{provider}/{dataset}/{window}/{instrument}/{payload_sha256}.json` —
  with `{window}` as the per-source-window **crypto-shred scope** (doc 17/13).
- **Alternatives Considered:** *MinIO via docker-compose now* (literal compliance and exercises
  the S3 path, but adds Docker + a service + boto3, slows the local loop, and makes CI
  non-hermetic — disproportionate at this scale); *write both backends now* (S3 fidelity on
  demand, but writes S3 code before it is needed and doubles maintenance from day one);
  *raw in Postgres* (rejected by ADR-0009 — would require a superseding ADR).
- **Consequences:** Zero new dependencies or infrastructure; CI stays hermetic and fast. The
  port keeps the S3 backend a drop-in — swapping it changes one module, not the application.
  Append-only/immutable semantics and the shred-scope prefix are preserved, so lawful erasure
  remains feasible without architectural change. **Accepted costs:** the S3 code path is not
  exercised until first deploy (deferring discovery of SDK/auth/consistency issues), and the
  Phase 0.5 recompute-from-raw timing is a **local filesystem baseline, not object-storage
  evidence** — it must be labelled as such and re-measured against real object storage at first
  deploy (doc 12 already requires re-measurement as volume grows).
- **Configuration Source:** `backend/ingestion/raw_store.py` (the port),
  `backend/ingestion/filesystem_object_store.py` (dev/CI backend),
  `backend/ingestion/raw_capture.py` (key layout); IaC/Terraform + secret store for the
  production bucket, added at deploy.
- **Related Architecture Documents:** [ADR-0009](../architecture/18-architecture-decision-records.md#adr-0009--object-storage-for-immutable-raw-capture-and-deep-history), [doc 05](../architecture/05-market-data-architecture.md), [doc 07](../architecture/07-database-design.md), [doc 12](../architecture/12-deployment-strategy.md), [doc 17](../architecture/17-entitlements-and-data-governance.md).

### ED-005 · Orchestrator product
- **Status:** Proposed *(the most architecture-adjacent ED — document any change carefully)*
- **Context:** [doc 16](../architecture/16-data-orchestration-and-freshness.md) fixes the **orchestration model** (declared DAGs, idempotent keyed tasks,
  the invalidation protocol) and explicitly states *the specific product is a selection*. This ED
  records that product.
- **Decision:** Recommend **Dagster** (asset-oriented; its asset graph maps naturally onto doc
  16's derived-data dependency graph and future invalidation wiring; strong local-dev story),
  used in its **minimal** form for the Walking Skeleton's single forward-only DAG.
- **Alternatives Considered:** *Temporal* (durable workflows, very powerful but heavier and
  steeper; a stronger fit only if/when an event-driven backbone is later un-gated, [ADR-0010](../architecture/18-architecture-decision-records.md#adr-0010--defer-the-event-bus));
  *Prefect* (lightweight, flexible; weaker asset/lineage alignment); *ad-hoc cron/scripts*
  (rejected — [doc 16](../architecture/16-data-orchestration-and-freshness.md) forbids undeclared cron above the skeleton).
- **Consequences:** The asset model aligns the orchestrator with the doc-16 dependency graph,
  easing Phase-2 invalidation. **Reversal cost is real but bounded** (re-expressing DAGs), which
  is why this is flagged as the ED to change most deliberately — but it remains an ED because the
  *model* it serves is already architectural (doc 16), unchanged by the product.
- **Configuration Source:** orchestrator project/workspace config; deployment config.
- **Related Architecture Documents:** [doc 16](../architecture/16-data-orchestration-and-freshness.md), [ADR-0010](../architecture/18-architecture-decision-records.md#adr-0010--defer-the-event-bus), [doc 12](../architecture/12-deployment-strategy.md).

### ED-006 · Backend cloud vendor
- **Status:** Proposed *(vendor finalized at first deploy)*
- **Context:** [doc 12](../architecture/12-deployment-strategy.md) already fixes the **deployment-model stance** — single cloud on the
  critical path until a measured reason to diversify, managed-first, API on containers (not
  serverless edge). Those are architectural and approved. This ED records **only the vendor
  selection** under that stance.
- **Decision:** A **single backend cloud vendor**, TBD at deploy, chosen to co-host the managed
  Postgres (ED-003), object storage (ED-004), and orchestrator (ED-005) to minimize ops surface
  for a 1–3 person team. API runs on **containers**. The existing frontend stays on Vercel.
- **Alternatives Considered:** *Multi-cloud now* (rejected by the doc-12 stance until a measured
  need); *serverless-edge API* (rejected by doc 12 — the API is stateful/DB-connected).
- **Consequences:** Consolidating managed services with one vendor reduces operational load;
  portability escape hatches (SQL, S3 API, containers) are documented, not pre-built (principle
  18). A vendor change is a re-host of managed services, not an architectural migration.
- **Configuration Source:** IaC/Terraform; deployment/environment config.
- **Related Architecture Documents:** [doc 12](../architecture/12-deployment-strategy.md), [ADR-0008](../architecture/18-architecture-decision-records.md#adr-0008--postgresql-as-the-primary-system-of-record), [ADR-0009](../architecture/18-architecture-decision-records.md#adr-0009--object-storage-for-immutable-raw-capture-and-deep-history).

### ED-007 · Test framework
- **Status:** Accepted
- **Context:** Doc 11 mandates hermetic, reproducible tests across several tiers (unit,
  contract, integration, guardrail). A Python test runner is needed from M1.
- **Decision:** **pytest** (+ **pytest-cov** for targeted coverage), pinned in `pyproject.toml`.
- **Alternatives Considered:** *stdlib `unittest`* (works, but weaker fixtures/parametrization
  and no ecosystem for property/contract tiers later); *nose2* (effectively unmaintained).
- **Consequences:** Fixtures/parametrization suit the guardrail and (later) property-based and
  contract tiers ([doc 11](../architecture/11-testing-strategy.md)); coverage is targeted, not vanity (principle 18). Runner is
  swappable — tests are plain assertions.
- **Configuration Source:** `pyproject.toml` (`[project.optional-dependencies] dev`,
  `[tool.pytest.ini_options]`, `[tool.coverage.run]`).
- **Related Architecture Documents:** [doc 11](../architecture/11-testing-strategy.md).

### ED-008 · Architecture guardrail implementation
- **Status:** Accepted
- **Context:** Doc 03/06 and ADR-0002/0003/0005 require CI to fail on an upward import, a
  vendor name above L1, or a cross-module schema read. An enforcement mechanism is needed.
- **Decision:** **Custom, stdlib-only AST checks** in `tools/ci/` (dependency-direction,
  no-vendor-above-L1, module-schema-isolation), driven by a single machine-readable
  `architecture_map.py`.
- **Alternatives Considered:** *import-linter* (good for layer contracts, but does not express
  the vendor-token or module-owned-schema rules, and adds a dependency + config dialect);
  *pydeps/grimp alone* (visualization, not enforcement); *hand review* (rejected — the whole
  point is that the rule is structural, not discretionary).
- **Consequences:** One dependency-free source of truth for the layer graph; the vendor and
  schema rules are first-class; the checks run anywhere with no third-party install. Trade-off:
  we maintain ~150 lines of lint code (covered by its own tests).
- **Configuration Source:** `tools/ci/architecture_map.py` (the rules); `tools/ci/*.py` (the
  checks); `.github/workflows/ci.yml` + `Makefile` (invocation — the workflow runs the
  same three steps as `make check`, in the same order).
- **Related Architecture Documents:** [doc 03](../architecture/03-system-architecture.md), [doc 06](../architecture/06-provider-abstraction-layer.md), [ADR-0002](../architecture/18-architecture-decision-records.md#adr-0002--strictly-layered-architecture-with-an-enforced-dependency-direction)/[0003](../architecture/18-architecture-decision-records.md#adr-0003--modular-monolith-with-module-owned-schemas)/[0005](../architecture/18-architecture-decision-records.md#adr-0005--provider-abstraction-via-portsadapters), [doc 11](../architecture/11-testing-strategy.md).

### ED-009 · Linter/formatter
- **Status:** Accepted
- **Context:** Consistent style and a fast import/order/bug lint keep the codebase reviewable.
- **Decision:** **ruff** (lint + import sorting), pinned in `pyproject.toml`.
- **Alternatives Considered:** *flake8 + isort + black* (three tools where one suffices);
  *pylint* (slower, noisier).
- **Consequences:** One fast tool; config lives in `pyproject.toml`; swappable (style only,
  no architectural weight).
- **Configuration Source:** `pyproject.toml` (`[tool.ruff]`, `[tool.ruff.lint]`).
- **Related Architecture Documents:** [doc 11](../architecture/11-testing-strategy.md).

### ED-010 · Property-based testing library
- **Status:** Accepted
- **Context:** [Doc 11](../architecture/11-testing-strategy.md) (hardened per review B10) makes property-based tests a **mandatory**
  tier for financial correctness — "the bugs no one thought to hand-compute" — alongside
  reference values and an independent reference implementation. M3 is the first milestone with
  financial math to test, so the mechanism is needed now. Doc 11 also requires the suite to stay
  hermetic with fixed seeds, which a randomized generator threatens by default.
- **Decision:** **hypothesis**, pinned in `pyproject.toml` under `[project.optional-dependencies] dev`,
  run under a `hermetic` profile (`derandomize=True`, `deadline=None`) registered in
  `backend/tests/conftest.py`.
- **Alternatives Considered:** *hand-rolled generators over `random.Random(seed)`* — zero new
  dependencies, but reimplements shrinking badly, and a minimal counterexample is most of what
  makes a failing property test actionable; *skip the tier* — rejected, doc 11 mandates it.
- **Consequences:** **Runtime dependencies remain zero** — this is dev-only, so nothing ships.
  `derandomize` makes a given commit always explore the same inputs, so failures are reproducible
  and green runs repeatable; `deadline=None` removes a wall-clock dependence masquerading as a
  correctness check. Reversal cost is low: the properties are plain assertions over generated
  lists and would survive a change of generator.
- **Configuration Source:** `pyproject.toml` (`[project.optional-dependencies] dev`);
  `backend/tests/conftest.py` (the hermetic profile).
- **Related Architecture Documents:** [doc 11](../architecture/11-testing-strategy.md); complements [ED-007](#ed-007--test-framework) (pytest).

### ED-011 · Application composition by constructor injection
- **Status:** Accepted
- **Context:** M4 needs a repository (L5) → feature (L6) → engine (L7) assembled to serve one
  metric. Reading the dependency map alone suggests no layer may do this: [doc 03](../architecture/03-system-architecture.md) grants L9 only
  L7 and L8, [doc 08](../architecture/08-analytics-framework.md) forbids engines from touching repositories, and nothing may import
  orchestration. This was initially raised as an architectural conflict warranting an ADR.
  **Re-reading the architecture against intent showed it is not one.** [Doc 02](../architecture/02-engineering-principles.md) principle 5
  governs what a layer may *depend on* — "only the layer directly beneath it **(via that layer's
  published contract)**" — and is silent on who *constructs* objects. Its stated concern is
  reach-arounds: the frontend reading the database, AI reading providers, analytics reading raw
  payloads. Being handed an already-built collaborator is not a reach-around.
- **Decision:** **Layers receive their collaborators as parameters; construction happens at the
  process entry point.** Concretely: L6 exposes `close_price_series_provider(repository)`, binding
  the repository inside the only layer permitted to hold one; L7 exposes
  `one_year_return_for(instrument_id, provider, …)`, consuming L6's published contract without
  ever seeing a repository; L9's `create_app(metric_service, clock=…)` takes the composed service
  and the clock. **No layer imports a concrete implementation from another layer**, and the
  dependency lint is unchanged — `api → features` and `api → domain` still fail, as they should.
- **Alternatives Considered:** *widen the map so `api` may import `features`/`domain`* — reopens
  the reach-around [doc 08](../architecture/08-analytics-framework.md) deliberately closed in v2.0; *a `composition.py` inside `backend/`
  exempt from the layer rule* — a new architectural concept for a problem plain injection solves;
  *compose inside the engine* — violates [ADR-0014](../architecture/18-architecture-decision-records.md#adr-0014--analytics-as-uniform-versioned-traced-engines) outright; *a composition root under `tools/`* —
  passes the lint on a technicality (it scans `backend/` only) while putting product code in a
  package `pyproject.toml` declares to be repo tooling.
- **Consequences:** The layer rule holds literally, not by convention — verified by the lint
  refusing the two forbidden imports. Dependency injection was already this codebase's practice
  (`YFinanceAdapter(fetcher=…)`, `build_close_price_series(repository, …)`), so this records an
  existing convention rather than introducing one; ports/adapters ([ADR-0005](../architecture/18-architecture-decision-records.md#adr-0005--provider-abstraction-via-portsadapters)) implies it. **No
  production entry point exists yet:** M4a ships the endpoint with composition performed in test
  fixtures, because binding a concrete repository is deployment work, deferred with M4b/M5.
  Reversal is a refactor, not a migration — the ED threshold.
- **Realized in M4b:** `backend/main.py` is the composition root, declared as
  `architecture_map.COMPOSITION_ROOT` and pinned by two guardrail tests — it is the only
  unlayered module under `backend/`, and it contains no control flow. It exposes an **application
  factory** (`create_app()`, loaded via `uvicorn --factory`) rather than a module-level `app`, so
  importing the entry point provisions nothing; the environment is read only when the factory is
  called.
- **Configuration Source:** `backend/features/returns.py` (`close_price_series_provider`),
  `backend/analytics/one_year_return.py` (`one_year_return_for`), `backend/api/app.py`
  (`create_app`), `backend/main.py` (the root), `tools/ci/architecture_map.py`
  (`COMPOSITION_ROOT`).
- **Related Architecture Documents:** [doc 02](../architecture/02-engineering-principles.md) principle 5, [doc 03](../architecture/03-system-architecture.md), [doc 08](../architecture/08-analytics-framework.md), [ADR-0005](../architecture/18-architecture-decision-records.md#adr-0005--provider-abstraction-via-portsadapters).

### ED-012 · Lineage granularity in a served result
- **Status:** Accepted
- **Context:** `AnalyticResult.lineage` carried one `ObservationRef` for every observation the
  feature scanned — 400 for a 400-bar series — where the engine reads two. Serializing that makes
  a single-metric response kilobytes of lineage a client cannot use, growing with history rather
  than with the answer. Recorded as [PROJECT_CONTEXT](../PROJECT_CONTEXT.md) §11 Decision 1; approved 2026-07-19.
- **Decision:** The engine names the observations that **actually determined the value**
  (`LineageHandle.contributing`); the scanned set stays available in-process and is summarized on
  the wire as `scanned_count`. An additive envelope field, spending [ADR-0014](../architecture/18-architecture-decision-records.md#adr-0014--analytics-as-uniform-versioned-traced-engines)'s revisit clause
  ("extend it additively"), which is why this is an ED and not ADR-0021.
- **Alternatives Considered:** *serve the full scanned set* — unbounded payload growth; *lineage
  by reference via a second endpoint* — [doc 10](../architecture/10-api-design.md) sanctions it ("expose **or link to**") and it is the
  likely Phase-1 shape, but M4's fence permits exactly one endpoint. The chosen shape is
  forward-compatible with it.
- **Consequences:** Response size tracks the answer. Recomputability is preserved — feature
  version, feature parameters and raw payload handles are all still pinned, so the series can be
  rebuilt and the result re-derived ([ADR-0017](../architecture/18-architecture-decision-records.md#adr-0017--first-class-lineage-with-three-guarantee-tiers) *recomputable* tier). The engine now depends on
  the series' index invariant (`points[i]` ↔ `lineage.inputs[i]`), which is pinned by a test.
- **Configuration Source:** `backend/domain/model/analytics.py` (`LineageHandle`),
  `backend/api/dto.py` (`LineageDTO`).
- **Related Architecture Documents:** [doc 04](../architecture/04-canonical-domain-model.md), [doc 10](../architecture/10-api-design.md), [ADR-0014](../architecture/18-architecture-decision-records.md#adr-0014--analytics-as-uniform-versioned-traced-engines), [ADR-0017](../architecture/18-architecture-decision-records.md#adr-0017--first-class-lineage-with-three-guarantee-tiers).

### ED-013 · Typed diagnostics on the `AnalyticResult` envelope
- **Status:** Accepted
- **Context:** The engine reported how far the anchor bar sat from the one-year target by encoding
  a number inside a quality flag (`anchor-offset-days:-3`). `quality_flags` is otherwise a set of
  opaque tags, so recovering the number meant string-parsing — at the API edge, which [doc 10](../architecture/10-api-design.md)
  forbids ("the API is a thin, validated projection"). Recorded as [PROJECT_CONTEXT](../PROJECT_CONTEXT.md) §11
  Decision 2; approved 2026-07-19.
- **Decision:** A typed `diagnostics: tuple[tuple[str, float], ...]` field on the envelope,
  serialized as a JSON object. `quality_flags` returns to being purely opaque tags. Additive, per
  the same [ADR-0014](../architecture/18-architecture-decision-records.md#adr-0014--analytics-as-uniform-versioned-traced-engines) clause as ED-012.
- **Alternatives Considered:** *keep it in the flag string* — pushes parsing to every consumer;
  *drop the offset* — the methodology catalog lists anchor approximation as a mandatory
  limitation, so hiding it at the API would contradict the published entry.
- **Consequences:** Consumers treating flags as opaque — the correct reading — no longer silently
  drop the information. Sorted pairs rather than a dict keep the frozen envelope hashable and
  comparison deterministic.
- **Configuration Source:** `backend/domain/model/analytics.py` (`AnalyticResult.diagnostics`),
  `backend/analytics/one_year_return.py` (`ANCHOR_OFFSET_DAYS`).
- **Related Architecture Documents:** [doc 04](../architecture/04-canonical-domain-model.md), [doc 08](../architecture/08-analytics-framework.md), [doc 10](../architecture/10-api-design.md), [ADR-0014](../architecture/18-architecture-decision-records.md#adr-0014--analytics-as-uniform-versioned-traced-engines).

### ED-014 · Strangler seam — server-side proxy rather than CORS
- **Status:** Accepted
- **Context:** M4b required the live Next.js site to render a value from the new backend
  *beside* its existing snapshot JSON ([ADR-0020](../architecture/18-architecture-decision-records.md#adr-0020--walking-skeleton-first-strangle-the-prototype)). The browser and the API are different origins,
  so a client-side fetch needs CORS configured on the API. The architecture is silent on CORS —
  [doc 13](../architecture/13-security.md) owns auth and secrets, not browser mechanics — so this is an implementation choice.
- **Decision:** The frontend calls a **same-origin Next.js route handler**
  (`web/app/api/metrics/one-year-return/route.ts`) that proxies to the backend server-side. **No
  CORS middleware is added to the API**, and the backend origin is a server-side
  `NIVESH_API_BASE_URL`, never a `NEXT_PUBLIC_` value baked into the client bundle.
- **Alternatives Considered:** *CORS middleware on the API* — works, but adds middleware, puts an
  allowed-origin list in backend config, and publishes the backend origin to every visitor;
  *a Next.js server component* — no CORS either, but awkward to place inside the existing
  client-rendered pane grid, and it couples page rendering to backend availability.
- **Consequences:** The seam is one file and deleting it returns the site to snapshot-only, which
  is what makes the strangler reversible. The proxy passes the DTO through **unchanged** — it is a
  pipe, not a mapper, so the OpenAPI spec stays the single source of truth. It degrades rather
  than fails: unset base URL, timeout (4s), non-200, and unreachable host all return an explicit
  `{"status": "UNREACHABLE", reason}` body the pane renders as an offline state. **Verified by
  running both halves and killing the API mid-session** — the live pane showed "api offline"
  while every snapshot pane kept working.
- **Configuration Source:** `web/app/api/metrics/one-year-return/route.ts`; `NIVESH_API_BASE_URL`.
- **Related Architecture Documents:** [ADR-0020](../architecture/18-architecture-decision-records.md#adr-0020--walking-skeleton-first-strangle-the-prototype), [doc 10](../architecture/10-api-design.md), [doc 15](../architecture/15-development-roadmap.md).

---

## Change log
| Date | Change | Rationale |
|------|--------|-----------|
| 2026-07-17 | Log created; ED-001…ED-006 recorded — the technology selections that realize Architecture v2.0, classified as implementation decisions (not ADRs) per the doc-18 threshold rule. | The six selections change no architectural boundary/contract/deployment-model; the architectural decisions they realize are already owned by ADR-0008/0009/0012/0014/0016 and docs 12/16. Keeps the ADR registry concise. |
| 2026-07-17 | **ED-007…ED-009 recorded** during Milestone M1 (test framework = pytest; guardrail lints = custom AST checks; linter/formatter = ruff). | M1 introduces and uses these tools; they are implementation/tooling details below the ADR threshold. |
| 2026-07-17 | **ED-003 revised** (Proposed → Accepted): interface is a `MarketDataRepository` port; dev/CI backend is stdlib SQLite; production remains managed PostgreSQL; one schema shape across both. | Same environment reasoning as ED-004: ADR-0008 fixes the **deployed** system of record; the local backend is ED-tier. SQLite is stdlib, so it adds zero dependencies and no Docker while still exercising real DDL, schema, exact-decimal round-trip and durability. Accepted cost recorded: SQL dialect differences and Postgres-specific behaviour unproven until deploy. |
| 2026-07-17 | **ED-004 revised** (Proposed → Accepted): interface is a provider-neutral `RawStore` port; dev/CI backend is a first-class `FilesystemObjectStore`; production remains S3-compatible object storage; key layout is backend-independent and S3-mapping. | Governance review determined object storage is architectural **for the deployed platform** (ADR-0009, unchanged), while the per-environment backend is ED-tier (doc 12 distinct environments). Applies the minimalism principle: no Docker/MinIO/boto3 until first deploy. Accepted cost recorded: S3 path unexercised until deploy; skeleton RTO is a local baseline. |
| 2026-07-18 | **ED-010 recorded** during Milestone M3: hypothesis as the property-based testing library, dev-only, under a derandomized hermetic profile. | M3 is the first milestone with financial math, and doc 11 makes the property tier mandatory for it. Dev-only, so the zero-runtime-dependency position is unchanged. Next id: ED-011. |
| 2026-07-19 | **ED-011…ED-013 recorded** during M4a: composition by constructor injection; contributing-input lineage; typed diagnostics. | ED-011 resolves what was first raised as an architectural conflict — re-reading doc 02 principle 5 showed it governs dependency, not construction, so no ADR was warranted and ADR-0021 remains unused. ED-012/013 spend ADR-0014's additive-extension clause. Next id: ED-014. |
| 2026-07-19 | **ED-003 revised** (M4a): the SQLite dev backend is now thread-safe — `check_same_thread=False` plus a lock serializing every statement. | M2d's "single-threaded pipeline" assumption was invalidated by M4's serving plane; a threaded ASGI worker calls the repository from arbitrary threads. Recorded explicitly as a development implementation choice, not a scalability strategy: the lock serializes all access and does not travel to the Postgres implementation. New accepted cost: concurrency behaviour is unproven until deploy, so load and RTO numbers must be re-measured against Postgres. |
| 2026-07-22 | **ED-014 recorded** during M4b: the strangler seam is a same-origin Next.js proxy, so no CORS middleware is added to the API. `backend/main.py` established as the ED-011 composition root and declared in `architecture_map.py`, with a guardrail test asserting it is the only unlayered module under `backend/`. | The dependency lint skips modules belonging to no layer, so an undeclared entry point would have been silently exempt from every rule. Declaring it turns a blind spot into a checked invariant. Next id: ED-015. |
