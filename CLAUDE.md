# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Quick Start Commands

```bash
# Launch the dashboard (use Python 3.12 explicitly)
/Library/Frameworks/Python.framework/Versions/3.12/bin/streamlit run home.py --server.port 8520

# Install dependencies
pip install -r requirements.txt

# Verify code compiles
python3.12 -m py_compile shared/calculations.py shared/data_loader.py shared/dashboard.py

# Run linting (if configured)
python3.12 -m flake8 shared/ pages/ --max-line-length=120
```

---

## Architecture Overview

### High-Level Flow

```
User Browser
    ↓
home.py (landing page)
    ↓
pages/ (1_india_market.py, 2_us_market.py)
    ↓
shared/dashboard.py (orchestrator: loads data → renders tabs)
    ↓
shared/data_loader.py (fetches market data from yfinance)
    ↓
shared/calculations.py (Sharpe, volatility, portfolio math)
    ↓
shared/tabs/*.py (7 tab modules: overview, builder, search, etc.)
    ↓
shared/theme.py (CSS design system)
```

### Core Modules

#### `shared/data_loader.py` (Data Pipeline)
- **Two-phase data fetching:**
  - Phase 1: Batch yfinance download (all 110 tickers in one HTTP call per period)
  - Phase 2: Market caps via yfinance `fast_info` (parallel, 5 workers)
- **Caching strategy:**
  - Market data: 900s (15 min) — allows UI responsiveness, respects API limits
  - Market caps: 86,400s (24 hr) — rarely changes
  - Live quotes (home page): 300s (5 min) — balances freshness vs. server load
  - FX rates: 300s (5 min) — USD/INR changes frequently
- **Key functions:**
  - `load_market_data(universe, market, usd_inr)` — returns df_daily, df_weekly with Close prices
  - `get_market_caps(tickers, market, usd_inr)` — returns dict of market caps in INR
  - `fetch_asset_history(ticker, market, period, interval, usd_inr)` — single ticker fetch (used by Search tab)
  - `get_live_quotes(pairs, usd_inr)` — home page pulse bar (5 global indices)

**Performance note:** After `load_market_data()` cache miss, India dashboard loads in ~20-30 sec (110 tickers × 2 batch calls). Subsequent loads are instant (cached).

#### `shared/calculations.py` (Financial Math)
All calculations are **annualized** and **statistically robust:**
- **Sharpe ratio:** `mean(weekly_returns) × 52 / annualized_volatility` — uses mean of returns, not 1Y% snapshot
- **Volatility:** `std(weekly_returns) × √52` (long-term) or `std(daily_returns) × √252` (short-term)
- **Portfolio variance:** Full covariance matrix (`w @ Σ @ w`), not naive sum
- **SIP calculator:** Annuity-due formula with CAGR interpolation
- **Max drawdown:** Expanding max vs. peak-to-trough percentage
- **RSI/MACD/Bollinger:** Standard technical definitions with Wilder's EMA smoothing

**Key insight:** All per-asset Sharpe values are computed from `annualised_mean_return()`, ensuring consistency with portfolio Sharpe in the Builder tab.

#### `shared/dashboard.py` (Orchestrator)
- Loads market data once at page start
- Dispatches to 7 tab modules
- Implements SEBI 5-stage risk profiler questionnaire
- Per-tab error isolation with `try/except`
- Applies USD→INR FX conversion for US data

#### `shared/tabs/` (UI Layer)
- **tab_overview.py** — Market pulse bar + sortable ticker table with Sharpe star ratings
- **tab_builder.py** — Percentile-rank recommender + Monte Carlo confidence cone + SIP/lump-sum projector + goal reverse calculator
- **tab_search.py** — Single ticker intelligence card (9 metrics) + radar chart comparison + AI 3-statement analysis
- **tab_heatmap.py** — Treemap/sunburst/calendar heatmap + top 5 gainers/decliners
- **tab_charts.py** — Interactive price history with SMA/EMA/Bollinger + RSI/MACD sub-charts
- **tab_risk.py** — Efficient frontier scatter + Security Market Line + max drawdown panel
- **tab_glossary.py** — Searchable financial terms + interactive Sharpe playground

#### `shared/theme.py` (Design System)
- **11 CSS design tokens:** colors, fonts, spacing, borders
- **4 font families:** Playfair Display (titles), DM Sans (body), JetBrains Mono (code), Inter (UI)
- **20+ component classes:** pulse-bar, metric-band, verdict-card, intelligence-chip, marquee, hero, feature-cards
- **Mobile breakpoint:** 768px (CSS handles stacking; Streamlit auto-responsive)

#### `tickers/` (Asset Universe)
- `india_universe.json` — 110 assets (editable without code changes)
- `us_universe.json` — 110 assets
- Each entry: `{ticker, label, sector, mcap_proxy}`

---

## Common Development Scenarios

