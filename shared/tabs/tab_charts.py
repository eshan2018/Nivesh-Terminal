"""Tab 4 — Price History: interactive chart with technical overlays."""
from __future__ import annotations  # Allow modern type hints

import pandas as pd              # DataFrame operations
import streamlit as st           # Streamlit UI framework

# Import financial calculation functions
from shared.calculations import get_max_drawdown, get_return
# Import data fetcher for individual asset history
from shared.data_loader import fetch_asset_history
# Import display helpers (formatting, dropdown builders, colors)
from shared.tabs._helpers import _MARGIN, asset_options, chg_color, fmt_num, fmt_pct, name_from, ticker_from
# Import Plotly theme constants
from shared.theme import PLOTLY_THEME, GRID_COLOR

import plotly.graph_objects as go          # Low-level Plotly charting
from plotly.subplots import make_subplots  # Multi-row chart layouts

# Import technical indicator functions
from shared.calculations import (
    compute_bollinger,  # Bollinger Bands (mean ± 2σ)
    compute_ema,        # Exponential Moving Average
    compute_macd,       # MACD (12-26-9 signal crossover)
    compute_rsi,        # Relative Strength Index (14-day)
    compute_sma,        # Simple Moving Average
)


def _price_chart(ticker: str, name: str, market: str, period: str, usd_inr: float,
                 overlays: list[str], subchart: str):
    """Build and return a Plotly Figure for one asset's price history.

    Supports SMA/EMA/Bollinger overlays on the main chart and
    RSI or MACD as a sub-chart below.
    """
    # Map user-facing period label → (yfinance period, interval, DateOffset for slicing)
    period_map = {
        "1W":  ("2y",  "1d",  pd.DateOffset(weeks=1)),    # Last 1 week from daily data
        "1M":  ("2y",  "1d",  pd.DateOffset(months=1)),   # Last 1 month from daily data
        "3M":  ("2y",  "1d",  pd.DateOffset(months=3)),   # Last 3 months from daily data
        "6M":  ("2y",  "1d",  pd.DateOffset(months=6)),   # Last 6 months from daily data
        "1Y":  ("2y",  "1d",  pd.DateOffset(years=1)),    # Last 1 year from daily data
        "3Y":  ("20y", "1wk", pd.DateOffset(years=3)),    # Last 3 years from weekly data
        "5Y":  ("20y", "1wk", pd.DateOffset(years=5)),    # Last 5 years from weekly data
        "10Y": ("20y", "1wk", pd.DateOffset(years=10)),   # Last 10 years from weekly data
        "20Y": ("20y", "1wk", pd.DateOffset(years=20)),   # Full 20 years from weekly data
    }
    src_period, interval, offset = period_map[period]  # Unpack the config for the selected period

    # Fetch price history from yfinance (or NSE fallback)
    hist = fetch_asset_history(ticker, market, src_period, interval, usd_inr)
    if hist.empty:
        return go.Figure()  # Return empty chart if no data available

    # Slice to only the selected time window
    cutoff = hist.index.max() - offset      # Calculate the start date
    hist   = hist.loc[hist.index >= cutoff].copy()  # Keep only data after the cutoff

    # Extract the Close price column (handles both Series and DataFrame formats)
    _c = hist["Close"]
    close = (_c.iloc[:, 0] if isinstance(_c, pd.DataFrame) else _c).dropna()

    # ── Set up the subplot layout (1 or 2 rows) ─────────────────────────────
    has_sub = subchart != "None"                # Whether to show RSI or MACD sub-chart
    rows   = 2 if has_sub else 1                # Number of chart rows
    heights = [0.75, 0.25] if has_sub else [1.0]  # Row height ratios (price gets 75%)
    specs  = [[{"secondary_y": True}]] + ([[{"secondary_y": False}]] if has_sub else [])

    fig = make_subplots(
        rows=rows, cols=1,
        shared_xaxes=True,       # Share the x-axis (time) between rows
        row_heights=heights,
        vertical_spacing=0.04,   # Small gap between price and indicator panels
        specs=specs,
    )

    # ── Volume bars (translucent, on secondary y-axis) ───────────────────────
    if "Volume" in hist.columns:
        vol = hist["Volume"]
        if isinstance(vol, pd.DataFrame):
            vol = vol.iloc[:, 0]  # Handle MultiIndex from batch download
        fig.add_trace(
            go.Bar(x=vol.index, y=vol.values, name="Volume",
                   marker_color="rgba(148,163,184,0.15)", showlegend=False),
            row=1, col=1, secondary_y=True,  # Plot on secondary y-axis so scale doesn't distort prices
        )

    # ── Main price line ──────────────────────────────────────────────────────
    color = "#f5b800"  # Cyan accent color for the price line
    fig.add_trace(
        go.Scatter(x=close.index, y=close.values, name=name,
                   line=dict(color=color, width=1.8)),
        row=1, col=1, secondary_y=False,
    )

    # ── Technical overlays (SMA, EMA, Bollinger) ─────────────────────────────
    # Map overlay names to their calculation functions
    overlay_fns = {
        "SMA 20":  lambda: compute_sma(close, 20),    # 20-period simple moving average
        "SMA 50":  lambda: compute_sma(close, 50),    # 50-period simple moving average
        "SMA 200": lambda: compute_sma(close, 200),   # 200-period simple moving average
        "EMA 12":  lambda: compute_ema(close, 12),    # 12-period exponential moving average
    }
    # Color for each overlay line
    overlay_colors = {"SMA 20": "#ffd700", "SMA 50": "#00e676", "SMA 200": "#f44336", "EMA 12": "#b388ff"}

    for key in overlays:
        if key in overlay_fns:
            s = overlay_fns[key]()  # Compute the moving average series
            fig.add_trace(
                go.Scatter(x=s.index, y=s.values, name=key,
                           line=dict(color=overlay_colors[key], width=1.2, dash="dot")),
                row=1, col=1, secondary_y=False,
            )
        elif key == "Bollinger Bands":
            # Bollinger: 20-period mean ± 2 standard deviations
            upper, _, lower = compute_bollinger(close, 20, 2.0)
            fig.add_trace(
                go.Scatter(x=upper.index, y=upper.values, name="BB Upper",
                           line=dict(color="rgba(148,163,184,0.5)", width=1, dash="dot")),
                row=1, col=1,
            )
            fig.add_trace(
                go.Scatter(x=lower.index, y=lower.values, name="BB Lower",
                           line=dict(color="rgba(148,163,184,0.5)", width=1, dash="dot"),
                           fill="tonexty", fillcolor="rgba(148,163,184,0.05)"),  # Shaded band between upper and lower
                row=1, col=1,
            )

    # ── Sub-chart: RSI ───────────────────────────────────────────────────────
    if subchart == "RSI":
        rsi = compute_rsi(close)  # 14-day RSI
        fig.add_trace(
            go.Scatter(x=rsi.index, y=rsi.values, name="RSI (14)",
                       line=dict(color="#f5b800", width=1.4)),
            row=2, col=1,
        )
        # Overbought (70) and oversold (30) reference lines
        fig.add_hline(y=70, line_color="rgba(244,67,54,0.4)", line_dash="dot", row=2, col=1)
        fig.add_hline(y=30, line_color="rgba(0,230,118,0.4)", line_dash="dot", row=2, col=1)
        fig.update_yaxes(range=[0, 100], row=2, col=1)  # RSI always 0-100

    # ── Sub-chart: MACD ──────────────────────────────────────────────────────
    elif subchart == "MACD":
        macd, sig, hist_bar = compute_macd(close)  # MACD line, signal line, histogram
        # Color histogram bars: green when positive, red when negative
        colors = ["rgba(0,230,118,0.6)" if v >= 0 else "rgba(244,67,54,0.6)" for v in hist_bar.fillna(0)]
        fig.add_trace(
            go.Bar(x=hist_bar.index, y=hist_bar.values, name="Histogram",
                   marker_color=colors, showlegend=False),
            row=2, col=1,
        )
        fig.add_trace(
            go.Scatter(x=macd.index, y=macd.values, name="MACD",
                       line=dict(color="#f5b800", width=1.3)),
            row=2, col=1,
        )
        fig.add_trace(
            go.Scatter(x=sig.index, y=sig.values, name="Signal",
                       line=dict(color="#ffd700", width=1.3)),
            row=2, col=1,
        )

    # ── Final layout configuration ───────────────────────────────────────────
    fig.update_layout(
        **PLOTLY_THEME,
        height=580 if not has_sub else 680,       # Taller when showing sub-chart
        margin=_MARGIN,
        xaxis_rangeslider_visible=False,           # Hide Plotly's default range slider
        legend=dict(orientation="h", y=1.02, x=0, font=dict(size=11)),  # Horizontal legend above chart
    )
    fig.update_yaxes(showgrid=True, gridcolor=GRID_COLOR, zeroline=False)  # Subtle grid lines
    fig.update_xaxes(showgrid=False)               # No vertical grid lines (cleaner look)
    fig.update_yaxes(showticklabels=False, row=1, col=1, secondary_y=True)  # Hide volume axis labels
    return fig


