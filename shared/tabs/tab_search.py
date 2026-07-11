"""Tab 2 — Search & Recommend: single ticker intel card + radar compare."""
from __future__ import annotations  # Allow modern type hints

import html   # For escaping dynamic content in HTML (XSS prevention)
import re     # For cleaning special characters from yfinance names

import pandas as pd              # DataFrame operations
import plotly.graph_objects as go  # Low-level Plotly charting
import streamlit as st           # Streamlit UI framework

# Import the AI 3-statement analysis function
from shared.ai_analysis import get_financial_analysis

# Import financial calculation functions
from shared.calculations import (
    annualised_mean_return,   # mean(weekly_returns) × 52
    annualised_volatility,    # σ × √periods_per_year
    compute_rsi,              # 14-day Relative Strength Index
    compute_sma,              # Simple Moving Average
    get_52w_stats,            # 52-week high/low and distance from high
    get_max_drawdown,         # Deepest peak-to-trough decline
    get_return,               # Calendar-accurate return over a DateOffset
    sharpe_ratio,             # (ann_mean_return - rfr) / volatility
)

# Import data fetcher and display helpers
from shared.data_loader import fetch_ticker_history
from shared.tabs._helpers import arrow, chg_color, fmt_num, fmt_pct, safe_ticker
from shared.theme import GRID_COLOR, PLOTLY_THEME


