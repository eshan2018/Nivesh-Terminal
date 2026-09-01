# Project Context — Nivesh Terminal

**Hand-off brief for any new session. Read this first, then the linked docs.**
**This is the single authoritative hand-off document.** There is no separate product-context
file; product intent lives in §2 below.
Last updated: 2026-08-12 · `main` @ M6c · reference state: tag `v0.3-walking-skeleton-complete`

---

## 0 · Freeze notice — Phase 0.5 is closed

**Phase 0.5 (Walking Skeleton) is COMPLETE and FROZEN as of 2026-07-22, tag
`v0.3-walking-skeleton-complete`.**

What "frozen" means here, precisely:

- **The skeleton's scope is closed.** 5 instruments · 1 provider · 1 metric · 1 endpoint.
  That fence held through nine milestones and does not reopen. Breadth is Phase 1+ (doc 15).
- **The tagged commit is the reference state.** Anyone can check it out, run `make check`
  and `make recompute`, and reproduce every claim in this document.
- **Architecture v2.0 remains frozen and authoritative.** This was always true (§3, §6) and
  is restated here because the next phase is where the pressure to bend it appears: Phase 1
  re-hardens the domain model, and "we already have the code" is not an argument that
  outranks the blueprint.

**Any architectural change requires an ADR** — a change to a layer boundary, a published
contract, the dependency direction, the deployment model, or anything that would need a
migration to reverse. Next id: **ADR-0021, still unused.** Nine milestones were delivered
without spending one; that is evidence the architecture was sufficient, and the bar for the
first one should stay high.

**Implementation choices remain Engineering Decisions** (next id: **ED-022**) and do not
need an ADR. The distinction and its litmus are in
[doc 01](implementation/01-engineering-decisions.md); when in doubt, classify before writing
code, not after.

