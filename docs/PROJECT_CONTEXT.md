# Project Context — Nivesh Terminal

**Hand-off brief for any new session. Read this first, then the linked docs.**
Last updated: 2026-07-22 · `main` @ `60adb08`

---

## 1 · Current progress

```
Current milestone      M5 COMPLETE — **Phase 0.5 Definition of Done met**
Next milestone         Phase 1 (see doc 15) — not started, not planned
Current branch         main
Latest merge           M5 DAG + recompute-from-raw RTO
Checkpoint tags        v0.1-walking-skeleton → bcd020f  (L1–L5, ingest half)
                       v0.2-compute-slice    → 4c0e5d5  (L6–L7, compute half)
Tests                  246 passing
Runtime dependencies   1 direct · 9 transitive  (see §5 — "0 dependencies" ended
                       at M4a; L1–L7 remain stdlib-only)
CI                     ACTIVE — guardrails + ruff + pytest on every push/PR
```

**Completed**

```
✓ Architecture v2.0        frozen, approved, merged (PR #2)
✓ M1   Guardrails          layer packages + 3 CI architecture lints
✓ M2   Provider    (L1)    PriceHistoryPort + yfinance adapter
✓ M2b  Raw store   (L2)    RawStore port + FilesystemObjectStore
✓ M2c  Validation  (L3-L4) fail-closed gate + normalization
✓ M2d  Repository  (L5)    MarketDataRepository + SQLite backend
✓ M3   Compute     (L6-L7) close-price-series feature (C3 seam) + one_year_return
                           → AnalyticResult; methodology catalog populated
✓ M4a  Serve       (L9)    one traced endpoint + committed OpenAPI contract artifact
✓ M4b  Strangler   (L10)   live-API pane beside the snapshot JSON; production
                           entry point (`backend/main.py`, the ED-011 composition root)
✓ M5   Orchestration       forward-only ingest DAG (stdlib, ED-015) + recompute-from-raw
                           procedure; **RTO measured: ~0.011 s, byte-identical rebuild**
```

**Remaining**

```
—  Phase 0.5 is complete. Phase 1 (doc 15) re-hardens the domain model and re-cuts the
   throwaway endpoint on it; it is neither started nor planned.
```

> ✅ **The Walking Skeleton is complete — 9/10 layers, 9/9 milestones.** L8 (AI) is Phase 7 and
> was never in skeleton scope, so 9/10 is the finished state, not a shortfall.
>
> **Every item of Phase 0.5's Definition of Done (plan §B8) is met:** every layer exists and is
> exercised; lineage resolves end-to-end; the recompute-from-raw number exists (~0.011 s,
> byte-identical); the strangler is proven live; `knowledge_time`, decimal money, vendor
> isolation and module-owned schemas are all green in CI; and no breadth was built — still
> 5 instruments, 1 provider, 1 metric, 1 endpoint.
>
> **What that does not mean.** This is a skeleton, not a product: one metric, five hand-listed
> instruments, a provisional domain model, a disposable endpoint that ADR-0020 re-cuts in
> Phase 1, and an RTO measured on a local baseline that must be re-measured against real
> infrastructure. The bones connect. That was the whole objective.

---

## 2 · North star

Nivesh Terminal aims to become an **institutional-grade wealth intelligence platform for Indian
retail investors**, built with production engineering discipline. Every implementation decision
optimizes for **long-term maintainability, correctness, and extensibility** rather than rapid
prototyping. Its differentiator is **explainability + lineage**: every number traces to its
source data and the formula that produced it.

It is explicitly **not** a stock screener, **not** an AI chatbot, **not** a scoring engine —
those are modules on a shared foundation, never the core.

---

## 3 · Things the assistant must never forget

```
1.  Architecture is FROZEN.
2.  Architecture is AUTHORITATIVE — if code and docs disagree, the docs win.
3.  The old prototype still exists and is still live (home.py, shared/, web/).
4.  backend/ is the future. Never add features to the prototype.
5.  Never redesign the architecture.
6.  Never bypass the ADR process for architectural change.
7.  Never introduce dependencies without justification.
8.  Never sacrifice hermetic tests (no network, no services, fixed seeds).
9.  Never continue automatically to the next milestone.
10. Always stop after milestone completion and report.
11. On a genuine architectural conflict: STOP, explain, recommend an ADR, wait.
12. Smallest coherent implementation — build only what THIS milestone requires.
```

