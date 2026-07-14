"""Data loading pipeline for Nivesh Terminal.

Fetches price history from multiple sources (NSE, yfinance, Alpha Vantage),
handles caching, currency conversion, and batch downloading for speed.
"""
from __future__ import annotations  # Allow modern type hints

import os                          # For reading environment variables
import time                        # (reserved for future retry logic)
from concurrent.futures import ThreadPoolExecutor, as_completed  # Parallel fetching
from datetime import datetime, timedelta, timezone               # Timestamps

import pandas as pd     # DataFrames for price data
import requests         # HTTP calls to FX rate API
import streamlit as st  # Caching and UI integration
import yfinance as yf   # Yahoo Finance API wrapper


# ── Low-level helpers ─────────────────────────────────────────────────────────

def _normalise_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Clean up a raw OHLCV DataFrame from any source.

    Handles yfinance MultiIndex columns, duplicate column names,
    timezone-aware indices, and duplicate dates.
    """
    if df.empty:
        return df
    # yfinance sometimes returns MultiIndex columns (ticker, field) — flatten to just field
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    # yfinance 0.2.x can produce duplicate column names after flattening — keep first
    df = df.loc[:, ~df.columns.duplicated()]
    # Keep only standard OHLCV columns that exist
    keep = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    out = df[keep].copy()
    # Remove timezone info (everything stored as naive UTC) and deduplicate dates
    out.index = pd.to_datetime(out.index).tz_localize(None)
    out = out[~out.index.duplicated(keep="last")]
    return out.sort_index()  # Chronological order


def _apply_fx(df: pd.DataFrame, usd_inr: float) -> pd.DataFrame:
    """Convert USD prices to INR by multiplying OHLC columns by the exchange rate."""
    if df.empty or usd_inr == 1:
        return df  # Nothing to convert
    out = df.copy()
    for col in ["Open", "High", "Low", "Close"]:
        if col in out.columns:
            out[col] = out[col] * usd_inr  # USD → INR conversion
    return out


def _yf_history(ticker: str, period: str, interval: str) -> pd.DataFrame:
    """Download a single ticker from yfinance and normalise the result."""
    return _normalise_ohlcv(
        yf.download(ticker, period=period, interval=interval,
                    auto_adjust=True, progress=False, threads=False)
    )


def _nse_symbol(ticker: str) -> str:
    """Convert a yfinance-style ticker to an NSE symbol.
    E.g. 'RELIANCE.NS' → 'RELIANCE', '^NSEI' → 'NIFTY 50'."""
    return ticker.replace(".NS", "").replace("^NSEI", "NIFTY 50").replace("^BSESN", "SENSEX")


# ── Batch yfinance download ───────────────────────────────────────────────────

def _batch_yf_download(tickers: list[str], period: str, interval: str) -> dict[str, pd.DataFrame]:
    """Download multiple tickers in a single yfinance HTTP request.

    This is the key speed optimisation: instead of 110 individual HTTP calls,
    we make 1 call that returns all tickers at once.

    Returns dict of ticker → normalised OHLCV DataFrame.
    Missing/failed tickers get an empty DataFrame — callers should check .empty.
    """
    if not tickers:
        return {}  # Nothing to download

    # Single batch call for all tickers — much faster than one-by-one
    raw = yf.download(
        tickers,
        period=period,
        interval=interval,
        auto_adjust=True,        # Use adjusted close prices (accounts for splits/dividends)
        progress=False,          # Don't print progress bar
        threads=True,            # yfinance internal threading for the batch
        group_by="ticker",       # Result columns: level-0 = ticker, level-1 = OHLCV field
    )

    results: dict[str, pd.DataFrame] = {}

    if len(tickers) == 1:
        # Edge case: single-ticker batch returns flat columns (not MultiIndex)
        t = tickers[0]
        results[t] = _normalise_ohlcv(raw.copy())
        return results

    # Multi-ticker: columns are a MultiIndex like (AAPL, Close), (AAPL, Open), etc.
    if isinstance(raw.columns, pd.MultiIndex):
        for t in tickers:
            try:
                df = raw[t].dropna(how="all")       # Extract this ticker's data
                results[t] = _normalise_ohlcv(df.copy())
            except KeyError:
                results[t] = pd.DataFrame()          # Ticker not in result (delisted?)
    else:
        # Unexpected format — give every ticker an empty DataFrame
        for t in tickers:
            results[t] = pd.DataFrame()

    return results


# ── Per-ticker NSE primary source ─────────────────────────────────────────────

def _fetch_india_primary(ticker: str, period: str, interval: str) -> pd.DataFrame:
    """Fetch Indian equity data directly from NSE (National Stock Exchange).

    Tries jugaad-data first, then nsepython as fallback. Both scrape NSE directly
    and are faster/more accurate than yfinance for Indian stocks.
    """
    years = 2 if period == "2y" else 20      # How many years of history to fetch
    end   = datetime.now()                    # Current date
    start = end.replace(year=end.year - years)  # Go back N years
    symbol = _nse_symbol(ticker)              # Convert to NSE symbol format

    # Attempt 1: jugaad-data library (most reliable NSE source)
    try:
        from jugaad_data.nse import stock_df
        raw = stock_df(symbol=symbol, from_date=start.date(), to_date=end.date(), series="EQ")
        # Rename columns to standard OHLCV format
        raw = raw.rename(columns={
            "DATE": "Date", "OPEN": "Open", "HIGH": "High",
            "LOW": "Low", "CLOSE": "Close", "VOLUME": "Volume",
        })
    except Exception:
        # Attempt 2: nsepython library (backup NSE source)
        try:
            from nsepython import equity_history
            raw = equity_history(symbol, "EQ", start.strftime("%d-%m-%Y"), end.strftime("%d-%m-%Y"))
            raw = raw.rename(columns={
                "CH_TIMESTAMP":        "Date",
                "CH_OPENING_PRICE":    "Open",
                "CH_TRADE_HIGH_PRICE": "High",
                "CH_TRADE_LOW_PRICE":  "Low",
                "CH_CLOSING_PRICE":    "Close",
                "CH_TOT_TRADED_QTY":   "Volume",
            })
        except Exception as exc:
            raise RuntimeError("NSE primary source failed") from exc

    if raw.empty:
        raise RuntimeError("NSE returned no rows")

    # Clean up: set Date as index, keep only OHLCV columns, sort by date
    raw["Date"] = pd.to_datetime(raw["Date"])
    out = raw.set_index("Date")[["Open", "High", "Low", "Close", "Volume"]].sort_index()

    # If weekly data requested, resample daily data to weekly (Friday close)
    if interval == "1wk":
        out = (
            out.resample("W-FRI")
               .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
               .dropna(subset=["Close"])
        )
    return out


# ── US Alpha Vantage fallback ─────────────────────────────────────────────────

def _fetch_us_alpha_vantage(ticker: str, period: str, interval: str) -> pd.DataFrame:
    """Fetch US equity data from Alpha Vantage (backup for yfinance)."""
    # Try to get API key from Streamlit secrets first, then environment variable
    try:
        secret_key = st.secrets.get("ALPHA_VANTAGE_API_KEY", None)
    except Exception:
        secret_key = None
    api_key = secret_key or os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        raise RuntimeError("ALPHA_VANTAGE_API_KEY is not configured")

    # Choose the right API function based on interval
    function = "TIME_SERIES_DAILY_ADJUSTED" if interval == "1d" else "TIME_SERIES_WEEKLY_ADJUSTED"
    url      = "https://www.alphavantage.co/query"

    # Make the API request
    response = requests.get(
        url,
        params={"function": function, "symbol": ticker, "outputsize": "full", "apikey": api_key},
        timeout=20,
    )
    response.raise_for_status()  # Raise error if HTTP status is not 200

    # Parse the JSON response
    payload = response.json()
    key = "Time Series (Daily)" if interval == "1d" else "Weekly Adjusted Time Series"
    if key not in payload:
        raise RuntimeError(payload.get("Note") or payload.get("Error Message") or "Alpha Vantage returned no time series")

    # Convert JSON time series to DataFrame
    frame = pd.DataFrame.from_dict(payload[key], orient="index")
    frame.index = pd.to_datetime(frame.index)
    # Map Alpha Vantage column names to standard OHLCV names
    frame = frame.rename(columns={
        "1. open":          "Open",
        "2. high":          "High",
        "3. low":           "Low",
        "4. close":         "Close",
        "5. adjusted close": "Close",  # Prefer adjusted close
        "6. volume":        "Volume",
    })
    # Convert all values to numbers, sort by date, trim to requested period
    out = frame[["Open", "High", "Low", "Close", "Volume"]].apply(pd.to_numeric, errors="coerce").sort_index()
    cutoff = pd.Timestamp.now() - pd.DateOffset(years=2 if period == "2y" else 20)
    return out.loc[out.index >= cutoff]


def _fetch_primary(ticker: str, market: str, period: str, interval: str) -> pd.DataFrame:
    """Route to the correct primary data source based on market."""
    if market == "india":
        return _fetch_india_primary(ticker, period, interval)
    return _fetch_us_alpha_vantage(ticker, period, interval)


# ── Single-ticker public API (used by Search / Compare tabs) ──────────────────

def fetch_asset_history(
    ticker: str, market: str, period: str, interval: str, usd_inr: float
) -> pd.DataFrame:
    """Fetch a single ticker's OHLCV history with automatic fallback.

    Tries the primary source (NSE for India, Alpha Vantage for US) first.
    If that fails, falls back to yfinance. Index tickers (^NSEI etc.) skip
    straight to yfinance since they're not on NSE/Alpha Vantage.
    """
    is_index = ticker.startswith("^")  # Index tickers start with ^
    try:
        if is_index:
            raise RuntimeError("index ticker — use yfinance directly")
        hist   = _fetch_primary(ticker, market, period, interval)
        source = "primary"
    except Exception:
        hist   = _yf_history(ticker, period, interval)  # Fallback to yfinance
        source = "yfinance fallback"

    # Convert US prices from USD to INR — but NOT index levels. An index
    # (^GSPC, ^VIX, ^FTSE, …) is a unitless point value, not a dollar price;
    # multiplying it by USD/INR would inflate it ~95× (S&P 7,524 → 718,571).
    # US stocks/ETFs (no ^ prefix) still convert so they compare in INR.
    if market == "us" and not is_index and not hist.empty:
        hist = _apply_fx(hist, usd_inr)

    # Remove any duplicate dates (can happen from multiple sources)
    if not hist.empty and hist.index.duplicated().any():
        hist = hist[~hist.index.duplicated(keep="last")]

    hist.attrs["source"] = source  # Tag which source this data came from
    return hist


@st.cache_data(ttl=900, show_spinner=False)  # Cache for 15 minutes
def fetch_ticker_history(
    ticker: str, market: str, usd_inr: float
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (df_daily_2y, df_weekly_20y) for a single ticker (15-min cache).

    Used by the Search and Compare tabs — repeated queries hit cache rather
    than re-fetching.
    """
    daily  = fetch_asset_history(ticker, market, "2y",  "1d",  usd_inr)  # 2 years of daily data
    weekly = fetch_asset_history(ticker, market, "20y", "1wk", usd_inr)  # 20 years of weekly data
    return daily, weekly