> One caution for whoever picks this up: the skeleton contains deliberate, documented debt —
> a provisional domain model, a disposable endpoint ([ADR-0020](architecture/18-architecture-decision-records.md#adr-0020--walking-skeleton-first-strangle-the-prototype)), vendor-inherited price
> adjustment, an O(n) lineage lookup, and an RTO measured on a laptop. None of it is a
> surprise; all of it is recorded in §10 and in the implementation docs. Phase 1 should read
> that list before adding anything new.

## 1 · Current progress

```
Phase                  **Phase 1 IN PROGRESS** — Portfolio Intelligence
                       (Phase 0.5 remains COMPLETE and FROZEN — see §0)
Last milestone         M6c — first deterministic judgement, served and rendered
Next milestone         none approved — M7 CLOSED with no product surface (gate G4 failed)
Current branch         main
Reference state        tag `v0.3-walking-skeleton-complete` (see §0)
Checkpoint tags        v0.1-walking-skeleton        (L1–L5, ingest half)
                       v0.2-compute-slice           (L6–L7, compute half)
                       v0.3-walking-skeleton-complete (Phase 0.5 closed)
Tests                  422 passing
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
Phase 1 · Portfolio Intelligence (stateless — no accounts, no persistence)
✓ M6a  Engine       return-series + aligned-matrix features; portfolio risk & return
✓ M6b-0 Provider     live path validated; 400-bar real payload recorded as a fixture;
                     findings in docs/implementation/05-provider-observations.md
✓ M6b-1 Universe     20 securities seeded as DATA (ED-018) with MIC/ISIN/aliases (ED-017);
                     identity verified against the live provider — report in
                     docs/implementation/06-universe-verification.md
✓ M6b-2 Ingestion    20 instruments ingested live (4,976 observations, 6.7s); batch
                     execution outcomes (ED-019); evidence in
                     docs/implementation/07-ingestion-at-scale.md.
                     Two live-only defects found and fixed — see §10 item 6
✓ M6c  Judgement    POST /v1/portfolio/analysis + the portfolio pane. The platform's
                     FIRST deterministic judgement: portfolio realized volatility vs the
                     Nifty 50 (`portfolio-volatility-vs-reference/v1`, ED-021), answer-first
                     in the UI. The compensation judgement was dropped on empirical
                     evidence — 99.8% inconclusive over 411 real portfolios — see the
                     methodology catalog.
✗ M7   Co-movement    CLOSED 2026-08-30 with NO product surface. The gating study passed
                     G1/G2/G3 but failed G4: the only viable reference frame was the
                     platform's own coverage list, which moves ~30% under reasonable
                     redefinition. Direction robust (0% reversals), decisiveness not.
                     Efficient frontier dropped separately — needs expected returns,
                     unestimable here per M6c, and its output is advice (doc 14).
                     Evidence: docs/implementation/08-m7-gating-study.json
                     Harness:  tools/diversification_study.py (make diversification-study)
                     N_eff retained as a RESEARCH FINDING only — not a product judgement.
```

> ✅ **Phase 0.5 (Walking Skeleton) is COMPLETE** — all 9 of its milestones, 9 of 10 layers.
> L8 (AI) is Phase 7 and was never in skeleton scope, so 9/10 is the finished state for this
> phase, not a shortfall.
>
> **This is one phase of doc 15's roadmap, not the project.** Phases 1–8 — model hardening,
> breadth, invalidation, entitlements, multi-provider, backtesting, AI, commercialization —
> are all ahead. "Complete" here means the skeleton's scope is met.
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

## 2 · North star & product principles

Nivesh Terminal aims to become an **institutional-grade wealth intelligence platform for Indian
retail investors**, built with production engineering discipline. Every implementation decision
optimizes for **long-term maintainability, correctness, and extensibility** rather than rapid
prototyping. Its differentiator is **explainability + lineage**: every number traces to its
source data and the formula that produced it.

It is explicitly **not** a stock screener, **not** an AI chatbot, **not** a scoring engine —
those are modules on a shared foundation, never the core.

### Product principles (binding, from 2026-07-22)

1. **Indian retail investors first.** Every decision resolves toward that user.
2. **The Bloomberg Terminal for retail investors** — not by copying Bloomberg, but by making
   institutional-grade financial intelligence understandable and accessible.
3. **Every feature answers a real investor question or improves an investment decision.**
   Infrastructure exists only to enable user-facing value, never as an objective in itself.
   A feature that answers none of these should be challenged, not built:
   *What do I own? · How healthy is my portfolio? · Why did this happen? · What risks am I
   taking? · What should I do next? · Can I trust this number?*
4. **Ship complete vertical slices over completing roadmap phases in order.** Product value
   takes precedence over roadmap sequence — **provided Architecture v2.0, the ADRs and every
   engineering boundary remain intact.** See the sequencing note below.
5. **Stateless before accounts.** Authentication, saved portfolios and workspaces stay
   deferred until they create clear product value.
6. **When product direction is uncertain, ask** — do not assume.

### The Intelligence lens (binding, 2026-07-22)

Nivesh Terminal is an **intelligence platform, not an analytics platform**. A feature is
measured not by how many metrics it exposes but by how much better an investor understands
their position after using it. **Phase 1's success criterion is a feeling:** *"I understand
my portfolio better than I did five minutes ago."*

- **Every feature begins from an investor question**, not a formula. A capability that
  answers none is challenged before it is built. Metrics support decisions; they are not
  the product.
- **Engines compute; the product explains.** Keep the technical metrics (volatility,
  Sharpe, correlation, drawdown) — **never remove them** — and layer investor-facing
  interpretation *above* them (Risk Level, Portfolio Health, Diversification Quality,
  Things Requiring Attention). Interpretation is deterministic, testable and
  lineage-preserving like any other engine output.
- **Explain before recommending.** For every result: *why · what contributed · what was
  assumed · how confident · what to watch.*
- **Think in capabilities, not indicators.** New ideas (promoter pledging, USD
  appreciation, G-Secs, sector concentration, core-satellite investing…) attach to an
  Intelligence capability — Portfolio · Risk · Ownership · Currency · Macro · Sector · Debt
  · Opportunity · AI Research — and evolve across milestones rather than landing as
  isolated features.
- **When a metric and understanding trade off, choose understanding.**

**Milestone proposals now open with an "Investor Value" section:** (1) the investor
question answered; (2) why it matters to an Indian retail investor; (3) the actionable
understanding gained; (4) why it is the highest-leverage next step.

This is a planning lens only. Architecture v2.0, ADR/ED governance, layering, contracts,
determinism, lineage, testing and CI are unchanged and mandatory.

### The intelligence pipeline (settled, 2026-07-24)

Never reason as *metric → interpretation*. Reason in six stages:

```
Investor Question → Evidence → Deterministic Reasoning → Deterministic Judgement
                  → Narrative & Conversation → Lineage
```

- **Evidence** is objective financial fact — the metric engines (L7). `portfolio-risk-return/v1`
  is the first of these: it produces traced, confidence-bearing numbers and interprets nothing.
- **Deterministic judgement** is a distinct stage: investor-meaningful verdicts ("underperformed
  the risk-free benchmark", "high concentration") built entirely from **transparent rules with
  complete lineage and exact tests**. Deterministic, testable, traceable — not AI.
- **Narrative** is where L8/AI belongs, and only there.

**The rule that protects the product's identity: AI never authors a judgement — it explains one.**
Truth comes from computation, rules and evidence; language comes from the layer above. A platform
whose numbers are produced by a probabilistic model cannot make the verifiability claim this
product is built on.

**Where the judgement layer lives is deliberately undecided.** It is *not* forced into L7 or L8
ahead of need; the placement will be settled when the first judgement capability is actually
built. Recorded so a future reader knows the omission is a decision, not an oversight.

### Sequencing note — doc 15 is a planning document

**[Doc 15](architecture/15-development-roadmap.md) is treated as an implementation roadmap,
not an architectural contract** (ruling, 2026-07-22). Delivery is reprioritized for user
value; its phase *numbering* is not binding, and departing from it needs **no ADR**.

What remains binding: every architectural boundary, the layer dependency direction, published
contracts, and the ADR/ED governance. **Architecture is not changed to accelerate delivery.**

This is consistent with how the roadmap has already been treated — Phase 0.5 itself built an
API that doc 15's Phase 1 lists under "do NOT build yet", sanctioned by
[ADR-0020](architecture/18-architecture-decision-records.md#adr-0020--walking-skeleton-first-strangle-the-prototype).
Phase 1 therefore leads with **Portfolio Intelligence** and pulls in only the canonical-model
and universe work that capability actually requires.

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

### The founder–architect operating model (settled, 2026-07-24)

How decisions get made here, recorded because it is easy to lose and expensive to rediscover:

1. **The architect thinks independently and challenges weaker decisions.** Do not optimize for
   agreement. When you disagree: explain why, give the trade-offs, recommend, and keep pressing
   until the trade-offs are genuinely explored. **Do not become a passive executor.**
2. **Once the founder makes a conscious decision after hearing the reasoning, that decision is
   the new constraint** — converge and execute it to the highest standard rather than
   relitigating.
3. **The founder does not override architecture casually**, and explains the product rationale
   when pushing back. The same rigor is expected on the engineering side.
4. **Reasoning order for any feature or milestone:** what investor problem does this solve? ·
   does it strengthen Nivesh Terminal's identity? · does it respect the architecture? · is it
   the simplest implementation that achieves the objective? · does it create unnecessary future
   complexity? This is a *reasoning* order, not a precedence order — **architecture remains a
   hard gate**, overridable only by a conscious ADR.
5. **Every milestone proposal opens with an "Investor Value" section:** the investor question
   answered · why it matters to an Indian retail investor · the actionable understanding gained
   · why it is the highest-leverage next step. Milestone objectives are written from the
   investor's perspective, never the engineering perspective.
6. **Risks are surfaced before implementation, not during it.** Milestones stay independently
   mergeable. Repository history is a record of *knowledge*, not just code.


1. **Never redesign the architecture.** `docs/architecture/` is frozen and authoritative.
2. **Never modify architecture documents** unless explicitly asked for an ADR.
3. **Genuine architectural conflict → STOP.** Explain, recommend an ADR, wait for approval.
   Do not improvise around it.
4. **Do not make architectural assumptions.** When a decision is genuinely the user's, present
   2–3 options with trade-offs plus a recommendation, then wait.
5. **Architectural change → ADR** (`docs/architecture/18-…`; next id **ADR-0021**, unused).
   **Implementation choice → Engineering Decision** (`docs/implementation/01-…`; next id **ED-022**).
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
    05-provider-observations.md    how the live provider actually behaves (M6b-0/M6b-1)
    06-universe-verification.md    identity evidence — regenerate, don't hand-edit
    07-ingestion-at-scale.md       the first real ingestion run (M6b-2)

backend/                      the layered app (422 tests)
  platform/                   kernel: InstrumentId
  providers/ports/            PriceHistoryPort, error taxonomy
  providers/yfinance/         the ONLY place vendor code may appear; symbology.json
  ingestion/                  raw_store, filesystem_object_store, raw_capture,
                              validation (L3), normalization (L4)
  domain/model/               quantities (Money/IndexLevel), instruments + universe.json,
                              observations
  domain/market_data/         schema, repository port, sqlite_repository
  features/                   L6: returns.py — close_price_series, the C3 seam
  analytics/                  L7: one_year_return.py → AnalyticResult
  api/                        L9: app, DTOs, OpenAPI export
  orchestration/              the forward-only ingest DAG + recompute + batch outcomes

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
make verify-universe  # LIVE: re-check seeded identity against the provider
make ingest      # LIVE: ingest the seeded universe (non-zero exit on trouble)
make serve       # run the API locally (needs the `serve` extra)
```

---

## 10 · Open items

1. **Data licensing — a PHASE 2 STRATEGIC DECISION, not an implementation task.**
   The platform's only data source is `yfinance`, an **unofficial scraper of Yahoo Finance**,
   and the raw store keeps vendor payloads permanently. Yahoo's terms restrict commercial
   redistribution. For a free public good this is grey; **for a funded, commercial product it
   is a first-meeting diligence question.**
   *Status:* deliberately **not** solved during M6b — it is a business decision, not an
   engineering one. **Before Phase 2 begins, a dedicated Licensing Strategy discussion** is
   required, covering: commercial viability of the current source, licensed provider options
   and their costs, migration paths, and the risks of each.
   *Why this is not a crisis:* [ADR-0005](architecture/18-architecture-decision-records.md#adr-0005--provider-abstraction-via-portsadapters)'s
   port/adapter boundary means swapping providers is an adapter change, not a re-architecture —
   the whole point of the abstraction. Doc 14 requires per-provider terms be captured as
   enforceable metadata; that work belongs with the strategy, not before it.
   *Risk accepted meanwhile:* a demo or pitch built on scraped data carries a dependency a
   diligent investor will ask about. Know it before the meeting, not during it.
2. **Frontend test infrastructure — deferred to Phase 1 (deliberate, not an oversight).**
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
3. **Tag name caveat** — `v0.1-walking-skeleton` marks L1–L5 only (see §1 warning).
   `v0.2-compute-slice` names its increment rather than the whole, so it carries no such trap.
4. **One interpretation open to a second opinion** — L4 preserves native currency and does not
   FX-convert (recorded in the plan's decision log). Changing it is a plan change, not an
   architecture change.
6. **Two defects existed for months and were only findable live (M6b-2).** The window
   parameter meant bars not days, and the fail-closed gate could not see NaN — a
   still-open session's all-NaN bar passed every comparison-based check and produced an
   `AVAILABLE` metric valued `NaN`. Both are fixed and pinned by tests
   ([doc 05](implementation/05-provider-observations.md) findings 12–13).
   *What to carry forward:* hermetic tests prove behaviour against what we imagined the
   vendor sends. Neither defect was a coverage gap — the gate had tests and they passed.
   A periodic deliberate live run is the only thing that finds this class, which is why
   `make ingest` and `make verify-universe` exist as standing tools rather than one-off
   scripts.
5. **No instrument carries an ISIN yet — deliberate, and the founder's call to close.**
   All 20 seeded rows have `isin: null`. The vendor offers a check-digit-valid ISIN for 9 of
   them, but adopting a value *from* the system being verified would make the check circular,
   and two of the offered values disagree with what those companies are believed to carry
   ([doc 05](implementation/05-provider-observations.md) finding 11). The candidates are listed
   in [doc 06](implementation/06-universe-verification.md).
   *What closes it:* confirm each against CDSL/NSDL or exchange listing data, paste the
   confirmed values into the seed (one field per row — the shape already exists, which is why
   ED-017 added it early), and re-run `make verify-universe`. The run then checks agreement
   rather than reporting a candidate, and the check stops being vacuous.
   *Risk accepted meanwhile:* the join key every Indian demat statement uses is absent, so
   broker-import work would have nothing to match on. Nothing currently depends on it.
6. **`source_ref` resolution is O(n)** — a lineage endpoint resolves a handle by scanning raw
   object keys (proven in `backend/tests/api/test_source_ref_resolution.py`). Correct and cheap at
   skeleton scale; needs a stored `ref → key` index before real traffic. The published contract
   does not change when that index lands.

---

## 11 · M6b-1 — DELIVERED (2026-07-30)

**Built:** the universe is now **data, not code** — `backend/domain/model/universe.json` (20
instruments) and `backend/providers/yfinance/symbology.json`, per **[ED-018](implementation/01-engineering-decisions.md#ed-018--reference-data-as-a-committed-seed-file)**.
`InstrumentReference` carries MIC exchange, optional ISIN and aliases (ED-017); MIC shape and
the **ISIN ISO 6166 check digit** are enforced in the constructor. `REFERENCE_VERSION` moved into
the seed and bumped to `instrument-reference/v2`; both goldens now assert it against the live
constant instead of freezing it, so a seed edit no longer re-blesses a golden — **both engines'
values were byte-identical across the bump**, which is the evidence that no methodology moved.

**Verified:** `python -m tools.verify_universe` (or `make verify-universe`) probed all 20
instruments live — **20 OK, 0 failed** — with the evidence committed to
[doc 06](implementation/06-universe-verification.md). The comparison logic is pure and
hermetically unit-tested; only the probe touches the network; CI never runs it.

**Two things the run taught us, both recorded in [doc 05](implementation/05-provider-observations.md):**
the first verifier read `info["isin"]` instead of `Ticker.isin` and produced a **fully green
report in which the ISIN check asked no question at all** — a green report is not evidence unless
you know which questions were asked. And the `LT.NS` name/ISIN discrepancy **reproduces stably**.
No vendor ISIN was adopted; all 10 valid ones are recorded as *candidates* awaiting an
authoritative source. Seeding them from the vendor would have made the next run verify the vendor
against itself.

The approved design this implemented, kept for reference:

**Investor question:** *"When I add HDFC Bank to my portfolio, am I actually getting HDFC Bank?"*
The failure this prevents is the one nobody notices — a wrong ticker yields a plausible number,
correctly computed and fully traced, that belongs to a different company. India makes this easy:
HDFC Ltd merged into HDFC Bank; Bajaj Finance vs Bajaj Finserv; `.NS`/`.BO` silently switch
exchange. *A number that knows it is wrong we refuse to show. A number that thinks it is right is
what destroys trust.*

**Approved decisions**

| | Decision |
|---|---|
| **A** | Add **exchange to the canonical model as MIC codes** (`XNSE`/`XBOM`). Vendor codes (Yahoo's `NSI`) stay inside the adapter — doc 06. |
| **B** | **Verify only what the vendor can genuinely corroborate.** ETF classification is recorded as *our own canonical knowledge*, not force-fitted to a vendor field. |
| **C** | **~15–20 of the most commonly held Indian retail securities**, including a few representative ETFs. **Breadth is explicitly not the goal** — proving portfolio intelligence against securities investors actually own is. Expansion is incremental once the capability is proven. |
| **D** | **Permanent readable slugs** as opaque internal identifiers (`hdfc-bank`, `infosys`). Never shown as a name; never regenerated on rename or merger. |
| **+** | **ISIN** (optional) and **aliases** carried in the seed — see [ED-017](implementation/01-engineering-decisions.md#ed-017--canonical-instrument-identity--mic-exchange-isin-and-aliases). |

**What verification means here.** Not "data exists" but **"the data belongs to the instrument we
believe it does."** Verify strictly what the vendor can corroborate — currency, exchange, market,
index-vs-not — and record honestly what it cannot. *A verification that always passes verifies
nothing.*

**Design constraint: CI stays hermetic.** Seed data and its consistency tests are offline;
verification is a **deliberate tool** producing a **committed, dated evidence report** — the
pattern M6b-0 established. A network call in CI would forfeit the reproducibility guarantee
everything else rests on (doc 11).

**Not in this milestone:** search machinery of any kind (aliases are *data*, search is
*machinery*), live ingestion at scale (M6b-2), any endpoint or UI (M6c).

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
