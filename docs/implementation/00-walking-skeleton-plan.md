# Implementation · 00 · Walking Skeleton Plan (Phase 0 + Phase 0.5)

| | |
|---|---|
| **Status** | Draft — implementation planning (not part of the frozen architecture set) |
| **Owner** | Chief Software Architect / implementing engineer |
| **Governed by** | Architecture v2.0 (`docs/architecture/`, APPROVED & FROZEN 2026-07-17) |
| **Implements** | [Roadmap doc 15](../architecture/15-development-roadmap.md) — Phase 0 & Phase 0.5; [ADR-0020](../architecture/18-architecture-decision-records.md#adr-0020--walking-skeleton-first-strangle-the-prototype) |
| **Precedence** | **Subordinate to the architecture.** If this plan and any `docs/architecture/` document ever disagree, the architecture wins and this plan is corrected — never the reverse. |

## Purpose
Translate the two entry phases of the approved roadmap — **Phase 0 (guardrails)** and
**Phase 0.5 (Walking Skeleton)** — into an actionable engineering plan that a small team can
execute, without deviating from Architecture v2.0. This is a *plan*, not code.

## Relationship to the architecture (and to change control)
1. This document **spends** the architecture; it does not amend it. Every build item below cites
   the architecture document / ADR it satisfies.
2. Per the frozen governance (README §Governance), every decision the architecture left open is
   first **classified** against the ADR threshold. The concrete technology selections this
   skeleton needs (language, framework, DB/object-storage host, orchestrator product, cloud
   vendor) are **implementation details that realize — but do not change — the approved
   architecture**, so they are **Engineering Decisions (ED-001…ED-006), not ADRs**. They are
   recorded in [Implementation doc 01 — Engineering Decision Log](01-engineering-decisions.md)
   and their config files, and must be recorded before the code that depends on them is written.
   *(The architectural decisions these realize are already owned — PostgreSQL by ADR-0008,
   object storage by ADR-0009, REST by ADR-0012, the orchestration model by doc 16, the
   single-cloud stance by doc 12 — so no new ADR is warranted. A selection that instead
   **replaced** one of those would require an ADR superseding it.)*
3. The Walking Skeleton is explicitly allowed to contain **one disposable exception** to
   "no API before the domain model" — a single throwaway endpoint scoped to one metric, re-cut
   on the hardened model in Phase 1 ([ADR-0020](../architecture/18-architecture-decision-records.md#adr-0020--walking-skeleton-first-strangle-the-prototype)). No other exceptions are permitted.

## Scope — what the skeleton is, and the fence around it
**The skeleton proves the *bones connect*, on the narrowest possible slice:** **5 instruments ·
1 provider · 1 metric · 1 endpoint**, threaded through *every* layer L0–L10 (minus L8 AI) once.

**Explicitly OUT of scope (the Phase 0.5 fence, doc 15 "Do NOT build yet"):**
- More than 5 instruments, more than 1 metric, more than 1 endpoint — **any breadth at all**.
- A second provider, a provider router, or multi-source reconciliation (Phase 5; [ADR-0005](../architecture/18-architecture-decision-records.md#adr-0005--provider-abstraction-via-portsadapters)).
- The AI layer L8 (Phase 7; [doc 09](../architecture/09-ai-framework.md)).
- Full price bitemporal *as-of queries* (Phase 6) — but `knowledge_time` **is populated now** (C1).
- The invalidation protocol / corporate-action reprocessing (Phase 2; [doc 16](../architecture/16-data-orchestration-and-freshness.md)). The skeleton's DAG runs forward only.
- The full entitlements engine, tiers, and licensed feeds (Phases 4/8; [doc 17](../architecture/17-entitlements-and-data-governance.md)).
- Fundamentals, economics, FX as first-class ingestion (later phases). *(FX is used read-only
  for one instrument's currency conversion — see data scope — not ingested as a data class.)*
- A dedicated TSDB, graph store, external cache, or event bus (all gated; [ADR-0008](../architecture/18-architecture-decision-records.md#adr-0008--postgresql-as-the-primary-system-of-record)/[0010](../architecture/18-architecture-decision-records.md#adr-0010--defer-the-event-bus)).

---

## Prerequisite · Engineering Decisions to record before any code (governance gate)
These are decisions the architecture deliberately left to implementation. Each is an
**Engineering Decision (not an ADR)** — it realizes an already-approved architectural decision
without changing it. Each must be recorded (status Accepted/Proposed) in
[doc 01 — Engineering Decision Log](01-engineering-decisions.md) and its config file **before**
the code that depends on it is written. Full context lives in doc 01; summarized here:

| ED | Decision | Selection | Realizes (already-owned architecture) |
|----|----------|-----------|----------------------------------------|
| [ED-001](01-engineering-decisions.md#ed-001--backend-language--runtime) | Backend language & runtime | **Python 3.12** (reuses proven `shared/calculations.py` math; decimal-native) | [ADR-0016](../architecture/18-architecture-decision-records.md#adr-0016--decimal-arithmetic-for-money)/[0014](../architecture/18-architecture-decision-records.md#adr-0014--analytics-as-uniform-versioned-traced-engines), [doc 12](../architecture/12-deployment-strategy.md) |
| [ED-002](01-engineering-decisions.md#ed-002--api-framework) | API framework | **FastAPI + Pydantic** (OpenAPI-first) | [ADR-0012](../architecture/18-architecture-decision-records.md#adr-0012--rest-first-api-as-the-single-client-contract), [doc 10](../architecture/10-api-design.md) |
| [ED-003](01-engineering-decisions.md#ed-003--postgresql-deployment-realization) | PostgreSQL deployment | Postgres 16; dev Docker, prod managed (vendor TBD) | [ADR-0008](../architecture/18-architecture-decision-records.md#adr-0008--postgresql-as-the-primary-system-of-record), [doc 07](../architecture/07-database-design.md)/[12](../architecture/12-deployment-strategy.md) |
| [ED-004](01-engineering-decisions.md#ed-004--object-storage-realization) | Object storage | S3 API; dev MinIO, prod managed (vendor TBD) | [ADR-0009](../architecture/18-architecture-decision-records.md#adr-0009--object-storage-for-immutable-raw-capture-and-deep-history), [doc 17](../architecture/17-entitlements-and-data-governance.md) |
| [ED-005](01-engineering-decisions.md#ed-005--orchestrator-product) | Orchestrator product | Recommend **Dagster**, minimal form | [doc 16](../architecture/16-data-orchestration-and-freshness.md), [ADR-0010](../architecture/18-architecture-decision-records.md#adr-0010--defer-the-event-bus) |
| [ED-006](01-engineering-decisions.md#ed-006--backend-cloud-vendor) | Backend cloud vendor | Single vendor TBD; API on containers | [doc 12](../architecture/12-deployment-strategy.md) |

> These EDs are the true first work item. They are *selections within* the frozen architecture,
> not changes to it — so they follow the **Engineering Decision** process, keeping the ADR
> registry reserved for long-lived architectural decisions.

---

## Part A · Phase 0 — Guardrails first (before any feature code)
**Objective (doc 15):** stand up the mechanisms that *enforce* the architecture, so the skeleton
cannot violate it even by accident.

### A1 · Repository structure — layer packages with module-owned boundaries
Proposed layout, realizing the L0–L10 stack ([doc 03](../architecture/03-system-architecture.md)) and module-owned schemas ([ADR-0003](../architecture/18-architecture-decision-records.md#adr-0003--modular-monolith-with-module-owned-schemas)).
The existing prototype (`shared/`, `web/`, `tickers/`) stays live and untouched during Phase 0.5
(strangler, [ADR-0020](../architecture/18-architecture-decision-records.md#adr-0020--walking-skeleton-first-strangle-the-prototype)); new code lands under `backend/`.

```
backend/
  platform/          shared kernel: Quantity value type (decimal money), InstrumentId,
                     AnalyticResult envelope shape, lineage types      → docs 02/04
  providers/         L1 — vendor knowledge quarantined here and ONLY here → doc 06
    ports/           canonical port interfaces (PriceHistoryPort, …)
    yfinance/        the one adapter (the only place "yfinance" may appear)
  ingestion/         L2–L4 — raw capture, validation gate, normalization  → doc 05
  domain/            L5 — canonical model + repositories; owns its schema  → docs 04/07
    market_data/     module-owned Postgres schema (no cross-module reads)
  features/          L6 — versioned feature definitions (only layer with repo access) → doc 08
  analytics/         L7 — engines producing AnalyticResults               → doc 08
  api/               L9 — REST, OpenAPI-first, DTO projections            → doc 10
  orchestration/     DAG definitions                                      → doc 16
  tests/             the test tiers (see Part B testing)                  → doc 11
tools/ci/            the enforcement lints
web/                 EXISTING Next.js frontend (L10) — strangled, not rewritten
```

### A2 · Module → owning-document map (Phase 0 success criterion: exactly one owner each)
| Module | Layer | Owning doc |
|--------|-------|-----------|
| `platform` | kernel | 02, 04 |
| `providers` | L1 | 06 |
| `ingestion` | L2–L4 | 05 |
| `domain` | L5 | 04, 07 |
| `features` | L6 | 08 |
| `analytics` | L7 | 08 |
| `api` | L9 | 10 |
| `orchestration` | — | 16 |

### A3 · CI enforcement (the guardrails that make the architecture structural)
Three lints + a test runner, all blocking on the default branch ([doc 03](../architecture/03-system-architecture.md)/[11](../architecture/11-testing-strategy.md)):
1. **Dependency-direction lint** — a module may import only the layer directly beneath it; an
   "upward" import fails CI ([ADR-0002](../architecture/18-architecture-decision-records.md#adr-0002--strictly-layered-architecture-with-an-enforced-dependency-direction)).
2. **No-vendor-name-above-L1** — the string `yfinance` (and any future vendor) is a build
   failure anywhere outside `backend/providers/yfinance/` ([ADR-0005](../architecture/18-architecture-decision-records.md#adr-0005--provider-abstraction-via-portsadapters)).
3. **No-cross-module-table-access** — a module may touch only its own schema; cross-module data
   goes through repository interfaces ([ADR-0003](../architecture/18-architecture-decision-records.md#adr-0003--modular-monolith-with-module-owned-schemas)).
4. **Test runner** — executes the (initially tiny) suites hermetically with pinned versions and
   fixed seeds ([doc 11](../architecture/11-testing-strategy.md)).

### A4 · Conventions to establish
- **Methodology catalog** — the versioned home for the one formula the skeleton ships (1Y
  return), incl. definition, assumptions, limitations ([doc 08](../architecture/08-analytics-framework.md)).
- **Engineering Decision log** — ED-001…ED-006 recorded in [doc 01](01-engineering-decisions.md) (Prerequisite table);
  ADR conventions (doc 18) stay reserved for architectural change (next id ADR-0021, unused).

### A5 · Definition of Done — Phase 0
- [ ] An upward import, a leaked vendor string, or a cross-module table read **fails CI**.
- [ ] Every module maps to exactly one owning document (table A2).
- [ ] CI runs the empty/tiny test suite green; seeds pinned; builds reproducible.
- [ ] ED-001…ED-006 are recorded in the Engineering Decision Log ([doc 01](01-engineering-decisions.md)). **No feature code exists yet.**

---

## Part B · Phase 0.5 — The Walking Skeleton

### B1 · Data scope (chosen to stress the exact bugs the domain model prevents)
**5 instruments** — deliberately mixed so the thin slice exercises identity, currency, and type:
| Internal instrument | Vendor symbol | Type | Currency | Why included |
|---------------------|---------------|------|----------|--------------|
| RELIANCE (NSE) | `RELIANCE.NS` | equity | INR | baseline Indian equity |
| TCS (NSE) | `TCS.NS` | equity | INR | second equity, same market |
| INFY (NSE) | `INFY.NS` | equity | INR | third equity |
| Nifty 50 | `^NSEI` | **index** | INR (points) | **must NOT be FX-converted** — validates the index-vs-equity type rule (the prototype's ~95× bug) |
| Apple | `AAPL` | equity | **USD** | exercises the USD→INR FX read path + a ticker-collision-prone symbol |

**1 provider:** yfinance ([ADR-0005](../architecture/18-architecture-decision-records.md#adr-0005--provider-abstraction-via-portsadapters), cleaned from prototype `data_loader.py`). **1 metric:** **1-year total
return** (from adjusted close) — a unitless ratio, chosen because it needs a price-history
feature and exercises the decimal→float seam (C3), as-of correctness, and end-to-end lineage.

### B2 · Layer-by-layer build (minimal per layer; what is stubbed/deferred is explicit)
| Layer | Skeleton build (minimal) | Deferred / stubbed | Doc |
|-------|--------------------------|--------------------|-----|
| **L0 Provider** | yfinance (external) | — | — |
| **L1 Adapter** | `PriceHistoryPort` + one yfinance adapter; canonical request in, raw payload + fetch metadata out; **versioned raw-payload contract** with drift → `Malformed`; symbology for the 5 instruments only | router, failover, other ports | [06](../architecture/06-provider-abstraction-layer.md) |
| **L2 Raw Store** | append-only capture of the verbatim payload + `fetched_at` into object storage; per-scope key placeholder for future crypto-shred | retention automation, archive tiering | [05](../architecture/05-market-data-architecture.md)/[07](../architecture/07-database-design.md) |
| **L3 Validation** | fail-closed gate: schema + range (price>0, volume≥0) + **index-not-FX-converted** + calendar sanity; quarantine path; stamp `authoritative` | cross-source corroboration (no 2nd source) | [05](../architecture/05-market-data-architecture.md) |
| **L4 Normalization** | → `PriceObservation` with typed **decimal** Quantity + currency; **`event_time` + `knowledge_time` both populated (C1)**; **native currency preserved** — equities are `Money(currency)`, indices are unitless `IndexLevel`, making FX conversion of `^NSEI` *type-impossible*; **reference-data snapshot version pinned** on the run | FX **conversion** (needs `FXRate`, a later data class — see decision log); full corporate-action adjustment engine | [04](../architecture/04-canonical-domain-model.md)/[05](../architecture/05-market-data-architecture.md) |
| **L5 Domain Store** | Postgres `market_data` schema; effective-dated prices; repository interface; lineage handle stored per observation | other schemas/entities (Phase 1) | [04](../architecture/04-canonical-domain-model.md)/[07](../architecture/07-database-design.md) |
| **L6 Feature** | one versioned feature (the adjusted-close return series inputs); **the single decimal→float conversion happens here (C3)**; lineage-carrying | feature breadth | [08](../architecture/08-analytics-framework.md) |
| **L7 Engine** | one `one_year_return` engine → **`AnalyticResult` envelope** (value, inputs, feature+formula+reference versions, as_of, quality flags, lineage handle); pure/deterministic; missing data → `Unavailable`, never zero | all other engines; scoring | [08](../architecture/08-analytics-framework.md) |
| **L8 AI** | **NOT BUILT** | entire layer (Phase 7) | [09](../architecture/09-ai-framework.md) |
| **L9 API** | one OpenAPI-first typed endpoint returning the metric as a **DTO projection** + lineage reference + freshness (`as_of`/`computed_at`); single public tier | entitlement tiers, async engine, breadth | [10](../architecture/10-api-design.md) |
| **L10 Frontend** | existing Next.js renders the one endpoint's value + a minimal "why?" (lineage) + freshness, **alongside** current snapshot JSON (strangler proof) | migration of other surfaces | [10](../architecture/10-api-design.md)/[15](../architecture/15-development-roadmap.md) |

### B3 · The one vertical trace (must run end-to-end, once)
```
yfinance.fetch(5 instruments)                         L1
  → raw_record{payload, fetched_at}  (object storage) L2  immutable
  → validate(schema,range,index-not-FX,calendar)      L3  → accept | quarantine
  → normalize → PriceObservation{decimal, ccy,        L4  event_time + knowledge_time(C1),
                                  ref_snapshot_ver}         USD→INR for AAPL only
  → repo.save (market_data schema)                    L5  + lineage handle
  → feature: return_series (decimal→float seam, C3)   L6  versioned
  → engine: one_year_return(v1)                       L7  → AnalyticResult{value, lineage, as_of}
  → GET /v1/instruments/{id}/metrics/one-year-return  L9  DTO + lineage ref + freshness
  → terminal renders value + "why?" + freshness       L10 next to snapshot JSON
```

### B4 · Orchestration (minimal DAG, forward-only)
A single DAG on the chosen orchestrator ([doc 16](../architecture/16-data-orchestration-and-freshness.md); product per [ED-005](01-engineering-decisions.md#ed-005--orchestrator-product)), tasks **idempotent and keyed**,
chaining fetch → validate → normalize → persist → materialize-feature → materialize-metric.
The DAG run records code + reference-snapshot versions as a lineage event. **No invalidation
protocol, no reprocessing** — that is Phase 2; the skeleton only proves the DAG shape works.

### B5 · Lineage end-to-end (the differentiator, tested)
For the one metric, the stored `AnalyticResult` must resolve, in bounded queries, to:
feature version → `PriceObservation`s → raw record(s) in object storage → provider +
reference-snapshot version + `formula_version`. Guarantee tier for this served value:
**recomputable** and (given pinned reference snapshot) **bit-reproducible** ([ADR-0017](../architecture/18-architecture-decision-records.md#adr-0017--first-class-lineage-with-three-guarantee-tiers), principle 6).

### B6 · Recompute-from-raw RTO measurement (a required Phase 0.5 deliverable)
A documented, repeatable procedure: drop canonical + derived data, replay the object-storage raw
records through validate → normalize → persist → feature → engine, **assert byte-identical
outputs** (proves the *recomputable* tier), and **record the wall-clock time** — the first RTO
data point ([doc 12](../architecture/12-deployment-strategy.md) RPO/RTO; [doc 15](../architecture/15-development-roadmap.md) success criterion).

### B7 · Testing plan (the tiers that apply to the skeleton, [doc 11](../architecture/11-testing-strategy.md))
- **Unit — financial correctness** for `one_year_return`: reference value + **property-based**
  (e.g. currency-scale invariance; a flat series → 0 return) + **independent reference
  implementation** with a documented numeric-tolerance policy (money exact, ratio within ε).
- **Contract test** — the yfinance adapter against a **recorded fixture**, proving it satisfies
  `PriceHistoryPort` (hermetic; no live vendor in CI).
- **Data-quality / gate tests** — good data passes; each bad class quarantines; `^NSEI` is
  rejected if FX-converted; nothing silently mutates; authority stamped.
- **Integration + as-of** — end-to-end on fixture data; assert no value carries a
  `knowledge_time` in the future of the query (lookahead-free by construction).
- **Lineage-resolution test** — the metric resolves fully to raw + reference + formula version.
- **Determinism test** — same inputs + versions ⇒ identical output.
- **CI guardrail tests** — the three lints actually fail on a planted violation.
> Golden-master is **not** seeded until the reference implementation + property tests pass
> (governed provenance, [doc 11](../architecture/11-testing-strategy.md) — a golden must not enshrine a first-write bug).

### B8 · Definition of Done — Phase 0.5 (maps 1:1 to doc 15 success criteria)
- [ ] **Every layer L0–L7, L9, L10 exists and is exercised once** for the 5 instruments / 1 metric.
- [ ] **Lineage resolves end-to-end** for the metric (B5), tested.
- [ ] **The recompute-from-raw timing number exists** (B6).
- [ ] **The strangler is proven**: the real endpoint renders live in the existing site **next to
      snapshot JSON, without breaking it**.
- [ ] `knowledge_time` populated on every observation (C1); money is decimal end-to-end (ADR-0016);
      no vendor name above L1; no cross-module table access — all green in CI.
- [ ] No breadth was built (the fence held).

---

## Work breakdown / sequencing
| Milestone | Content | Gate to next |
|-----------|---------|--------------|
| **M0 · Decisions** | Record ED-001…ED-006 in the Engineering Decision Log ([doc 01](01-engineering-decisions.md)) + config files | EDs recorded |
| **M1 · Guardrails (Phase 0)** | Repo skeleton, module map, 3 CI lints, test runner, catalog/log conventions | Phase 0 DoD (A5) |
| **M2 · Provider slice (L1)** | `PriceHistoryPort` + yfinance adapter + provisional symbology (5 instruments) + versioned raw contract + drift detection; hermetic contract tests | adapter satisfies the port; vendor isolated; contract tests green on a fixture |
| **M2b · Raw store (L2)** | `RawStore` port + `FilesystemObjectStore` reference backend + deterministic S3-mapping key layout + raw capture | verbatim payloads captured append-only and immutably; capture idempotent |
| **M2c · Gate + normalization (L3–L4)** | validation gate + quarantine + authority stamping; normalization to `PriceObservation` (C1 `knowledge_time`, decimal `Quantity`, index-not-FX rule, pinned reference version) | bad data quarantines; canonical observations produced |
| **M2d · Domain store (L5)** | Postgres `market_data` schema + repository; persist observations with lineage handles | 5 instruments persist with lineage |
| **M3 · Compute slice (L6–L7)** | return feature (C3 seam) + `one_year_return` engine → `AnalyticResult`; unit/property/reference tests | metric reproducible + traced |
| **M4 · Serve slice (L9–L10)** | one OpenAPI endpoint (DTO + lineage + freshness); frontend renders it beside snapshot JSON | strangler proven live |
| **M5 · DAG + recompute (L-orchestration)** | minimal forward-only DAG; recompute-from-raw procedure + RTO timing | Phase 0.5 DoD (B8) |

Sequencing honors the layered invariant: no layer is built before the one beneath it exists and
is tested (bottom-up, [ADR-0002](../architecture/18-architecture-decision-records.md#adr-0002--strictly-layered-architecture-with-an-enforced-dependency-direction)/[0020](../architecture/18-architecture-decision-records.md#adr-0020--walking-skeleton-first-strangle-the-prototype)).

## Risks specific to the skeleton
| Risk | Mitigation |
|------|-----------|
| Scope creep ("just add a few more tickers/metrics") | The B8 fence + CI; breadth is Phase 1+. |
| Provisional domain model hardens into debt | Phase 1 explicitly re-hardens the model over the skeleton ([doc 15](../architecture/15-development-roadmap.md)); the skeleton's model is labeled provisional. |
| The one throwaway endpoint outliving its purpose | Re-cut on the hardened model in Phase 1 ([ADR-0020](../architecture/18-architecture-decision-records.md#adr-0020--walking-skeleton-first-strangle-the-prototype)); tracked as debt. |
| Decimal↔float mistakes at the seam | Single declared seam at L6 (C3); property test for currency-scale invariance. |
| Reusing prototype math verbatim (untraced) | The prototype's return math is *ported behind* the engine contract, not lifted ([ADR-0014](../architecture/18-architecture-decision-records.md#adr-0014--analytics-as-uniform-versioned-traced-engines)). |

## Explicit non-goals recap
No AI, no second provider/router, no invalidation/reprocessing, no entitlement tiers, no
breadth, no as-of query machinery, no extra stores. The skeleton's *only* job is to prove the
bones connect and to produce the recompute-RTO number.

## Decision log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-07-17 | Walking Skeleton plan authored against frozen Architecture v2.0; scope fixed at 5 instruments / 1 provider / 1 metric / 1 endpoint. | Enter implementation without deviating from or silently amending the frozen architecture. |
| 2026-07-17 | **Revised M0 and the prerequisite section:** the six technology selections are classified as **Engineering Decisions (ED-001…ED-006, [doc 01](01-engineering-decisions.md)), not ADRs.** | They realize already-approved architectural decisions (ADR-0008/0009/0012/0014/0016, docs 12/16) without changing them; per the doc-18 threshold they are implementation decisions. Keeps the ADR registry concise. |
| 2026-07-17 | **Split the ingest slice** into **M2 (Provider slice, L1)** and **M2b (Persistence slice, L2–L5)**. | Adopted minimalism principle (smallest coherent implementation; smallest reviewable commits). L1 delivers real, hermetically-testable value with no infrastructure; the stores (Postgres/object storage, ED-003/004) are stood up where they are first exercised — deferring them until necessary. Architecture scope unchanged. |
| 2026-07-17 | **Split the persistence slice further** into **M2b (Raw store, L2)**, **M2c (Gate + normalization, L3–L4)** and **M2d (Domain store, L5)**; M2b delivered with a filesystem `RawStore` backend per revised [ED-004](01-engineering-decisions.md#ed-004--object-storage-realization). | Same principle. Each is independently reviewable and testable; Postgres (ED-003) is now deferred to M2d, the milestone that first needs it. ADR-0008/0009 unchanged. |
| 2026-07-17 | **L4 preserves native currency; no FX conversion in the skeleton.** Equities normalize to `Money(currency)`, indices to unitless `IndexLevel`. Supersedes this plan's earlier "USD→INR applied to AAPL" wording. | Doc 04 states currency is *tagged*, that `FXRate` is the **only** sanctioned source of conversion factors, and that index-as-points must make FX conversion **type-impossible** — which separate types now enforce. FX is not an ingested data class until a later phase, and the skeleton's metric (1Y return) is a **ratio**, hence FX-invariant. Converting without a real rate source would invent data. Architecture unchanged; this removes an implementation-plan overreach. |
| 2026-07-18 | **The `AnalyticResult` envelope lives in `backend/domain/model/`, not `backend/platform/`** as §A1 proposed. | [Doc 04](../architecture/04-canonical-domain-model.md) owns the envelope as a *canonical entity* (the v2.0 co-ownership resolution), and M2c already set this precedent by placing the `Quantity` types in `domain/model/` rather than the kernel. Keeping doc 04's entities in one package is the point; splitting them across two would be the deviation. The layer lints already permit both L6 and L7 to import `backend.domain.model`. Architecture unchanged — this corrects a plan-level placement, not a boundary. |
| 2026-07-18 | **M3's feature consumes `PriceObservation.close` as the adjusted close**, rather than adding a distinct `adjusted_close` field to the canonical model first. | The provider is fetched with `auto_adjust=True`, so the ingested `close` *is* split- and dividend-adjusted; the values are correct today. The model does not yet make that explicit, which is real modelling debt: a provider change or `auto_adjust=False` would silently change the field's meaning. Adding the field is L1–L5 rework across four layers, well outside M3's fence, and belongs to Phase 1 model-hardening alongside `CorporateAction`. Recorded instead as an explicit **assumption and limitation** in the [methodology catalog](02-methodology-catalog.md), so the honest boundary of the metric ships with it. |
| 2026-07-18 | **The 1Y-return anchor tolerance is 7 calendar days, tightened from the prototype's effective 45.** | Porting behind the engine contract ([ADR-0014](../architecture/18-architecture-decision-records.md#adr-0014--analytics-as-uniform-versioned-traced-engines)) means porting the *shape*, not the parameters. A 45-day error on the anchor date measures a materially different window while still calling itself a one-year return; 7 days spans the longest ordinary exchange closure in scope and suits weekly bars. Availability lost to the tighter rule surfaces as an explicit `Unavailable` reason rather than a quietly wrong number. |
| 2026-07-22 | **M5's DAG is a stdlib task graph; ED-005 (Dagster) stays `Proposed`.** | Doc 16 owns the orchestration *model* and states the product is a doc 12 selection, banning ad-hoc cron only *above* the walking skeleton. The model's requirements are met without a framework: declared task order, tasks keyed by (type, scope, window, config version), idempotent by construction, runs recorded as lineage events. Recorded as [ED-015](01-engineering-decisions.md#ed-015--skeleton-orchestration--stdlib-dag-orchestrator-product-deferred), which enumerates the capabilities that will force the product. |
| 2026-07-22 | **`knowledge_time` is populated from the raw envelope's `fetch.fetched_at`, not from the clock at normalization.** | The platform learned a bar when it fetched it, and that instant is immutable in the raw store. Reading the clock instead would restamp every rebuild, making the §B6 byte-identical recompute impossible by construction. C1 requires the field be populated, not where it comes from — a plan-level correction, not an architectural change. |
| 2026-07-22 | **`computed_at` is treated as a replay input; the recompute compares the full envelope.** | Comparing everything *except* the timestamps would still pass if a rebuild silently used a different observation set. Pinning `computed_at` from the recorded run is what [ADR-0017](../architecture/18-architecture-decision-records.md#adr-0017--first-class-lineage-with-three-guarantee-tiers)'s *bit-reproducible* tier actually claims. |