### Adding a New Stock to India Universe
Edit `tickers/india_universe.json`:
```json
{"ticker": "NEWSTOCK.NS", "label": "New Stock", "sector": "Technology", "mcap_proxy": "INFY"}
```
No code change needed; restart dashboard.

### Fixing a Financial Calculation
1. **Sharpe ratio:** Modify `annualised_mean_return()` or `annualised_volatility()` in `calculations.py`
2. **Ensure consistency:** Both per-asset Sharpe and portfolio Sharpe use the same numerator (`annualised_mean_return`)
3. **Test:** Build a 3-5 asset portfolio in the Builder tab and verify Sharpe matches Overview tab

### Updating Hardcoded Constants
- **Risk-free rate fallback:** `calculations.py:14` (currently 6.5%)
- **FX fallback:** `data_loader.py:476` (currently 85.5)
- **Benchmark rates in Portfolio Builder:** `tab_builder.py:15-18` (3.5% savings, 7.25% FD, 12% index, 5.5% inflation)

### Adding a New Tab
1. Create `shared/tabs/tab_mynew.py` with `def render(*, filtered, metrics, market, usd_inr): ...`
2. Add tab selector in `shared/dashboard.py:166-173`
3. Import and dispatch in dashboard orchestrator

---

## Known Limitations & Trade-offs

### Performance
- **First India dashboard load:** ~20-30 sec due to 110 ticker batch download. Subsequent loads cached for 15 min.
- **NSE is not used:** Removed because sequential NSE requests (100+ tickers with throttling) took 2-5 min. yfinance is 100x faster.
- **ThreadPool workers capped at 2-5:** Prevents overwhelming upstream APIs.

### Data Quality
- **Sharpe thresholds are heuristic:** Buy (≥1.0 Sharpe AND >8% 1Y), Hold (≥0.35 AND ≥0%), Sell (otherwise). Not backtested.
- **Benchmark rates are illustrative:** Portfolio Builder uses fixed rates (3.5% savings, 7.25% FD). Should be parameterized or fetched live.
- **SML slope is dynamic:** Computed from market index data (not hardcoded anymore).

### Compliance
- **Educational tool only:** All signals are quantitative; not investment advice. Disclaimer on home page footer + dashboard banner.
- **SEBI 5-stage risk profiler:** Used to filter assets by risk category; not an official SEBI tool.

---

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| yfinance for India + US data | Fast batch API; NSE throttles on bulk requests |
| Weekly returns for Sharpe | More stable than daily; annual 52-week scaling is standard |
| Full covariance matrix | Accounts for sector correlations; naive sum underestimates portfolio risk |
| 15-min cache for market data | Balances responsiveness vs. API rate limits |
| Streamlit (not React/FastAPI) | Rapid prototyping; no backend maintenance; single-user educational tool |
| JSON universe files | Asset lists are user-editable without code recompilation |

---

## API Key Setup

Create `.streamlit/secrets.toml` with:
```toml
GROQ_API_KEY = "gsk_..."           # Free at console.groq.com
ALPHA_VANTAGE_API_KEY = "..."      # Free at alphavantage.co
```

Both free tiers are sufficient for single-user development.

---

## Recent Changes (Latest Session)

- **Removed NSE Phase 1 loop:** Sequential NSE requests (110 tickers) took 2-5 min. Switched to yfinance batch for speed.
- **Fixed duplicate index warnings:** Added deduplication in `_extract_close()` to handle MultiIndex yfinance returns.
- **Optimized ThreadPool workers:** Reduced concurrent requests (2-5 workers) to avoid overwhelming upstream APIs.
- **Enhanced README:** Added API key setup links, troubleshooting section, and usage guide for new users.

---

## Where to Find Things

| What | Where |
|------|-------|
| Financial math (Sharpe, volatility, portfolio variance) | `shared/calculations.py` |
| Data fetching (yfinance, caching, FX conversion) | `shared/data_loader.py` |
| Dashboard layout & tab orchestration | `shared/dashboard.py` |
| AI financial analysis prompt | `shared/ai_analysis.py` |
| CSS design tokens & component styles | `shared/theme.py` |
| Market Overview tab | `shared/tabs/tab_overview.py` |
| Portfolio Builder with Monte Carlo | `shared/tabs/tab_builder.py` |
| Ticker Search + AI analysis | `shared/tabs/tab_search.py` |
| Heatmaps & gainers/decliners | `shared/tabs/tab_heatmap.py` |
| Price history with technical overlays | `shared/tabs/tab_charts.py` |
| Efficient Frontier & SML | `shared/tabs/tab_risk.py` |
| Financial glossary | `shared/tabs/tab_glossary.py` |
| Home page (live pulse, intelligence chips) | `home.py` |
| India dashboard entry point | `pages/1_india_market.py` |
| US dashboard entry point | `pages/2_us_market.py` |
| Asset lists (editable) | `tickers/india_universe.json`, `tickers/us_universe.json` |