def render(*, filtered, metrics, df_daily, df_weekly, market, usd_inr, profile, rfr, **_):
    """Render the Search & Recommend tab: single-ticker intelligence card (returns,
    volatility, Sharpe, RSI, 52W stats, quantitative verdict, AI 3-statement
    analysis) and a multi-ticker radar comparison mode."""

    # Section header
    st.markdown(
        '<div style="font-size:0.7rem;font-weight:700;letter-spacing:0.12em;'
        'text-transform:uppercase;color:var(--text-muted);margin-bottom:12px;">'
        'Search any ticker for a full Intelligence Report</div>',
        unsafe_allow_html=True,
    )

    # Toggle between single analysis and comparison modes
    mode = st.radio("Mode", ["Single Analysis", "Compare (2–4 tickers)"], horizontal=True)

    # ══════════════════════════════════════════════════════════════════════════
    # MODE 1: Single Ticker Analysis
    # ══════════════════════════════════════════════════════════════════════════
    if mode == "Single Analysis":
        # Text input for the ticker symbol
        query = st.text_input("Ticker", placeholder="RELIANCE.NS  ·  AAPL  ·  TCS  ·  ^NSEI",
                              label_visibility="collapsed")
        if query:
            ticker = safe_ticker(query, market)  # Sanitise and normalise the ticker
            if not ticker:
                st.warning("Enter a valid ticker symbol.")
            else:
                # Fetch 2-year daily and 20-year weekly price history
                with st.spinner(f"Fetching intelligence for {ticker}…"):
                    hist2, hist20 = fetch_ticker_history(ticker, market, usd_inr)

                def _ts(df: pd.DataFrame, col: str) -> pd.Series:
                    """Extract a clean price Series from a DataFrame column.
                    Handles both single-column and multi-column (batch download) formats."""
                    if col not in df:
                        return pd.Series(dtype=float)
                    c = df[col]
                    return (c.iloc[:, 0] if isinstance(c, pd.DataFrame) else c).dropna()

                # Get clean close-price Series from both timeframes
                prices_w = _ts(hist20, "Close")  # Weekly prices (20 years)
                prices_d = _ts(hist2,  "Close")  # Daily prices (2 years)
                prices_d.index = pd.to_datetime(prices_d.index)  # Ensure datetime index

                # ── Calculate all metrics ─────────────────────────────────────
                ret_1y     = get_return(prices_w, pd.DateOffset(years=1))     # 1-year return %
                ret_1m     = get_return(prices_d, pd.DateOffset(months=1))    # 1-month return %
                ret_3m     = get_return(prices_d, pd.DateOffset(months=3))    # 3-month return %
                ret_3y     = get_return(prices_w, pd.DateOffset(years=3))     # 3-year return %
                vol        = annualised_volatility(prices_w, 52)              # Long-term vol (weekly × √52)
                vol_1m     = annualised_volatility(prices_d, 252)             # Short-term vol (daily × √252)
                ann_mean_w = annualised_mean_return(prices_w, 52)             # Annualised mean weekly return
                shp        = sharpe_ratio(ann_mean_w, vol, rfr=rfr)          # Sharpe ratio
                mdd        = get_max_drawdown(prices_w)                       # Max drawdown over 20Y
                w52        = get_52w_stats(prices_d if not prices_d.empty else prices_w)  # 52-week high/low
                cur_p      = float(prices_d.iloc[-1]) if not prices_d.empty else None     # Latest price

                # ── RSI calculation (need at least 14 data points) ────────────
                rsi_val = None
                if not prices_d.empty and len(prices_d) >= 14:
                    rsi_series = compute_rsi(prices_d)
                    rsi_val = float(rsi_series.dropna().iloc[-1]) if not rsi_series.dropna().empty else None

                # ── Trend signal: price vs 50-day SMA ─────────────────────────
                trend_sig = "—"
                if not prices_d.empty and len(prices_d) >= 50:
                    sma50 = compute_sma(prices_d, 50)
                    if not sma50.dropna().empty and cur_p:
                        trend_sig = "↑ Above 50-day MA" if cur_p > float(sma50.dropna().iloc[-1]) else "↓ Below 50-day MA"

                # ── Quantitative signal scoring ───────────────────────────────
                # Thresholds are illustrative heuristics, NOT empirically backtested.
                # Educational only — not investment advice.
                signals = []
                if shp is not None:     signals.append(2 if shp > 1.0 else 1 if shp > 0.5 else -1)      # Sharpe signal
                if ret_1y is not None:  signals.append(2 if ret_1y > 15 else 1 if ret_1y > 5 else -1)    # Return signal
                if rsi_val is not None: signals.append(1 if rsi_val < 40 else -1 if rsi_val > 70 else 0) # RSI signal
                if w52["vs_high_pct"] is not None:
                    signals.append(1 if -10 < w52["vs_high_pct"] < -2 else 0)  # Near-high breakout signal

                score = sum(signals)  # Total score determines the verdict

                # Map score to a verdict label, CSS class, and explanation
                if score >= 4:
                    verd, vcls, vreason = "📈 Strong Signal", "verdict-strong", f"Sharpe {fmt_num(shp)}, {fmt_pct(ret_1y)} 1Y return, RSI neutral-to-oversold, near 52W high breakout zone."
                elif score >= 2:
                    verd, vcls, vreason = "📊 Moderate Signal", "verdict-moderate", f"Good risk-adjusted profile (Sharpe {fmt_num(shp)}). Further research recommended."
                elif score >= 0:
                    verd, vcls, vreason = "⚠️ Weak Signal", "verdict-weak", "Mixed signals. Monitor for Sharpe improvement before building a position."
                else:
                    verd, vcls, vreason = "🔍 Low Signal", "verdict-low", "Poor risk-adjusted metrics or overbought RSI. Quantitative signals are unfavourable."

                # ── Fetch display name and sector from yfinance ───────────────
                disp_name, disp_sector = ticker, "—"
                try:
                    import yfinance as yf
                    info = yf.Ticker(ticker).info
                    raw_name = info.get("longName") or info.get("shortName") or ticker
                    disp_name   = re.sub(r"[<>\"'&]", "", str(raw_name))[:48]  # Strip HTML-unsafe chars, truncate
                    disp_sector = re.sub(r"[<>\"'&]", "", str(info.get("sector", "—")))
                except Exception:
                    pass  # Use ticker as fallback name

                # Format the current price for display
                price_disp = f"₹{cur_p:,.2f}" if cur_p else "—"
                chg1d = get_return(prices_d, pd.DateOffset(days=1))  # 1-day change
                cc = chg_color(chg1d)  # Green/red color based on 1-day return

                # ── Render the Intelligence Card (3-column grid) ──────────────
                st.markdown(f"""
                <div class="intel-card">
                  <div class="intel-header">
                    <div>
                      <div class="intel-ticker">{html.escape(ticker)}</div>
                      <div class="intel-name">{html.escape(disp_name)} &nbsp;·&nbsp; {html.escape(disp_sector)}</div>
                    </div>
                    <div>
                      <div class="intel-price">{price_disp}</div>
                      <div style="color:{cc};font-family:'JetBrains Mono',monospace;font-size:0.9rem;text-align:right;">
                        {arrow(chg1d)} {fmt_pct(chg1d)} today
                      </div>
                    </div>
                  </div>
                  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px;">
                    <div>
                      <div class="intel-section-title">Returns</div>
                      <div class="intel-row"><span class="intel-row-label">1 Month</span><span class="intel-row-value" style="color:{chg_color(ret_1m)}">{fmt_pct(ret_1m)}</span></div>
                      <div class="intel-row"><span class="intel-row-label">3 Months</span><span class="intel-row-value" style="color:{chg_color(ret_3m)}">{fmt_pct(ret_3m)}</span></div>
                      <div class="intel-row"><span class="intel-row-label">1 Year</span><span class="intel-row-value" style="color:{chg_color(ret_1y)}">{fmt_pct(ret_1y)}</span></div>
                      <div class="intel-row"><span class="intel-row-label">3 Years</span><span class="intel-row-value" style="color:{chg_color(ret_3y)}">{fmt_pct(ret_3y)}</span></div>
                    </div>
                    <div>
                      <div class="intel-section-title">Risk Metrics</div>
                      <div class="intel-row"><span class="intel-row-label">Sharpe Ratio</span><span class="intel-row-value" style="color:{'var(--green)' if shp and shp>0.5 else 'var(--red)'}">{fmt_num(shp)}</span></div>
                      <div class="intel-row"><span class="intel-row-label">Vol (Long-term)</span><span class="intel-row-value">{fmt_num(vol)}%</span></div>
                      <div class="intel-row"><span class="intel-row-label">Vol 1M (Daily)</span><span class="intel-row-value">{fmt_num(vol_1m)}%</span></div>
                      <div class="intel-row"><span class="intel-row-label">Max Drawdown</span><span class="intel-row-value" style="color:var(--red)">{fmt_num(mdd)}%</span></div>
                    </div>
                    <div>
                      <div class="intel-section-title">Trend Signals</div>
                      <div class="intel-row"><span class="intel-row-label">52W High</span><span class="intel-row-value">₹{w52['high']:,.2f}</span></div>
                      <div class="intel-row"><span class="intel-row-label">52W Low</span><span class="intel-row-value">₹{w52['low']:,.2f}</span></div>
                      <div class="intel-row"><span class="intel-row-label">vs 52W High</span><span class="intel-row-value" style="color:{chg_color(w52['vs_high_pct'])}">{fmt_pct(w52['vs_high_pct'])}</span></div>
                      <div class="intel-row"><span class="intel-row-label">RSI (14d)</span><span class="intel-row-value" style="color:{'var(--green)' if rsi_val and rsi_val<40 else ('var(--red)' if rsi_val and rsi_val>70 else 'var(--text-primary)')}">{fmt_num(rsi_val, 1) if rsi_val else '—'}</span></div>
                      <div class="intel-row"><span class="intel-row-label">Trend</span><span class="intel-row-value">{trend_sig}</span></div>
                    </div>
                  </div>
                  <div class="verdict-card {vcls}">
                    <div class="verdict-label">Quantitative Signal</div>
                    <div class="verdict-text">{verd}</div>
                    <div class="verdict-reason">{vreason}</div>
                    <div class="verdict-disclaimer">⚠️ Quantitative signal only — not investment advice. Past performance does not guarantee future results. Consult a SEBI-registered advisor before investing.</div>
                  </div>
                </div>
                """, unsafe_allow_html=True)

                # ── Mini sparkline chart (last 252 trading days) ──────────────
                st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
                if not prices_d.empty:
                    fig_mini = go.Figure()
                    color = "#00e676" if (ret_1y or 0) >= 0 else "#f44336"  # Green if positive 1Y, red if negative
                    fig_mini.add_trace(go.Scatter(
                        x=prices_d.index[-252:], y=prices_d.values[-252:],  # Last ~1 year of daily data
                        line=dict(color=color, width=1.8),
                        fill="tozeroy",  # Fill area under the line
                        fillcolor=f"rgba({'0,230,118' if color=='#00e676' else '244,67,54'},0.07)",
                        name="1Y Price",
                    ))
                    fig_mini.update_layout(**PLOTLY_THEME, height=160, margin=dict(l=0, r=0, t=0, b=0),
                                           showlegend=False, xaxis_visible=False)
                    fig_mini.update_yaxes(showgrid=False, showticklabels=False)
                    st.plotly_chart(fig_mini, use_container_width=True, config={"displayModeBar": False})

                # ── AI 3-Statement Financial Analysis (Groq / Llama) ──────────
                st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
                with st.expander("🔬 Deep Financial Analysis — 3-Statement Breakdown (AI-powered)", expanded=False):
                    st.caption(
                        "Pulls the latest annual income statement, balance sheet, and cash flow statement, "
                        "then maps the 3 critical connections between them in plain English."
                    )
                    st.warning("⚠️ **AI-generated output.** This analysis is produced by Llama 3.3 70B (Groq) and may contain errors or hallucinations. It is not investment advice. Always verify figures independently before making any financial decision.", icon=None)
                    if st.button("Run Financial Analysis", key=f"ai_{ticker}"):
                        with st.spinner(f"Analysing {ticker} financials with Llama 3.3…"):
                            result = get_financial_analysis(ticker)

                        # Handle sentinel return values with user-friendly messages
                        if result == "__NO_KEY__":
                            st.warning("GROQ_API_KEY not found. Set it in `.streamlit/secrets.toml`: `GROQ_API_KEY = \"gsk_...\"`")
                        elif result == "__NO_DATA__":
                            st.info(f"No annual financial statements available for **{ticker}** via yfinance.")
                        elif result.startswith("__ERROR__"):
                            st.error(f"API error: {result[9:]}")  # Strip the sentinel prefix
                        else:
                            st.markdown(result)  # Display the AI analysis
                            st.caption("🤖 AI-generated by Llama 3.3 70B via Groq. Educational only — not investment advice. Verify all figures independently.")

    # ══════════════════════════════════════════════════════════════════════════
    # MODE 2: Multi-Ticker Radar Comparison
    # ══════════════════════════════════════════════════════════════════════════
    else:
        compare_input = st.text_input(
            "Enter 2–4 tickers separated by commas",
            placeholder="RELIANCE.NS, TCS.NS, INFY.NS",
            label_visibility="collapsed",
        )
        if compare_input:
            # Parse and sanitise each ticker
            parsed = [safe_ticker(t.strip(), market) for t in compare_input.split(",") if t.strip()]
            if len(parsed) > 4:
                st.warning(f"Showing first 4 of {len(parsed)} tickers.")
            raw_tickers = parsed[:4]  # Cap at 4 tickers

            if len(raw_tickers) < 2:
                st.warning("Enter at least 2 tickers separated by commas.")
            else:
                # ── Fetch metrics for each ticker ─────────────────────────────
                radar_data: dict = {}
                with st.spinner("Loading comparison data…"):
                    for tk in raw_tickers:
                        r1m_h, h = fetch_ticker_history(tk, market, usd_inr)  # 2Y daily + 20Y weekly

                        # Extract weekly close prices
                        _hc = h["Close"] if "Close" in h else None
                        p   = (_hc.iloc[:, 0] if isinstance(_hc, pd.DataFrame) else _hc).dropna() if _hc is not None else pd.Series(dtype=float)

                        # Extract daily close prices
                        _rc = r1m_h["Close"] if "Close" in r1m_h else None
                        p1m = (_rc.iloc[:, 0] if isinstance(_rc, pd.DataFrame) else _rc).dropna() if _rc is not None else pd.Series(dtype=float)

                        # Calculate all 5 radar dimensions
                        r1y  = get_return(p, pd.DateOffset(years=1))                    # 1Y return
                        r1m_v = get_return(p1m, pd.DateOffset(months=1))                # 1M momentum
                        vl   = annualised_volatility(p, 52)                              # Volatility
                        sp   = sharpe_ratio(annualised_mean_return(p, 52), vl, rfr=rfr) # Sharpe
                        w52v = get_52w_stats(p1m if not p1m.empty else p)                # 52W stats

                        radar_data[tk] = {
                            "1Y Return": r1y if r1y is not None else 0,
                            "Sharpe":    sp * 50 if sp is not None else 0,               # Scale Sharpe for radar
                            "Low Vol":   max(0, 100 - (vl if vl is not None else 50)),   # Invert: lower vol = higher score
                            "Momentum":  r1m_v if r1m_v is not None else 0,
                            "Value":     max(0, 100 + (w52v["vs_high_pct"] if w52v["vs_high_pct"] is not None else 0)),  # Closer to 52W high = higher
                        }

                if radar_data:
                    # ── Normalise each dimension to 0-100 across the compared tickers ─
                    cats = ["1Y Return", "Sharpe", "Low Vol", "Momentum", "Value"]
                    for cat in cats:
                        vals = [radar_data[tk][cat] for tk in raw_tickers]
                        mn, mx = min(vals), max(vals)
                        rng = mx - mn
                        for tk in raw_tickers:
                            # Scale to 0-100 (ties get 100 if all values are equal)
                            radar_data[tk][cat] = round((radar_data[tk][cat] - mn) / rng * 100 if rng > 0 else 100, 1)

                    # ── Build the radar (polar) chart ─────────────────────────
                    colors_palette = ["#f5b800", "#f5b800", "#00e676", "#b388ff"]  # One color per ticker
                    fig_r = go.Figure()
                    for i, tk in enumerate(raw_tickers):
                        # Close the polygon by repeating the first value at the end
                        vals = [radar_data[tk][c] for c in cats] + [radar_data[tk][cats[0]]]
                        fig_r.add_trace(go.Scatterpolar(
                            r=vals, theta=cats + [cats[0]],
                            fill="toself",
                            fillcolor=f"rgba{tuple(int(colors_palette[i][j:j+2],16) for j in (1,3,5))+(0.12,)}",
                            line=dict(color=colors_palette[i], width=2),
                            name=tk,
                        ))

                    # Apply layout and render
                    fig_r.update_layout(
                        **PLOTLY_THEME, height=420,
                        polar=dict(
                            bgcolor="#0d1526",
                            radialaxis=dict(visible=True, range=[0,100], gridcolor=GRID_COLOR, tickfont=dict(size=9)),
                            angularaxis=dict(gridcolor=GRID_COLOR, tickfont=dict(size=11)),
                        ),
                        title=dict(text="Multi-Asset Radar Comparison (normalised)", font=dict(size=13), x=0.5),
                        legend=dict(orientation="h", y=-0.1),
                    )
                    st.plotly_chart(fig_r, use_container_width=True, config={"displayModeBar": False})
                    st.caption("Each axis normalised across the compared assets. Higher = relatively better on that dimension.")