def render(*, filtered, metrics, df_daily, df_weekly, market, usd_inr, profile, rfr, **_):
    """Render the Price History tab: interactive candlestick/line chart with
    SMA/EMA/Bollinger overlays and RSI/MACD sub-charts."""

    # ── Asset and period selectors ────────────────────────────────────────────
    col_asset, col_period = st.columns([2, 1])
    asset_sel  = col_asset.selectbox("Asset", asset_options(metrics), label_visibility="collapsed")
    period_sel = col_period.selectbox(
        "Period",
        ["1W","1M","3M","6M","1Y","3Y","5Y","10Y","20Y"],
        index=4,  # Default to 1Y
        label_visibility="collapsed",
    )
    sel_ticker = ticker_from(asset_sel)  # Extract ticker symbol from selection
    sel_name   = name_from(asset_sel)    # Extract display name from selection

    # ── Overlay and sub-chart controls ────────────────────────────────────────
    ov_col1, ov_col2 = st.columns([3, 1])
    with ov_col1:
        overlays_sel = st.multiselect(
            "Overlays",
            ["SMA 20", "SMA 50", "SMA 200", "EMA 12", "Bollinger Bands"],
            default=[],
            label_visibility="collapsed",
        )
    with ov_col2:
        subchart_sel = st.radio(
            "Sub-chart", ["None", "RSI", "MACD"],
            horizontal=True, label_visibility="collapsed",
        )

    # ── Annotation bar (period return, peak, trough, drawdown) ────────────────
    hist_ann = fetch_asset_history(
        sel_ticker, market,
        "2y"  if period_sel in ["1W","1M","3M","6M","1Y"] else "20y",  # Choose data source
        "1d"  if period_sel in ["1W","1M","3M","6M","1Y"] else "1wk",  # Daily or weekly
        usd_inr,
    )
    if not hist_ann.empty and "Close" in hist_ann:
        # Extract close prices as a clean Series
        _ac = hist_ann["Close"]
        ann_prices = (_ac.iloc[:,0] if isinstance(_ac, pd.DataFrame) else _ac).dropna()
        ann_prices.index = pd.to_datetime(ann_prices.index)

        # Map period to DateOffset for slicing
        offset_map = {
            "1W": pd.DateOffset(weeks=1), "1M": pd.DateOffset(months=1),
            "3M": pd.DateOffset(months=3), "6M": pd.DateOffset(months=6),
            "1Y": pd.DateOffset(years=1),  "3Y": pd.DateOffset(years=3),
            "5Y": pd.DateOffset(years=5),  "10Y": pd.DateOffset(years=10),
            "20Y": pd.DateOffset(years=20),
        }
        cutoff = ann_prices.index.max() - offset_map[period_sel]  # Start date for the period
        sl = ann_prices[ann_prices.index >= cutoff]                # Slice to the selected period

        if not sl.empty:
            p_ret   = get_return(ann_prices, offset_map[period_sel])  # Period return %
            p_peak  = float(sl.max())                                  # Highest price in period
            p_low   = float(sl.min())                                  # Lowest price in period
            p_mdd   = get_max_drawdown(sl)                             # Max drawdown in period
            p_color = chg_color(p_ret)                                 # Green if positive, red if negative

            # Display the annotation bar with key stats
            st.markdown(
                f'<div class="metric-band" style="border-left-color:{p_color};margin-bottom:10px;">'
                f'<span class="t-mono" style="font-size:0.82rem;color:{p_color};">'
                f'{period_sel}: <b>{fmt_pct(p_ret)}</b></span>'
                f'&nbsp;&nbsp;&nbsp;<span class="t-mono t-muted" style="font-size:0.78rem;">'
                f'Peak ₹{p_peak:,.2f} · Trough ₹{p_low:,.2f} · Drawdown {fmt_num(p_mdd)}%'
                f'</span></div>', unsafe_allow_html=True,
            )

    # ── Render the main price chart ──────────────────────────────────────────
    fig_price = _price_chart(sel_ticker, sel_name, market, period_sel, usd_inr,
                              overlays_sel, subchart_sel)
    st.plotly_chart(fig_price, use_container_width=True, config={"displayModeBar": True})  # Show toolbar for zoom/pan