---

## 4 · Architecture snapshot

Data flows **down**; dependencies point only **up**. Nothing skips a layer.

```
        L10  Frontend             ✅  live-API pane beside the snapshot JSON (M4b)
              │
        L9   REST API             ✅  one endpoint + OpenAPI artifact (M4a)
              │
        L8   AI Layer             ⬜  Phase 7
              │
        L7   Analytics Engines    ✅  one_year_return → AnalyticResult
              │
        L6   Feature Engineering  ✅  close_price_series (the C3 seam)
              │
        L5   Domain Store         ✅  MarketDataRepository + SQLite
              │
        L4   Normalization        ✅  → PriceObservation (Decimal, knowledge_time)
              │
        L3   Validation Gate      ✅  fail-closed, quarantine
              │
        L2   Raw Store            ✅  immutable, content-addressed
              │
        L1   Provider Adapters    ✅  PriceHistoryPort + yfinance
              │
        L0   Provider (yfinance)      external
```

Run `make skeleton` for the live version — it probes the code and executes the real pipeline,
so it can never be stale.

---

## 5 · Key implementation decisions

Recorded so they aren't rediscovered. Full reasoning in `docs/implementation/01-engineering-decisions.md`.

```
                    Development / CI        Production
Raw store           Filesystem              S3-compatible object storage
Domain store        SQLite (stdlib)         PostgreSQL
Language            Python 3.12             Python 3.12
API framework       FastAPI + Pydantic (built, M4a)
ASGI server         uvicorn (optional `serve` extra — the package ships an app,
                    not a server)
Orchestrator        Dagster (proposed, not yet built)

Reason:  the minimalism principle. The PORT is the architectural requirement;
         the backend is an Engineering Decision. Production choices are
         unchanged (ADR-0008 Postgres, ADR-0009 object storage) and remain
         drop-in replacements behind the same interface.

Accepted cost: the S3 and Postgres code paths are unexercised until deploy,
         and the Phase-0.5 recompute-RTO will be a local filesystem baseline
         that must be re-measured against real object storage.
```

---

### Runtime dependencies — precisely

The "zero runtime dependencies" position held through M3 and **ended at M4a**, when L9 needed a
web framework. Stated exactly, so the claim stays checkable:

```
Direct (declared in pyproject `[project] dependencies`)      1
  fastapi

Transitive (installed because fastapi requires them)         9
  annotated-types · anyio · exceptiongroup · idna · pydantic
  pydantic-core · starlette · typing-extensions · typing-inspection

Optional extra `serve` (not installed by default)            1 direct · 4 transitive
  uvicorn → click · colorama · h11 · typing-extensions

Dev-only (`[dev]`, never shipped)
  hypothesis · httpx · pytest · pytest-cov · ruff
```

**Layers L1–L7 remain stdlib-only.** The dependency lives entirely at L9: nothing in ingestion,
the domain, features, or analytics imports a third-party package, so the compute core stays
portable and the framework stays swappable behind ADR-0012's REST contract. The ASGI *server* is
an optional extra rather than a dependency because the package ships an application, and which
server runs it is a deployment choice (ED-002).

---

## 6 · Governance rules — binding

1. **Never redesign the architecture.** `docs/architecture/` is frozen and authoritative.
2. **Never modify architecture documents** unless explicitly asked for an ADR.
3. **Genuine architectural conflict → STOP.** Explain, recommend an ADR, wait for approval.
   Do not improvise around it.
4. **Do not make architectural assumptions.** When a decision is genuinely the user's, present
   2–3 options with trade-offs plus a recommendation, then wait.
5. **Architectural change → ADR** (`docs/architecture/18-…`; next id **ADR-0021**, unused).
   **Implementation choice → Engineering Decision** (`docs/implementation/01-…`; next id **ED-011**).
   *Threshold:* does it change architecture, boundaries, public contracts, maintainability or
   deployment model, or require a **migration** if reversed? If not, it is an ED.

### The minimalism principle

Built by a **solo founder** (1–3 engineers foreseeable). For every new file, package,
abstraction, document, tool or dependency:

> *"Is this required to complete the current milestone according to Architecture v2.0?"*

If no — **do not build it; defer it to the milestone where it becomes necessary.** Optimize for
the smallest coherent implementation, fewest artifacts, smallest reviewable commits, incremental
delivery, production quality. **Do not** optimize for hypothetical scale. Architecture quality
stays fixed; implementation complexity stays minimal.

