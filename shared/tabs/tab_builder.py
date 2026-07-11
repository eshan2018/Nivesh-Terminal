"""Tab 1 — Portfolio Builder: recommender, What-If projector, goal calculator."""
from __future__ import annotations  # Allow modern type hints

import pandas as pd              # DataFrame operations
import plotly.graph_objects as go  # Low-level Plotly charting
import streamlit as st           # Streamlit UI framework

# Import financial helpers
from shared.calculations import fmt_inr, ret_color, sip_future_value_freq
from shared.tabs._helpers import _MARGIN, _PGRID     # Chart layout constants
from shared.theme import PLOTLY_THEME                 # Dark Plotly theme


def render(*, filtered, metrics, df_daily, df_weekly, market, usd_inr, profile, rfr, **_):
    """Render the Portfolio Builder tab: percentile-rank recommender, What-If projector
    with +-1 sigma cone, and goal reverse-calculator."""

    # ── Constants ─────────────────────────────────────────────────────────────
    # Map investment cycle names to their compounding frequency (periods per year)
    _CYCLE_FREQ = {"Daily": 252, "Weekly": 52, "Monthly": 12, "Quarterly": 4, "Yearly": 1, "Lump-sum": 0}

    # Benchmark rates for comparison (illustrative defaults — not live data)
    _RATES = {
        "india": {"savings": 0.035, "fd": 0.0725, "index": 0.12,  "inflation": 0.055},
        "us":    {"savings": 0.045, "fd": 0.0525, "index": 0.10,  "inflation": 0.035},
    }
    _IDX_LABEL = "Nifty 50" if market == "india" else "S&P 500"  # Index name for display
    rates = _RATES[market]  # Pick the rate set for this market

    # ── Investment profile inputs ─────────────────────────────────────────────
    st.markdown('<div class="intel-section-title">Your Investment Profile</div>', unsafe_allow_html=True)
    ip1, ip2, ip3 = st.columns(3)  # Three-column layout for input widgets
    inv_amount = ip1.number_input("Amount per period (₹)", min_value=100.0, value=10_000.0, step=500.0)  # How much to invest each cycle
    inv_cycle  = ip2.selectbox("Investment cycle", list(_CYCLE_FREQ.keys()), index=2)  # How often (default: Monthly)
    lock_in    = ip3.slider("Lock-in period (years)", 1, 30, 10)  # How many years to stay invested

    freq    = _CYCLE_FREQ[inv_cycle]                # Periods per year for selected cycle
    is_lump = inv_cycle == "Lump-sum"               # Whether this is a one-time investment
    total_invested = inv_amount if is_lump else inv_amount * freq * lock_in  # Total capital deployed

    # Show the total invested amount in a styled banner
    st.markdown(f"""
    <div class="metric-band" style="margin-bottom:18px;">
      <div class="m-label">Total Capital Deployed Over {lock_in} Years</div>
      <div class="m-value">{fmt_inr(total_invested)}</div>
      <div style="font-size:0.74rem;color:var(--text-muted);margin-top:3px;">
        {fmt_inr(inv_amount)} {'one-time lump sum' if is_lump else f'× {freq} periods / yr × {lock_in} yrs'}
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Percentile-rank composite recommender ────────────────────────────────
    st.markdown('<div class="intel-section-title">Top Picks for Your Profile &amp; Risk Level</div>',
                unsafe_allow_html=True)

    # Weights for each factor vary by risk profile
    # (Sharpe weight, 1Y return weight, 3Y return weight, low-volatility weight)
    _PROFILE_WEIGHTS = {
        "Conservative": (0.25, 0.15, 0.15, 0.45),  # Heavy on low volatility
        "Moderate":     (0.30, 0.20, 0.20, 0.30),
        "Balanced":     (0.35, 0.25, 0.25, 0.15),
        "Growth":       (0.35, 0.35, 0.20, 0.10),  # Heavy on returns
        "Aggressive":   (0.30, 0.45, 0.20, 0.05),  # Heaviest on returns
    }
    w_sh, w_1y, w_3y, w_mdd = _PROFILE_WEIGHTS.get(profile, (0.35, 0.25, 0.25, 0.15))

    def _pct_rank(series: pd.Series) -> pd.Series:
        """Convert raw values to percentile ranks (0-100). Higher = better."""
        return series.rank(pct=True, na_option="keep") * 100

    # Start with assets that have both Sharpe and 1Y return data
    recs = filtered.dropna(subset=["Sharpe", "1Y%"]).copy()
    if not recs.empty:
        # Rank each asset on 4 dimensions
        recs["_rk_sh"]  = _pct_rank(recs["Sharpe"])                    # Sharpe rank (higher = better)
        recs["_rk_1y"]  = _pct_rank(recs["1Y%"])                      # 1Y return rank
        recs["_rk_3y"]  = _pct_rank(recs["3Y%"].fillna(recs["1Y%"]))  # 3Y return rank (fallback to 1Y)

        # Low-volatility rank: lower vol → higher rank (hence negation)
        # Use direct column from recs (already filtered) — O(n) not O(n²)
        _mdd_col = recs["Volatility"]
        recs["_rk_mdd"] = _pct_rank(-_mdd_col.fillna(_mdd_col.median()))  # Negate so lower vol ranks higher

        # Composite score: weighted sum of all 4 ranks (0-100 scale)
        recs["Score"] = (
            w_sh  * recs["_rk_sh"].fillna(50) +   # Sharpe contribution
            w_1y  * recs["_rk_1y"].fillna(50) +   # 1Y return contribution
            w_3y  * recs["_rk_3y"].fillna(50) +   # 3Y return contribution
            w_mdd * recs["_rk_mdd"].fillna(50)     # Low-vol contribution
        ).round(1)
        recs = recs.drop(columns=["_rk_sh", "_rk_1y", "_rk_3y", "_rk_mdd"])  # Clean up temp columns

    # Show the top 10 assets by composite score
    recs = recs.sort_values("Score", ascending=False).head(10).reset_index(drop=True)
    recs.index = range(1, len(recs) + 1)  # 1-based index for display

    # Build the display table with star-rated Sharpe
    rec_disp = recs[["Ticker", "Name", "Sector", "Type", "1Y%", "3Y%", "Sharpe", "Volatility", "Score"]].copy()
    rec_disp["Sharpe ★  (score)"] = rec_disp["Sharpe"].apply(
        lambda v: (f"★★★  {v:.2f}" if v >= 1.5 else f"★★    {v:.2f}" if v >= 0.5 else
                   f"★      {v:.2f}" if v >= 0 else f"✕       {v:.2f}") if pd.notna(v) else "—"
    )
    rec_disp = rec_disp.drop(columns=["Sharpe"])  # Remove raw Sharpe (replaced by star version)

    # Render the recommendations table
    st.dataframe(
        rec_disp.style
            .map(ret_color, subset=["1Y%", "3Y%"])  # Color returns green/red
            .format({"1Y%": "{:+.2f}%", "3Y%": "{:+.2f}%", "Volatility": "{:.2f}%", "Score": "{:.1f}"}, na_rep="—")
            .set_properties(**{"background-color": "#0d1526", "color": "#f0f6ff"}),
        use_container_width=True, height=310,
    )
    # Show scoring methodology as a caption
    st.caption(
        f"Profile: **{profile}** · Score = percentile-rank composite "
        f"(Sharpe {w_sh*100:.0f}% + 1Y Return {w_1y*100:.0f}% + 3Y Return {w_3y*100:.0f}% + Low-Vol {w_mdd*100:.0f}%) "
        f"· 100 = top of universe · ★★★ ≥1.5  ·  ★★ 0.5–1.49  ·  ★ 0–0.49  ·  ✕ negative"
    )

    # ── What-If projector ─────────────────────────────────────────────────────
    st.markdown('<div class="intel-section-title" style="margin-top:18px;">What-If Projector — compare every scenario</div>',
                unsafe_allow_html=True)

    # Build dropdown options from the top 10 recommended tickers
    rec_opts = [f"{r.Ticker} — {r.Name}" for r in recs.itertuples()]
    wi_c1, wi_c2, wi_c3 = st.columns([2, 1, 1])
    wi_sel    = wi_c1.selectbox("Analyse ticker:", rec_opts, label_visibility="collapsed")
    wi_ticker = wi_sel.split(" — ")[0]  # Extract just the ticker symbol

    # Get historical returns for the selected ticker
    ticker_row   = recs[recs["Ticker"] == wi_ticker]

    # 1Y% is already a 1-year return = 1-year CAGR (no conversion needed)
    hist_cagr_1y = float(ticker_row["1Y%"].iloc[0]) / 100 if not ticker_row.empty and pd.notna(ticker_row["1Y%"].iloc[0]) else rates["index"]

    # 3Y% is a TOTAL 3-year return — must convert to annualised CAGR: (1 + r)^(1/3) - 1
    if not ticker_row.empty and pd.notna(ticker_row["3Y%"].iloc[0]):
        total_3y     = float(ticker_row["3Y%"].iloc[0]) / 100
        hist_cagr_3y = (1 + total_3y) ** (1 / 3) - 1  # Annualise the 3Y total return
    else:
        hist_cagr_3y = hist_cagr_1y

    # Cap individual CAGRs at 60% to prevent freak 1-year outliers distorting long-term projections
    hist_cagr_1y = min(hist_cagr_1y, 0.60)
    hist_cagr_3y = min(hist_cagr_3y, 0.60)

    # Blend 1Y and 3Y annualised CAGR — 3Y gets more weight as it's more representative
    ticker_cagr  = 0.4 * hist_cagr_1y + 0.6 * hist_cagr_3y

    # Show the blended CAGR and inflation rate
    wi_c2.metric("Ticker Blended CAGR", f"{ticker_cagr*100:.1f}% / yr")
    wi_c3.metric("Inflation Rate", f"{rates['inflation']*100:.1f}% / yr")

    # ── Store selected ticker in session state for cross-tab sharing ─────────
    # The Risk vs Return tab reads these to highlight this ticker on its scatter plot
    _tk_row = filtered[filtered["Ticker"] == wi_ticker]
    if not _tk_row.empty:
        st.session_state["_wi_ticker_rv"] = wi_ticker
        st.session_state["_wi_ret_rv"]    = _tk_row["1Y%"].iloc[0] if pd.notna(_tk_row["1Y%"].iloc[0]) else None
        st.session_state["_wi_vol_rv"]    = _tk_row["Volatility"].iloc[0] if pd.notna(_tk_row["Volatility"].iloc[0]) else None

    # ── Build projection lines ────────────────────────────────────────────────
    years_range    = list(range(0, lock_in + 1))  # [0, 1, 2, ..., lock_in]
    # Cumulative capital invested at each year (no growth)
    cumulative     = [inv_amount if is_lump else inv_amount * freq * y for y in years_range]
    # Inflation-adjusted capital (what your invested amount would need to be worth to maintain purchasing power)
    inflation_line = [c * (1 + rates["inflation"]) ** y for y, c in enumerate(cumulative)]

    def _fv(rate: float) -> list[float]:
        """Calculate future value at each year for a given annual growth rate."""
        if is_lump:
            # Lump sum: simple compound growth
            return [inv_amount * (1 + rate) ** y for y in years_range]
        # SIP: use the annuity-due formula at the given frequency
        return [sip_future_value_freq(inv_amount, rate, y, freq) if y > 0 else 0.0 for y in years_range]

    # ── Build the comparison chart ────────────────────────────────────────────
    fig_wi = go.Figure()

    # Inflation break-even line (red dotted)
    fig_wi.add_trace(go.Scatter(x=years_range, y=inflation_line,
        name=f"Inflation break-even ({rates['inflation']*100:.1f}%)",
        line=dict(color="rgba(244,67,54,0.55)", width=1.3, dash="dot")))

    # Total invested line (grey dotted) with red-shaded area below inflation
    fig_wi.add_trace(go.Scatter(x=years_range, y=cumulative,
        name="Total Invested (no growth)",
        line=dict(color="rgba(148,163,184,0.4)", width=1.1, dash="dot"),
        fill="tonexty", fillcolor="rgba(244,67,54,0.05)"))  # Light red fill = inflation erosion zone

    # Add lines for each scenario: selected ticker, index, FD, savings
    for vals, name, color, dash, width in [
        (_fv(ticker_cagr),     f"📈 {wi_ticker} ({ticker_cagr*100:.1f}%)",         "#f5b800", "solid",   2.6),
        (_fv(rates["index"]),  f"📊 {_IDX_LABEL} ({rates['index']*100:.0f}%)",      "#00e676", "dash",    1.8),
        (_fv(rates["fd"]),     f"🏦 Fixed Deposit ({rates['fd']*100:.2f}%)",         "#ffd700", "dot",     1.6),
        (_fv(rates["savings"]),f"💰 Savings Acct ({rates['savings']*100:.1f}%)",     "#b388ff", "dashdot", 1.4),
    ]:
        fig_wi.add_trace(go.Scatter(x=years_range, y=vals, name=name,
                                    line=dict(color=color, width=width, dash=dash)))

    # ── ±1σ volatility cone (shaded uncertainty band) ─────────────────────────
    _tk_vol_row = filtered[filtered["Ticker"] == wi_ticker]
    _vol_ann = float(_tk_vol_row["Volatility"].iloc[0]) / 100 if not _tk_vol_row.empty and pd.notna(_tk_vol_row["Volatility"].iloc[0]) else None
    if _vol_ann and _vol_ann > 0:
        upper_vals = _fv(ticker_cagr + _vol_ann)                    # Optimistic: CAGR + 1 std dev
        lower_vals = _fv(max(ticker_cagr - _vol_ann, -0.99))       # Pessimistic: CAGR - 1 std dev (floor at -99%)
        # Upper boundary (invisible line — just for the fill anchor)
        fig_wi.add_trace(go.Scatter(x=years_range, y=upper_vals,
            line=dict(color="rgba(0,212,255,0.0)", width=0), showlegend=False, hoverinfo="skip"))
        # Lower boundary with fill between upper and lower
        fig_wi.add_trace(go.Scatter(x=years_range, y=lower_vals,
            name=f"±1σ range (vol {_vol_ann*100:.0f}%)",
            line=dict(color="rgba(0,212,255,0.25)", width=1, dash="dot"),
            fill="tonexty", fillcolor="rgba(0,212,255,0.06)", hoverinfo="skip"))

    # ── Milestone annotations (2×, 5×, 10×) ──────────────────────────────────
    ticker_vals = _fv(ticker_cagr)
    for mult, lbl in [(2, "2×"), (5, "5×"), (10, "10×")]:
        target = cumulative[-1] * mult  # Target = multiple of total invested
        for yi, sv in enumerate(ticker_vals):
            if sv >= target:
                # Add an annotation arrow at the first year where the milestone is hit
                fig_wi.add_annotation(x=yi, y=sv, text=lbl,
                    font=dict(size=9, color="#f5b800"),
                    showarrow=True, arrowhead=2, arrowcolor="#f5b800", ay=-28, ax=0)
                break  # Only mark the first crossing

    # Apply theme and render
    fig_wi.update_layout(**PLOTLY_THEME, height=400, margin=_MARGIN,
        xaxis_title="Year", yaxis_title="Future Value (₹)",
        legend=dict(orientation="h", y=-0.28, x=0, font=dict(size=10)))
    fig_wi.update_xaxes(**_PGRID)
    fig_wi.update_yaxes(**_PGRID)
    st.plotly_chart(fig_wi, use_container_width=True, config={"displayModeBar": False})

    # ── Summary table: final values for all scenarios ─────────────────────────
    final = {
        f"{wi_ticker} (historical)":  ticker_vals[-1],           # Selected ticker's projected value
        f"{_IDX_LABEL}":              _fv(rates["index"])[-1],   # Index fund
        "Fixed Deposit":              _fv(rates["fd"])[-1],      # Bank FD
        "Savings Account":            _fv(rates["savings"])[-1], # Savings account
        "Inflation break-even":       inflation_line[-1],        # Minimum needed to beat inflation
        "Total Invested (no growth)": cumulative[-1],            # Raw capital with zero growth
    }
    base = cumulative[-1]  # Total capital invested (denominator for return calculation)
    summary_df = pd.DataFrame([
        {
            "Scenario": k,
            "Final Value": fmt_inr(v),
            "Gain over Invested": fmt_inr(v - base),
            "Total Return": f"{((v/base-1)*100):.1f}%" if base > 0 else "—",
            "Beats Inflation?": "✅ Yes" if v > inflation_line[-1] else "❌ No",
        }
        for k, v in final.items()
    ])
    summary_df.index = range(1, len(summary_df) + 1)
    st.dataframe(summary_df, use_container_width=True)

    # Methodology note
    st.caption(
        f"{inv_cycle} SIP of {fmt_inr(inv_amount)} · {lock_in}Y lock-in · "
        f"Inflation rate {rates['inflation']*100:.1f}% p.a. · "
        "Shaded cone = ±1σ volatility range around the selected ticker's blended CAGR. "
        "Rates are historical averages — past performance does not guarantee future results."
    )

    # ── Goal reverse calculator ───────────────────────────────────────────────
    st.markdown('<div class="intel-section-title" style="margin-top:14px;">Goal Calculator — How much do I need to invest?</div>',
                unsafe_allow_html=True)

    gc1, gc2, gc3 = st.columns(3)
    target_corpus = gc1.number_input("Target corpus (₹)", min_value=0.0, value=10_000_000.0, step=500_000.0)  # Desired final amount
    goal_years    = gc2.slider("In how many years?", 1, 30, lock_in)  # Investment horizon
    goal_rate_pct = gc3.number_input(
        "Expected CAGR %", min_value=1.0, max_value=80.0,
        value=max(1.0, min(80.0, round(ticker_cagr * 100, 1))),  # Default from selected ticker's CAGR
        step=0.5,
    )
    goal_rate = goal_rate_pct / 100  # Convert percentage to decimal

    # Reverse-engineer the required periodic investment using the annuity-due formula
    if goal_rate > 0 and freq > 0:
        r_period = (1 + goal_rate) ** (1 / freq) - 1   # Convert annual rate to per-period rate
        n        = goal_years * freq                     # Total number of contribution periods
        # Annuity-due factor: accounts for beginning-of-period contributions
        ann_fac  = ((1 + r_period) ** n - 1) / r_period * (1 + r_period) if r_period > 0 else n
        req_per_period = target_corpus / ann_fac if ann_fac > 0 else None  # Required amount per period
    elif is_lump:
        # For lump sum: just discount the target back to present value
        req_per_period = target_corpus / (1 + goal_rate) ** goal_years
    else:
        req_per_period = None  # Cannot calculate (edge case)

    # Display the results as three metric cards
    m1, m2, m3 = st.columns(3)
    m1.metric(f"Required {inv_cycle} Investment", fmt_inr(req_per_period))
    m2.metric("Total You'll Invest", fmt_inr(req_per_period * freq * goal_years if req_per_period and not is_lump else req_per_period))
    m3.metric("Wealth Created (gain)", fmt_inr(target_corpus - (req_per_period * freq * goal_years if req_per_period and not is_lump else (req_per_period or 0))))
