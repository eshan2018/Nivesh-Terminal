# Project Context — Nivesh Terminal

**Hand-off brief for any new session. Read this first, then the linked docs.**
Last updated: 2026-07-18 · `main` @ `bcd020f`

---

## 1 · Current progress

```
Current milestone      M2d COMPLETE
Next milestone         M3 — Feature Engine + AnalyticResult + One Year Return
Current branch         main
Latest merge           PR #3  (7 commits)
Checkpoint tag         v0.1-walking-skeleton  → bcd020f
Tests                  125 passing
Runtime dependencies   0
```

**Completed**

```
✓ Architecture v2.0        frozen, approved, merged (PR #2)
✓ M1   Guardrails          layer packages + 3 CI architecture lints
✓ M2   Provider    (L1)    PriceHistoryPort + yfinance adapter
✓ M2b  Raw store   (L2)    RawStore port + FilesystemObjectStore
✓ M2c  Validation  (L3-L4) fail-closed gate + normalization
✓ M2d  Repository  (L5)    MarketDataRepository + SQLite backend
```

**Remaining**

```
□ M3   Compute     (L6-L7) feature + one_year_return engine → AnalyticResult
□ M4   Serve       (L9-L10) REST API + frontend strangler cutover
□ M5   Orchestration        DAG + recompute-from-raw RTO measurement
```

> ⚠️ **The Walking Skeleton is NOT finished** — 5/10 layers, 6/9 milestones. The tag
> `v0.1-walking-skeleton` marks the **ingest half** (L1–L5). Phase 0.5's Definition of Done is
> still unmet: the recompute-RTO number does not exist (M5) and the strangler is not proven live
> (M4). Do not read the tag name as completion.

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
        L10  Frontend             ⬜  (prototype live on snapshot JSON)
              │
        L9   REST API             ⬜  M4
              │
        L8   AI Layer             ⬜  Phase 7
              │
        L7   Analytics Engines    ⬜  M3
              │
        L6   Feature Engineering  ⬜  M3
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
API framework       FastAPI + Pydantic (chosen, not yet built)
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

## 6 · Governance rules — binding

1. **Never redesign the architecture.** `docs/architecture/` is frozen and authoritative.
2. **Never modify architecture documents** unless explicitly asked for an ADR.
3. **Genuine architectural conflict → STOP.** Explain, recommend an ADR, wait for approval.
   Do not improvise around it.
4. **Do not make architectural assumptions.** When a decision is genuinely the user's, present
   2–3 options with trade-offs plus a recommendation, then wait.
5. **Architectural change → ADR** (`docs/architecture/18-…`; next id **ADR-0021**, unused).
   **Implementation choice → Engineering Decision** (`docs/implementation/01-…`; next id **ED-010**).
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
    01-engineering-decisions.md    ED-001…ED-009
    02-methodology-catalog.md      formula home — EMPTY, first entry in M3
    03-walking-skeleton-status.md  status snapshot (regenerate, don't hand-edit)

backend/                      the layered app (42 modules, 125 tests)
  platform/                   kernel: InstrumentId
  providers/ports/            PriceHistoryPort, error taxonomy
  providers/yfinance/         the ONLY place vendor code may appear
  ingestion/                  raw_store, filesystem_object_store, raw_capture,
                              validation (L3), normalization (L4)
  domain/model/               quantities (Money/IndexLevel), instruments, observations
  domain/market_data/         schema, repository port, sqlite_repository
  features/ analytics/ api/ orchestration/    ← EMPTY, awaiting M3/M4/M5

tools/ci/                     the three architecture guardrails + tests
tools/skeleton_status.py      live status board (`make skeleton`)
deploy/ci.workflow.yml        CI — NOT YET ACTIVE (see §10)

home.py, pages/, shared/, tickers/, web/    ← OLD PROTOTYPE, still live. Do not extend.
```

---

## 9 · How to run

```bash
python3.12 -m venv .venv && source .venv/bin/activate
make install     # pip install -e ".[dev]"
make check       # guardrails + ruff + pytest  ← the gate, before every commit
make skeleton    # live status board + real end-to-end trace
```

---

## 10 · Open items

1. **CI is dormant.** `deploy/ci.workflow.yml` needs one manual step — add it via the GitHub UI
   at `.github/workflows/ci.yml`, or grant the PAT `workflow` scope and `git mv` it. It lives in
   `deploy/` because the token lacks `workflow` scope (same convention as
   `deploy/snapshots.workflow.yml`, see `MIGRATION.md`). **Until then the guardrails only run
   when someone runs `make check` locally.**
2. **Tag name caveat** — `v0.1-walking-skeleton` marks L1–L5 only (see §1 warning).
3. **One interpretation open to a second opinion** — L4 preserves native currency and does not
   FX-convert (recorded in the plan's decision log). Changing it is a plan change, not an
   architecture change.

---

## 11 · Next milestone — M3 · Compute slice (L6–L7)

**Objective:** one versioned feature and one traced engine, proving a metric is reproducible and
fully traceable. **Gate to next:** *metric reproducible + traced.*

**Build**
- **L6 feature** — adjusted-close return-series inputs as a **versioned, lineage-carrying**
  feature definition. **The single decimal→float conversion happens here (C3).**
- **L7 engine** — `one_year_return` producing an **`AnalyticResult` envelope**: value, inputs
  referenced, feature + formula + reference-snapshot versions, `as_of`, quality flags, lineage
  handle. Pure and deterministic. **Missing inputs ⇒ `Unavailable` with a reason, never zero.**
  Engines read **features only**, never repositories.
- **Methodology catalog entry** (`docs/implementation/02-…`) for the 1Y-return formula:
  definition, assumptions, **limitations**, `formula_version`.
- **Tests** (doc 11): reference values **plus** property-based tests **plus** an **independent
  reference implementation** with a documented numeric-tolerance policy. A **golden-master may
  only be seeded after** reference-implementation parity and property tests pass — a golden must
  never enshrine a first-write bug.

**Do NOT build in M3:** more metrics or features; scoring; any other engine; the API (M4); the
DAG or recompute timing (M5); AI (Phase 7); as-of query machinery (Phase 6).

**Prior art:** the prototype's math in `shared/calculations.py` is a *reference*, not a source to
copy — it is **ported behind the engine contract**, versioned and lineage-emitting (ADR-0014).

---

## 12 · Conventions

- **Commits** — small, per-milestone; `type(scope): summary`; body explains what and why; footer
  cites the architecture docs, ADRs and EDs satisfied. Gate must be green at each commit.
- **Branching** — work on a branch off `main`; never commit to `main` directly; PR when done.
- **Docs** — architecture docs are frozen; implementation docs are living. Update the plan's
  decision log when a plan-level choice changes. **Update this file at each milestone.**
- **Tests** — hermetic: no network, no services, fixtures, pinned versions, fixed seeds.

```bash
git checkout -b <branch> main    # start M3 here
```