### Per-milestone process

- Read **only** the architecture docs relevant to that milestone.
- Implement **only** that milestone; keep the repo buildable; production-quality code.
- Comprehensive unit tests; integration tests where required.
- Run the full gate. **Stop.**
- Report: (1) summary (2) architecture docs followed (3) ADRs referenced (4) EDs referenced
  (5) files created/modified (6) tests written (7) test results (8) remaining risks
  (9) recommended commit message (10) suggested next milestone.

---

## 7 · Constraints that bite in code

The first three are enforced by CI; a violation fails the build.

- **Layer dependency direction** — a module may import only the kernel (`backend.platform`), its
  own subpackages, and the layers allowed in `tools/ci/architecture_map.py`.
- **No vendor name above L1** — `yfinance` may appear only under `backend/providers/yfinance/`.
- **Module-owned schemas** — a domain module must not read another module's tables.
- **Money is `Decimal`, never float** (ADR-0016) — `Money` raises `TypeError` on a float.
- **Index levels are unitless points with no currency field** — FX-converting an index is
  *type-impossible* (`IndexLevel`). Never give it a currency.
- **`knowledge_time` populated on every observation** (C1), passed as an **explicit input** —
  never an ambient clock (time is an input, principle 11).
- **The single decimal→float seam is feature-layer ingress (L6)** — C3. **This is exactly what
  M3 touches.** Money is decimal at rest, in the domain and at the API; converting statistical
  floats back into money is forbidden.
- **Fail-closed** — bad data quarantines with reasons, never reaches the canonical model, and is
  retained not discarded. Missing input ⇒ `Unavailable`, never zero.
- **Features are the only layer with repository access.** Engines consume features and other
  engines' results — never repositories.
- **No FX conversion** — native currency preserved; `FXRate` is the only sanctioned conversion
  source and is a later data class.
- **Determinism** — same inputs + versions ⇒ identical output; randomness takes an explicit seed.

---

## 8 · Where things live

```
docs/
  PROJECT_CONTEXT.md          ← this file
  architecture/               FROZEN v2.0 — 21 files
    README.md                 index, governance, decision log
    01–17                     vision → entitlements (the specification)
    18-…decision-records.md   ADR-0001…0020
    19-…readiness-checklist.md
    REVIEW-…                  the adversarial reviews that produced v2.0
  implementation/             living, implementation tier
    00-walking-skeleton-plan.md    milestone plan + decision log
    01-engineering-decisions.md    ED-001…ED-010
    02-methodology-catalog.md      formula home — close_price_series v1,
                                   one-year-total-return v1 (+ golden seeding record)
    03-walking-skeleton-status.md  status snapshot (regenerate, don't hand-edit)
    04-recompute-rto.md            the recompute procedure + the measured RTO number

backend/                      the layered app (45 modules, 173 tests)
  platform/                   kernel: InstrumentId
  providers/ports/            PriceHistoryPort, error taxonomy
  providers/yfinance/         the ONLY place vendor code may appear
  ingestion/                  raw_store, filesystem_object_store, raw_capture,
                              validation (L3), normalization (L4)
  domain/model/               quantities (Money/IndexLevel), instruments, observations
  domain/market_data/         schema, repository port, sqlite_repository
  features/                   L6: returns.py — close_price_series, the C3 seam
  analytics/                  L7: one_year_return.py → AnalyticResult
  api/ orchestration/         ← EMPTY, awaiting M4/M5

tools/ci/                     the three architecture guardrails + tests
tools/skeleton_status.py      live status board (`make skeleton`)
.github/workflows/ci.yml      CI — active: guardrails + ruff + pytest on every push/PR

home.py, pages/, shared/, tickers/          ← OLD PROTOTYPE, still live. Do not extend.
web/                        Next.js frontend — being strangled, not rewritten:
                            app/api/metrics/…/route.ts is the one seam to the backend.
```

---

## 9 · How to run

```bash
python3.12 -m venv .venv && source .venv/bin/activate
make install     # pip install -e ".[dev]"
make check       # guardrails + ruff + pytest  ← the gate, before every commit
make skeleton    # live status board + real end-to-end trace
make recompute   # rebuild every derived value from raw and time it (doc 00 §B6)
make serve       # run the API locally (needs the `serve` extra)
```

