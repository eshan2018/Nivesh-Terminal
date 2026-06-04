"""Core financial mathematics for Artha Terminal.

Contains all return, volatility, Sharpe, risk, SIP, portfolio optimisation,
and technical indicator calculations. No UI code — pure math only.
"""
from __future__ import annotations  # Allow modern type hints

import math                   # For sqrt, isnan
from typing import Iterable   # For type-hinting the universe parameter

import numpy as np    # For array math (portfolio optimisation, covariance)
import pandas as pd   # For time series manipulation


# ── Constants ────────────────────────────────────────────────────────────────

# India 10Y G-Sec yield fallback — used when live rate unavailable
RISK_FREE_RATE = 0.065  # 6.5% annual

# Maps SIP contribution frequency names to how many times per year
FREQ_MULTIPLIER = {
    "Monthly": 12,     # 12 contributions per year
    "Quarterly": 4,    # 4 contributions per year
    "Yearly": 1,       # 1 contribution per year
    "One-time": 1,     # Lump sum (special case)
}

# SEBI-aligned 5-stage risk scale — ordered from most conservative to most aggressive
RISK_ORDER = ["Conservative", "Moderate", "Balanced", "Growth", "Aggressive"]

# Which asset categories each risk profile is allowed to invest in
RISK_ALLOWED = {
    "Conservative": {"Safe Haven", "Stabilizer"},                    # Only safe assets
    "Moderate":     {"Safe Haven", "Stabilizer"},                    # Safe + stable
    "Balanced":     {"Safe Haven", "Stabilizer", "High Growth"},     # All categories
    "Growth":       {"Stabilizer", "High Growth"},                   # Skip safe haven
    "Aggressive":   {"Safe Haven", "Stabilizer", "High Growth"},     # Full access
}

# Target allocation percentages for each risk profile across 3 asset categories
ALLOCATIONS = {
    "Conservative": {"Safe Haven": 0.55, "Stabilizer": 0.40, "High Growth": 0.05},
    "Moderate":     {"Safe Haven": 0.35, "Stabilizer": 0.50, "High Growth": 0.15},
    "Balanced":     {"Safe Haven": 0.20, "Stabilizer": 0.50, "High Growth": 0.30},
    "Growth":       {"Safe Haven": 0.10, "Stabilizer": 0.35, "High Growth": 0.55},
    "Aggressive":   {"Safe Haven": 0.05, "Stabilizer": 0.20, "High Growth": 0.75},
}


# ── Safe math helpers ────────────────────────────────────────────────────────

def safe_div(numerator: float | int | None, denominator: float | int | None) -> float | None:
    """Safely divide two numbers. Returns None if either is missing, NaN, or denominator is zero."""
    if numerator is None or denominator is None:
        return None  # Can't divide if either value is missing
    if pd.isna(numerator) or pd.isna(denominator) or float(denominator) == 0:
        return None  # Can't divide by zero or NaN
    return float(numerator) / float(denominator)


# ── Return calculations ──────────────────────────────────────────────────────

def get_return(prices: pd.Series, offset: pd.DateOffset) -> float | None:
    """Calculate percentage return over a calendar period (e.g. 1 month, 1 year).

    Uses nearest-date matching with adaptive tolerance — not hardcoded day counts.
    Example: get_return(prices, pd.DateOffset(years=1)) gives the 1-year return.
    """
    series = pd.to_numeric(prices, errors="coerce").dropna()  # Clean non-numeric values
    if len(series) < 2:
        return None  # Need at least 2 prices to compute a return
    series.index = pd.to_datetime(series.index)  # Ensure dates are datetime objects
    last_date = series.index.max()               # Most recent date in the series
    target = last_date - offset                  # Date we want to look back to

    # If our data doesn't go back far enough, return None
    if series.index.min() > target:
        return None

    # Find the nearest available date to our target date
    loc = series.index.get_indexer([target], method="nearest")
    if loc.size == 0 or loc[0] < 0:
        return None  # No match found

    # Check if the nearest date is within acceptable tolerance
    actual = series.index[loc[0]]
    # Tolerance scales with the period: 7 days min, 45 days max, 15% of period
    tolerance = max(7, min(45, int((last_date - target).days * 0.15)))
    if abs((actual - target).days) > tolerance:
        return None  # Nearest date is too far from target

    # Calculate return: (current_price / past_price) - 1, as percentage
    ratio = safe_div(series.iloc[-1], series.iloc[loc[0]])
    if ratio is None:
        return None
    return round((ratio - 1.0) * 100, 2)  # Convert to percentage with 2 decimals