# ── Bulk loader (the fast path) ───────────────────────────────────────────────

def _extract_close(df: pd.DataFrame) -> pd.Series | None:
    """Pull the Close price column from a DataFrame. Returns None if empty."""
    if df.empty or "Close" not in df.columns:
        return None
    c = df["Close"]
    # Handle case where Close is a DataFrame (MultiIndex) instead of Series
    s = c.iloc[:, 0] if isinstance(c, pd.DataFrame) else c
    # Remove duplicate index values (keep the last occurrence)
    s = s[~s.index.duplicated(keep='last')]
    return s


@st.cache_data(ttl=900, show_spinner=False)  # Cache for 15 minutes
def load_market_data(
    universe_raw: tuple, market: str, usd_inr: float
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load close-price history for every asset in the universe.

    Speed strategy
    ──────────────
    US market
        Two yfinance batch calls (daily + weekly) — one HTTP request covers all
        110 tickers each.  Result: ~2 network requests instead of 220.

    India market
        Phase 1 – NSE primary (jugaad-data / nsepython) in a ThreadPool.
                  These must remain per-ticker; NSE has no bulk API.
        Phase 2 – All NSE failures + index tickers (^) are batched into a single
                  yf.download([...]) call per period.
                  Result: 2 batch calls for fallbacks instead of N individual ones.
    """
    # Extract ticker symbols from the universe definition
    tickers = [dict(a)["ticker"] for a in universe_raw]
    daily_closes:  dict[str, pd.Series] = {}   # Will hold each ticker's daily close prices
    weekly_closes: dict[str, pd.Series] = {}   # Will hold each ticker's weekly close prices
    sources:       dict[str, str]       = {}   # Track which API source each ticker used

    # ── US: pure batch path (2 HTTP calls for all 110 tickers) ────────────
    if market == "us":
        daily_batch  = _batch_yf_download(tickers, "2y",  "1d")   # 1 call for all daily data
        weekly_batch = _batch_yf_download(tickers, "20y", "1wk")  # 1 call for all weekly data
        for t in tickers:
            d = _apply_fx(daily_batch.get(t,  pd.DataFrame()), usd_inr)   # Convert USD → INR
            w = _apply_fx(weekly_batch.get(t, pd.DataFrame()), usd_inr)
            if not d.empty and "Close" in d.columns:
                daily_closes[t]  = _extract_close(d)
                sources[t] = "yfinance"
            if not w.empty and "Close" in w.columns:
                weekly_closes[t] = _extract_close(w)

    # ── India: Use yfinance for speed (NSE is too slow for bulk requests) ──
    else:
        # Batch yfinance call for all tickers (both indices and equities)
        # This is ~100x faster than trying NSE sequentially
        yf_d_batch = _batch_yf_download(tickers, "2y",  "1d")   # 1 batch call
        yf_w_batch = _batch_yf_download(tickers, "20y", "1wk")  # 1 batch call

        # Collect close prices from yfinance
        for t in tickers:
            d = yf_d_batch.get(t,  pd.DataFrame())
            w = yf_w_batch.get(t, pd.DataFrame())
            sources[t] = "yfinance"
            s = _extract_close(d)
            if s is not None:
                daily_closes[t] = s
            s = _extract_close(w)
            if s is not None:
                weekly_closes[t] = s

    # Build the final DataFrames — one column per ticker, one row per date
    _IST = timezone(timedelta(hours=5, minutes=30))
    df_daily  = pd.DataFrame(daily_closes).sort_index()   # Daily close prices
    df_weekly = pd.DataFrame(weekly_closes).sort_index()   # Weekly close prices
    # Attach metadata to the daily DataFrame (market caps populated later)
    df_daily.attrs["market_caps"] = {}
    df_daily.attrs["sources"]     = sources                # Which API each ticker used
    df_daily.attrs["fetched_at"]  = datetime.now(_IST).strftime("%d %b %Y, %H:%M IST")
    return df_daily, df_weekly


# ── Market caps (day-cached, second wave) ────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False)  # Cache for 24 hours
def get_market_caps(tickers: tuple, market: str, usd_inr: float) -> dict[str, float | None]:
    """Fetch market capitalisation for all tickers (₹).

    Called after price data is ready so the UI renders prices first.
    Workers bumped to 20 — fast_info calls are lightweight HTTP requests.
    """
    def _one(t: str) -> tuple[str, float | None]:
        """Fetch market cap for a single ticker."""
        try:
            cap = yf.Ticker(t).fast_info.get("market_cap")
            # Convert USD market cap to INR for US stocks
            return t, None if cap is None else float(cap) * (usd_inr if market == "us" else 1)
        except Exception:
            return t, None  # Silently skip on failure

    caps: dict[str, float | None] = {}
    # Parallel fetch with 5 workers — fast_info is a quick lightweight call
    with ThreadPoolExecutor(max_workers=5) as pool:
        for ticker, cap in pool.map(_one, tickers):
            caps[ticker] = cap
    return caps


# ── Risk-free rate ────────────────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False)  # Cache for 24 hours
def get_risk_free_rate() -> float:
    """Fetch live India 10Y government bond yield as the risk-free rate.

    The risk-free rate is used as the Sharpe ratio denominator — it's the
    return you'd get with zero risk (government bonds). Falls back to 6.5%
    if the live rate is unavailable.

    NOTE (May 2026): ^INBMK has been intermittently delisted from Yahoo
    Finance — the code keeps the lookup in case it returns, but the 6.5%
    fallback is currently the operative value for all Sharpe calculations.
    """
    try:
        # ^INBMK is India's 10Y benchmark bond yield on yfinance (may be unavailable)
        hist = yf.download("^INBMK", period="5d", progress=False, auto_adjust=True)
        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = hist.columns.get_level_values(0)
        close = hist.get("Close", pd.Series(dtype=float))
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        close = close.dropna()
        if not close.empty:
            rate = float(close.iloc[-1]) / 100   # Yield is in %, convert to decimal
            if 0.02 < rate < 0.20:               # Sanity check: between 2% and 20%
                return rate
    except Exception:
        pass
    return 0.065  # Fallback: 6.5%


# ── FX rate ───────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)  # Cache for 5 minutes (FX changes fast)
def get_usd_inr() -> float:
    """Get current USD/INR exchange rate.

    Tries exchangerate.host API first, then yfinance USDINR=X, then falls back
    to a hardcoded rate as last resort.
    """
    # Attempt 1: exchangerate.host (free FX API)
    try:
        response = requests.get(
            "https://api.exchangerate.host/latest",
            params={"base": "USD", "symbols": "INR"},
            timeout=8,
        )
        response.raise_for_status()
        rate = float(response.json()["rates"]["INR"])
        if rate > 0:
            return rate
    except Exception:
        pass

    # Attempt 2: yfinance USD/INR forex pair
    try:
        fx = yf.download("USDINR=X", period="5d", progress=False, auto_adjust=True)
        if isinstance(fx.columns, pd.MultiIndex):
            fx.columns = fx.columns.get_level_values(0)
        rate = float(fx["Close"].dropna().iloc[-1])
        if rate > 0:
            return rate
    except Exception:
        pass

    import warnings
    warnings.warn("USD/INR live fetch failed — using hardcoded fallback rate of 95.5. US prices may be slightly inaccurate.", stacklevel=2)
    return 95.5  # Hardcoded fallback (as of May 2026 ~₹95.78). Update periodically if live feeds keep failing.


# ── Live quotes (home page pulse bar) ────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)  # Cache for 5 minutes
def get_live_quotes(pairs: tuple, usd_inr: float) -> list[dict]:
    """Fetch latest price and daily change for a list of index/asset pairs.

    Used on the home page to show the live market pulse bar with
    Nifty 50, Sensex, S&P 500, etc.
    """
    rows = []
    for ticker, label, market in pairs:
        hist  = fetch_asset_history(ticker, market, "5d", "1d", usd_inr)  # Last 5 days
        close = hist.get("Close", pd.Series(dtype=float)).dropna()
        if len(close) < 2:
            continue  # Need today + yesterday to compute change
        prev = float(close.iloc[-2])  # Yesterday's close
        cur  = float(close.iloc[-1])  # Today's close
        if prev == 0:
            continue  # Avoid division by zero
        # Calculate daily percentage change
        rows.append({"ticker": ticker, "label": label, "price": cur, "chg": round((cur / prev - 1) * 100, 2)})
    return rows