---

## 10 · Open items

1. **Frontend test infrastructure — deferred to Phase 1 (deliberate, not an oversight).**
   The L10 strangler pane has **no automated test**. Its behaviour was verified by running both
   halves together and killing the API mid-session (see §1), but nothing guards it in CI. Doc 11
   defines the test tiers for the backend and is silent on frontend unit testing, so this is a
   gap in coverage, not a violation.
   *Why deferred:* a frontend test runner (Vitest/RTL, or Playwright for the end-to-end path) is
   a new dependency set and a second CI job, for one pane that is itself disposable — ADR-0020
   re-cuts this endpoint and its consumer on the hardened model in Phase 1. Building the harness
   now would test code scheduled for replacement.
   *What to do in Phase 1:* choose the runner as an ED, and cover at minimum the three states the
   pane must never get wrong — available, `UNAVAILABLE` (reason shown, never `0.00%`), and
   `UNREACHABLE` (site intact).
   *Risk accepted meanwhile:* a regression in the pane's degraded-state rendering would reach the
   live site undetected by CI.
2. **Tag name caveat** — `v0.1-walking-skeleton` marks L1–L5 only (see §1 warning).
   `v0.2-compute-slice` names its increment rather than the whole, so it carries no such trap.
3. **One interpretation open to a second opinion** — L4 preserves native currency and does not
   FX-convert (recorded in the plan's decision log). Changing it is a plan change, not an
   architecture change.
4. **`source_ref` resolution is O(n)** — a lineage endpoint resolves a handle by scanning raw
   object keys (proven in `backend/tests/api/test_source_ref_resolution.py`). Correct and cheap at
   skeleton scale; needs a stored `ref → key` index before real traffic. The published contract
   does not change when that index lands.

---

## 11 · Pre-M4 design decisions — **RESOLVED**

Two questions the M3 code review raised that M3 could defer and M4 cannot. Both are invisible
until something serializes the `AnalyticResult`; M4 is the first thing that does. Both are
recorded here rather than left in conversation so the next engineer does not have to reconstruct
the reasoning.

**Both options A extend the envelope.** [Doc 04](architecture/04-canonical-domain-model.md) owns
the envelope's shape and [doc 08](architecture/08-analytics-framework.md) may not alter it.
[ADR-0014](architecture/18-architecture-decision-records.md#adr-0014--analytics-as-uniform-versioned-traced-engines)'s
revisit clause pre-authorizes *additive* extension ("If the envelope proves insufficient for a new
analytic class, extend it additively (owned by doc 04, ADR-0004)"). **Classification decided 2026-07-19: Engineering Decision, not ADR** — additive extension spends
ADR-0014's clause; no boundary, contract direction, or migration is involved, and reversal is a
field deletion. Recorded as **ED-012** and **ED-013**. **ADR-0021 remains unused.**

---

### Decision 1 — Lineage granularity in a served result

**Context.** `AnalyticResult.lineage.features[].inputs` currently carries one `ObservationRef`
(instrument id, `event_time`, `knowledge_time`, full `Provenance`) for **every observation the
feature scanned**. A 400-bar series produces 400 of them. The engine reads exactly **two**: the
anchor and the end bar. Serializing that into a DTO makes a single-metric response several
kilobytes of lineage the caller cannot use, and materializing results (doc 07) multiplies it.

**Option A — distinguish contributing inputs from scanned inputs (recommended).**
The engine names the observations that actually determined the value; the response carries those
plus a scanned count plus the de-duplicated raw object keys.
- *For:* response stays proportional to the answer, not the history. The "why?" panel shows the
  two bars that produced the number — which is what a user asking "why?" actually wants.
  Recomputability survives: raw object keys, feature version and feature parameters are all
  still pinned, so the series can be rebuilt and the result re-derived.
- *Against:* requires a small additive envelope field. Shifts the recomputability argument from
  "here is every input" to "here is how to rebuild every input" — weaker on paper, though
  ADR-0017's *recomputable* tier asks for reproducibility, not an inline copy of the inputs.

**Option B — serve the full scanned set.**
- *For:* maximal literal traceability; no envelope change; no new concept.
- *Against:* payload grows without bound as history grows; the differentiator becomes a
  performance problem exactly where users first meet it.

**Option C — lineage by reference (a second endpoint returns the full chain).**
- *For:* smallest response; doc 10 explicitly sanctions it ("expose **or link to** the
  `AnalyticResult` envelope").
- *Against:* a second endpoint, which M4's own fence forbids. **This is the likely Phase-1
  shape** — A is forward-compatible with it.

**Status: APPROVED 2026-07-19 → Option A. Implemented as ED-012.** C remains the Phase-1 successor.

---

### Decision 2 — Anchor-offset representation

**Context.** When the one-year target date has no bar, the engine uses the nearest bar within
7 days and publishes the actual offset as the string `anchor-offset-days:-3` inside
`quality_flags` — a tuple of otherwise-opaque tags (`stale-series`, `reference-version-drift`).
Recovering the number means string-parsing a flag.

**Option A — typed diagnostics field; flags stay opaque tags (recommended).**
- *For:* `quality_flags` keeps one meaning (a set of tags you test membership in). The offset
  becomes a typed JSON number. Any consumer treating flags as opaque — the correct reading —
  stops silently dropping the information.
- *Against:* additive envelope field (see classification note above).

**Option B — keep it in the flag string; the DTO parses it out.**
- *For:* no envelope change.
- *Against:* puts parsing logic at the API edge, which doc 10 forbids ("the API is a thin,
  validated projection"). Every future consumer reimplements the same split.

**Option C — drop the offset from the response.**
- *For:* simplest.
- *Against:* the caller can no longer tell a 365-day window from a 368-day one. The methodology
  catalog lists that approximation as a mandatory limitation; hiding it at the API contradicts
  the entry.

**Status: APPROVED 2026-07-19 → Option A. Implemented as ED-013.**

---

## 12 · Completed milestone — M4 · Serve slice (L9–L10)

**Objective:** one OpenAPI-first endpoint that projects the `AnalyticResult` into a DTO, rendered
live in the existing site beside the snapshot JSON. **Gate to next:** *strangler proven live.*

**Build**
- **L9 API** — one typed, contract-first endpoint:
  `GET /v1/instruments/{id}/metrics/one-year-return`. Returns the metric as a **DTO projection**
  (never the domain object), plus a **lineage reference** and **freshness** (`as_of` /
  `computed_at`). Single public tier — no entitlements. FastAPI + Pydantic (ED-002).
- **L10 Frontend** — the existing Next.js app renders that one endpoint's value, a minimal
  "why?" (lineage), and freshness, **alongside** the current snapshot JSON without breaking it.
  This *is* the strangler proof (ADR-0020).
- **Tests** — contract tests against the OpenAPI spec; the `Unavailable` path must render as
  absence-with-a-reason, not a blank or a zero.

**Carried in from M3 — decide before the DTO is designed:**
1. **Lineage volume.** Every `AnalyticResult` carries an `ObservationRef` for every input
   observation (400 for a 400-bar series) though the metric uses two. Serializing that whole
   block per response is heavy. Options: distinguish contributing from scanned inputs, or use
   doc 08's batch-granularity lineage for bulk runs. Touches the envelope shape → doc 04 owns it.
2. **The anchor offset is encoded in a flag string** (`anchor-offset-days:-3`). A DTO consumer
   must parse a tag to recover a number. A structured field would be cleaner, but again the
   envelope's shape is doc 04's.
3. **`UnknownInstrument`** now raises from the feature layer — the endpoint should map it to 404,
   distinct from a 200 carrying `Unavailable`.

**Do NOT build in M4:** more endpoints or metrics; entitlement tiers; async engine handles; the
DAG or recompute timing (M5); AI (Phase 7); as-of query machinery (Phase 6).

**Note (ADR-0020):** the skeleton is allowed *one* disposable endpoint as its single exception to
"no API before the hardened domain model". It is re-cut on the hardened model in Phase 1 and is
tracked as debt. No other exception is permitted.

## 13 · Conventions

- **Commits** — small, per-milestone; `type(scope): summary`; body explains what and why; footer
  cites the architecture docs, ADRs and EDs satisfied. Gate must be green at each commit.
- **Branching** — work on a branch off `main`; never commit to `main` directly; PR when done.
- **Docs** — architecture docs are frozen; implementation docs are living. Update the plan's
  decision log when a plan-level choice changes. **Update this file at each milestone.**
- **Tests** — hermetic: no network, no services, fixtures, pinned versions, fixed seeds.

```bash
git checkout -b <branch> main    # start M3 here
```