def annualised_volatility(prices: pd.Series, periods_per_year: int) -> float | None:
    """Calculate annualised volatility (standard deviation of returns, scaled to 1 year).

    For weekly data: periods_per_year=52 → σ_weekly × √52
    For daily data:  periods_per_year=252 → σ_daily × √252
    """
    returns = pd.to_numeric(prices, errors="coerce").dropna().pct_change().dropna()
    # Need minimum data points to produce meaningful volatility
    if len(returns) < max(12, periods_per_year // 2):
        return None
    # Standard deviation × sqrt(periods) = annualised volatility, × 100 for percentage
    vol = float(returns.std() * math.sqrt(periods_per_year) * 100)
    if pd.isna(vol) or vol == 0:
        return None  # Zero volatility is meaningless (flat line)
    return round(vol, 2)


def sharpe_ratio(
    annual_return_pct: float | None,
    volatility_pct: float | None,
    rfr: float | None = None,
) -> float | None:
    """Sharpe Ratio = (Return - Risk-Free Rate) / Volatility.

    Measures excess return per unit of risk. Higher = better.
    Inputs are in percentage form (e.g. 12.5 for 12.5%).
    """
    if annual_return_pct is None or volatility_pct is None:
        return None
    if pd.isna(annual_return_pct) or pd.isna(volatility_pct) or volatility_pct == 0:
        return None  # Can't divide by zero volatility
    rate = rfr if rfr is not None else RISK_FREE_RATE  # Use live rate or 6.5% fallback
    # Convert percentages to decimals, compute Sharpe, round to 2 decimals
    return round(((annual_return_pct / 100) - rate) / (volatility_pct / 100), 2)


# ── SIP (Systematic Investment Plan) ────────────────────────────────────────

def sip_future_value(annual_amount: float, cagr: float, years: int, is_bulk: bool = False) -> float:
    """Annuity-due SIP formula — assumes beginning-of-period contributions.

    For lump sum (is_bulk=True): FV = P × (1 + r)^n
    For SIP (is_bulk=False):     FV = P × [((1+r)^n - 1) / r] × (1+r)
    """
    if years <= 0:
        return 0.0 if not is_bulk else float(annual_amount)  # No growth if no time
    if is_bulk:
        return float(annual_amount) * ((1 + cagr) ** years)  # Compound growth on lump sum
    if cagr == 0:
        return float(annual_amount) * years  # Zero return: just sum up contributions
    # Standard annuity-due formula: each payment compounds from its deposit date
    return float(annual_amount) * ((((1 + cagr) ** years) - 1) / cagr) * (1 + cagr)


# ── Risk profiling ───────────────────────────────────────────────────────────

def get_risk_profile(age: int, horizon: int, drawdown_tolerance: str, knowledge: str) -> str:
    """Score-based SEBI 5-tier risk profiling.

    Inputs from the sidebar questionnaire are converted to a 4-15 point score,
    then mapped to one of: Conservative, Moderate, Balanced, Growth, Aggressive.
    """
    score = 0
    # Younger investors can take more risk (4 pts max)
    score += 4 if age < 30 else 3 if age < 40 else 2 if age < 55 else 1
    # Longer horizon = more risk capacity (4 pts max)
    score += 1 if horizon < 3 else 2 if horizon < 7 else 3 if horizon < 12 else 4
    # Higher drawdown comfort = more risk tolerance (4 pts max)
    score += {"Low": 1, "Medium": 2, "High": 4}.get(drawdown_tolerance, 2)
    # More knowledge = better equipped for risk (3 pts max)
    score += {"Beginner": 1, "Intermediate": 2, "Advanced": 3}.get(knowledge, 2)

    # Map total score (4-15) to risk profile
    if score <= 6:
        return "Conservative"
    if score <= 8:
        return "Moderate"
    if score <= 10:
        return "Balanced"
    if score <= 12:
        return "Growth"
    return "Aggressive"


def annualised_mean_return(prices: pd.Series, periods_per_year: int) -> float | None:
    """Mean periodic return annualised — correct numerator for Sharpe ratio.

    Uses mean(r_t) × T rather than the point-in-time (P_end/P_start - 1).
    For a trending stock the difference can be 30-40%.
    """
    rets = pd.to_numeric(prices, errors="coerce").dropna().pct_change().dropna()
    if len(rets) < max(12, periods_per_year // 2):
        return None  # Not enough data for meaningful average
    # Average of all periodic returns × number of periods = annualised return
    val = float(rets.mean() * periods_per_year * 100)  # × 100 for percentage
    return round(val, 2) if not math.isnan(val) else None


# ── Per-asset metrics aggregation ────────────────────────────────────────────

def compute_metrics(
    df_daily: pd.DataFrame,
    df_weekly: pd.DataFrame,
    universe: Iterable[tuple],
    rfr: float | None = None,
) -> pd.DataFrame:
    """Build a metrics table with one row per asset: returns, volatility, Sharpe, etc.

    This is the core function that powers the Market Overview table and all filtering.
    """
    rows = []
    daily = df_daily.copy()
    weekly = df_weekly.copy()
    daily.index = pd.to_datetime(daily.index)    # Ensure datetime index
    weekly.index = pd.to_datetime(weekly.index)
    market_caps = daily.attrs.get("market_caps", {})  # Pre-fetched market caps

    # Loop through every asset in the universe (110 India or 110 US)
    for asset_raw in universe:
        asset = dict(asset_raw)       # Convert from tuple-of-tuples back to dict
        ticker = asset["ticker"]

        # Skip if this ticker wasn't loaded (API failure, etc.)
        if ticker not in daily.columns:
            continue

        # Get daily close prices, cleaned of non-numeric values
        d = pd.to_numeric(daily[ticker], errors="coerce").dropna()
        if len(d) < 2:
            continue  # Need at least 2 prices

        # Get weekly close prices (for long-term metrics) — may be empty
        w = pd.to_numeric(weekly[ticker], errors="coerce").dropna() if ticker in weekly.columns else pd.Series(dtype=float)

        # Current price and 1-day return
        cur = float(d.iloc[-1])                          # Latest close price
        prev_ratio = safe_div(cur, d.iloc[-2])           # Today / Yesterday
        one_day = None if prev_ratio is None else round((prev_ratio - 1) * 100, 2)

        # 1-year return: use weekly data if available (less noise), else daily
        one_year = get_return(w if len(w) else d, pd.DateOffset(years=1))

        # Long-term volatility: weekly returns × √52 (suitable for 1Y+ holding periods)
        vol = annualised_volatility(w, 52)

        # Short-term volatility: daily returns × √252 (suitable for ~1M holding period)
        vol_1m = annualised_volatility(d, 252)

        # Sharpe uses annualised MEAN weekly return — not point-in-time 1Y return
        # This is more statistically robust for trending assets
        ann_mean = annualised_mean_return(w, 52) if len(w) >= 26 else None

        # Build the row with all metrics for this asset
        rows.append(
            {
                "Ticker": ticker,
                "Name": asset["name"],
                "Sector": asset["sector"],
                "Type": asset["type"],                              # equity, etf, or fund
                "Category": asset.get("category", "Stabilizer"),    # Risk category
                "Tier": asset.get("tier", "Universe"),              # Nifty 50, etc.
                "Price (₹)": round(cur, 2),
                "1D%": one_day,                                      # 1-day return
                "1W%": get_return(d, pd.DateOffset(weeks=1)),        # 1-week return
                "1M%": get_return(d, pd.DateOffset(months=1)),       # 1-month return
                "3M%": get_return(d, pd.DateOffset(months=3)),       # 3-month return
                "6M%": get_return(d, pd.DateOffset(months=6)),       # 6-month return
                "1Y%": one_year,                                     # 1-year return
                "3Y%": get_return(w, pd.DateOffset(years=3)),        # 3-year return
                "5Y%": get_return(w, pd.DateOffset(years=5)),        # 5-year return
                "10Y%": get_return(w, pd.DateOffset(years=10)),      # 10-year return
                "Volatility": vol,                                   # Long-term vol
                "Vol 1M": vol_1m,                                    # Short-term vol
                "Sharpe": sharpe_ratio(ann_mean, vol, rfr=rfr),      # Risk-adjusted return
                "Market Cap": market_caps.get(ticker),               # Market cap in ₹
            }
        )
    return pd.DataFrame(rows)


# ── Portfolio-level statistics ───────────────────────────────────────────────

def portfolio_stats(
    metrics: pd.DataFrame,
    weights: dict[str, float],
    df_weekly: pd.DataFrame | None = None,
) -> dict[str, float | None]:
    """Weighted portfolio return + volatility.

    Volatility uses the full weekly-return covariance matrix when ``df_weekly`` is
    supplied, so cross-asset correlation is reflected. Without it, falls back to
    the zero-correlation approximation (sum of w²σ²) and the result is flagged
    as understated by the caller's UI layer.
    """
    # Filter metrics table to only the assets in our portfolio
    selected = metrics[metrics["Ticker"].isin(weights)]
    if selected.empty:
        return {"return": None, "volatility": None, "sharpe": None}

    # Normalise weights so they sum to 1.0
    total_weight = sum(weights.values())
    if total_weight == 0:
        return {"return": None, "volatility": None, "sharpe": None}

    # ── Portfolio return & volatility from weekly returns ─────────────────
    # Uses annualised mean return (mean(r_t) × 52) — same methodology as
    # per-asset Sharpe in compute_metrics(), ensuring consistency.
    annual_return: float | None = None
    vol: float | None = None

    if df_weekly is not None:
        # Get tickers that exist in both our portfolio and the weekly data
        valid = [t for t in weights if t in df_weekly.columns]
        if len(valid) >= 2:
            prices = df_weekly[valid].dropna()  # Aligned price matrix
            if len(prices) >= 26:  # Need at least 6 months of weekly data
                rets = prices.pct_change().dropna()  # Weekly return matrix
                w_vec = np.array([weights[t] / total_weight for t in valid])  # Weight vector

                # Annualised mean return (weighted sum of each asset's mean return)
                ann_means = rets.mean() * 52 * 100  # Same as annualised_mean_return()
                annual_return = float(w_vec @ ann_means[valid].values)  # Dot product

                # Portfolio volatility using full covariance matrix
                # This accounts for correlation between assets (diversification benefit)
                cov = rets.cov() * 52  # Annualise weekly covariance
                var = float(w_vec @ cov.values @ w_vec)  # w'Σw = portfolio variance
                if var > 0 and not math.isnan(var):
                    vol = math.sqrt(var) * 100  # √variance = standard deviation (%)

    # Fallback to 1Y% point-in-time return if weekly data unavailable
    if annual_return is None:
        annual_return = 0.0
        for _, row in selected.iterrows():
            w = weights[row["Ticker"]] / total_weight
            if pd.notna(row.get("1Y%")):
                annual_return += w * float(row["1Y%"])  # Weighted sum of 1Y returns

    # Fallback volatility: zero-correlation approximation (underestimates real vol)
    if vol is None:
        var_zero = 0.0
        for _, row in selected.iterrows():
            w = weights[row["Ticker"]] / total_weight
            if pd.notna(row.get("Volatility")):
                var_zero += (w * float(row["Volatility"])) ** 2  # Sum of w²σ²
        vol = math.sqrt(var_zero) if var_zero else None

    return {
        "return": round(annual_return, 2),
        "volatility": None if vol is None else round(vol, 2),
        "sharpe": sharpe_ratio(annual_return, vol) if vol is not None else None,
    }


# ── Verdict (heuristic signal) ───────────────────────────────────────────────

def verdict(return_1y: float | None, sharpe: float | None) -> str | None:
    """Heuristic quantitative signal based on Sharpe and 1Y return.

    Thresholds are illustrative defaults, NOT empirically backtested.
    These are quantitative indicators only — NOT buy/sell recommendations.
    Do not act on these signals without independent research.
    """
    if return_1y is None or sharpe is None:
        return None
    if sharpe >= 1 and return_1y > 8:      # Strong risk-adjusted return + solid absolute return
        return "Positive"
    if sharpe >= 0.35 and return_1y >= 0:   # Acceptable Sharpe + non-negative return
        return "Neutral"
    return "Caution"                         # Poor risk-adjusted metrics


# ── Display formatting ───────────────────────────────────────────────────────

def ret_color(value):
    """Return inline CSS color for positive (green), negative (red), or neutral."""
    if value is None or pd.isna(value):
        return ""
    return "color: #16a34a" if value > 0 else "color: #dc2626" if value < 0 else ""


def fmt_inr(x: float | int | None) -> str:
    """Format a number in Indian currency notation (Crores and Lakhs).
    ₹1,00,00,000 → '₹1.00 Cr', ₹1,00,000 → '₹1.00 L'."""
    if x is None or pd.isna(x):
        return "-"
    x = float(x)
    if abs(x) >= 1e7:           # 1 Crore = 10 million
        return f"₹{x / 1e7:.2f} Cr"
    if abs(x) >= 1e5:           # 1 Lakh = 100 thousand
        return f"₹{x / 1e5:.2f} L"
    return f"₹{x:,.0f}"        # Below 1 Lakh: show full number with commas


# ── Technical indicators ─────────────────────────────────────────────────────

def compute_sma(prices: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average — arithmetic mean of last N prices."""
    return prices.rolling(period).mean()


def compute_ema(prices: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average — gives more weight to recent prices."""
    return prices.ewm(span=period, adjust=False).mean()


def compute_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (RSI) using Wilder's EWM smoothing.

    RSI ranges from 0-100:
    - RSI > 70 = overbought (price may fall)
    - RSI < 30 = oversold (price may rise)
    """
    delta = pd.to_numeric(prices, errors="coerce").diff()      # Price changes
    gain = delta.clip(lower=0)                                  # Only positive changes
    loss = -delta.clip(upper=0)                                 # Only negative changes (made positive)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()  # Wilder-smoothed avg gain
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()  # Wilder-smoothed avg loss
    # RS = avg_gain / avg_loss. When avg_loss → 0 (pure uptrend), RS → ∞ → RSI → 100.
    # numpy.where avoids divide-by-zero warning; final NaN handled by clipping.
    rs = np.where(avg_loss > 0, avg_gain / avg_loss.replace(0, np.nan), np.inf)
    rsi = 100 - (100 / (1 + rs))                                # RSI formula
    return pd.Series(rsi, index=prices.index).round(2)


def compute_macd(
    prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD (Moving Average Convergence Divergence).
    Returns (macd_line, signal_line, histogram)."""
    p = pd.to_numeric(prices, errors="coerce")
    ema_fast = p.ewm(span=fast, adjust=False).mean()     # 12-period EMA (fast)
    ema_slow = p.ewm(span=slow, adjust=False).mean()     # 26-period EMA (slow)
    macd_line = ema_fast - ema_slow                       # MACD line = fast - slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()  # 9-period EMA of MACD
    return macd_line, signal_line, macd_line - signal_line          # histogram = MACD - signal


def compute_bollinger(
    prices: pd.Series, period: int = 20, std_dev: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Bollinger Bands — price channel based on moving average ± 2 standard deviations.
    Returns (upper_band, mid_band, lower_band)."""
    p = pd.to_numeric(prices, errors="coerce")
    mid = p.rolling(period).mean()              # Middle band = 20-period SMA
    std = p.rolling(period).std()               # Rolling standard deviation
    return mid + std_dev * std, mid, mid - std_dev * std  # Upper, Mid, Lower


# ── Risk metrics ─────────────────────────────────────────────────────────────

def get_max_drawdown(prices: pd.Series) -> float | None:
    """Maximum drawdown — the largest peak-to-trough decline (%).

    A drawdown of -35% means the asset fell 35% from its highest point before recovering.
    """
    s = pd.to_numeric(prices, errors="coerce").dropna()
    if len(s) < 2:
        return None
    roll_max = s.expanding().max()              # Running all-time high at each point
    dd = (s - roll_max) / roll_max * 100        # How far below the peak at each point
    val = float(dd.min())                       # The deepest trough
    return round(val, 2) if not math.isnan(val) else None


def get_rolling_drawdown(prices: pd.Series) -> pd.Series:
    """Full drawdown time series (%) for the underwater chart."""
    s = pd.to_numeric(prices, errors="coerce").dropna()
    roll_max = s.expanding().max()              # Running peak
    return ((s - roll_max) / roll_max * 100).round(2)  # % below peak at each date


def get_52w_stats(prices: pd.Series) -> dict:
    """52-week high, low, and current price vs 52W high (%)."""
    s = pd.to_numeric(prices, errors="coerce").dropna()
    if s.empty:
        return {"high": None, "low": None, "vs_high_pct": None}
    s.index = pd.to_datetime(s.index)
    cutoff = s.index.max() - pd.DateOffset(years=1)  # 1 year ago from latest date
    yr = s[s.index >= cutoff]                         # Last 52 weeks of data
    if yr.empty:
        yr = s  # If not enough data, use full history
    high = float(yr.max())                            # 52-week high
    low  = float(yr.min())                            # 52-week low
    cur  = float(s.iloc[-1])                          # Current price
    # How far current price is below the 52W high (negative = below high)
    vs_high = round((cur / high - 1) * 100, 2) if high > 0 else None
    return {"high": round(high, 2), "low": round(low, 2), "vs_high_pct": vs_high}


# ── Portfolio optimisation ───────────────────────────────────────────────────

def compute_portfolio_frontier(
    df_weekly: pd.DataFrame,
    tickers: list[str],
    n_portfolios: int = 2000,
) -> pd.DataFrame:
    """Monte Carlo efficient frontier using proper covariance from weekly returns.

    Generates 2000 random portfolio weight combinations and computes each one's
    return, volatility, and Sharpe ratio. The resulting cloud of dots approximates
    the efficient frontier (best return for each level of risk).
    """
    valid = [t for t in tickers if t in df_weekly.columns]  # Only use available tickers
    if len(valid) < 2:
        return pd.DataFrame()  # Need at least 2 assets
    prices = df_weekly[valid].dropna()    # Aligned price matrix (all assets on same dates)
    if len(prices) < 52:
        return pd.DataFrame()  # Need at least 1 year of weekly data
    rets = prices.pct_change().dropna()   # Weekly return matrix
    ann_mean = rets.mean() * 52           # Annualised expected return per asset
    ann_cov  = rets.cov() * 52            # Annualised covariance matrix
    n = len(valid)
    rng = np.random.default_rng(42)       # Fixed seed for reproducible results

    rows = []
    for _ in range(n_portfolios):
        w = rng.random(n)                 # Random weights
        w /= w.sum()                      # Normalise to sum to 1 (100%)
        port_ret = float(np.dot(w, ann_mean)) * 100   # Portfolio return (%)
        port_vol = float(math.sqrt(max(0.0, w @ ann_cov.values @ w))) * 100  # Portfolio vol (%)
        rows.append({
            "Vol":    round(port_vol, 3),
            "Return": round(port_ret, 3),
            "Sharpe": sharpe_ratio(port_ret, port_vol),
        })
    return pd.DataFrame(rows)


def sip_future_value_freq(
    amount_per_period: float,
    annual_rate: float,
    years: int,
    periods_per_year: int = 12,
) -> float:
    """FV for a recurring SIP with arbitrary contribution frequency.

    Converts annual rate to per-period rate, then applies annuity-due formula.
    periods_per_year: 252=daily, 52=weekly, 12=monthly, 4=quarterly, 1=yearly.
    """
    if years <= 0 or periods_per_year <= 0:
        return 0.0
    n = years * periods_per_year  # Total number of contributions
    if annual_rate == 0:
        return float(amount_per_period) * n  # No growth: just sum contributions
    # Convert annual rate to per-period rate using compound formula
    r = (1 + annual_rate) ** (1 / periods_per_year) - 1
    # Annuity-due FV: each contribution grows from its deposit date
    return float(amount_per_period) * (((1 + r) ** n - 1) / r) * (1 + r)


def compute_correlation_matrix(df_weekly: pd.DataFrame, tickers: list[str]) -> pd.DataFrame | None:
    """Pearson correlation matrix of weekly returns between selected tickers.

    Used to show how closely assets move together (diversification analysis).
    """
    valid = [t for t in tickers if t in df_weekly.columns]
    if len(valid) < 2:
        return None  # Need at least 2 assets
    prices = df_weekly[valid].dropna()
    if len(prices) < 26:
        return None  # Need at least 6 months of data
    return prices.pct_change().dropna().corr().round(3)  # Correlation of returns
