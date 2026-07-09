# ================================================================
# NIVESH TERMINAL — LANDING PAGE
# ================================================================
# This is the main entry point for the Streamlit app.
# It renders the home/landing page with:
#   - Hero section (title + tagline)
#   - Live marquee ticker bar (12 global indices)
#   - Market selection cards (India + US)
#   - Today's Intelligence panel (top gainer, biggest decline, breadth, sentiment)
#   - Feature showcase, how-it-works steps, why-nivesh section
#   - Footer with disclaimer
# ================================================================

import html as _html          # For escaping dynamic content in HTML (XSS prevention)
import streamlit as st        # Streamlit UI framework
from datetime import datetime  # For current timestamp display

from shared import IST as _IST                        # Indian Standard Time timezone
from shared.data_loader import get_live_quotes, get_usd_inr  # Live market data fetchers
from shared.theme import inject_theme                  # CSS design system injection

# ── Page configuration (must be the first Streamlit call) ─────────────────────
st.set_page_config(
    page_title="Nivesh Terminal — Wealth Intelligence",  # Browser tab title
    page_icon="📈",                                     # Browser tab icon
    layout="wide",                                       # Use full screen width
    initial_sidebar_state="collapsed",                  # Hide sidebar on home page
)

# Inject the full CSS design system and hide the sidebar completely on home page
inject_theme(hide_sidebar=True)


# ── EXPANDED LIVE PULSE (12 global indices + USD/INR) ─────────────────────────
@st.cache_data(ttl=300, show_spinner=False)  # Cache for 5 minutes
def get_live_pulse():
    """Fetch live prices and daily changes for 12 global market indices.

    Returns a list of dicts (one per index) + the current USD/INR rate.
    Each dict has: label, price, chg (%), ticker.
    """
    usd_inr = get_usd_inr()  # Current USD/INR exchange rate

    # Define the indices to track: (ticker, display_name, market)
    pulse = (
        # India indices
        ("^NSEI",      "Nifty 50",       "india"),
        ("^BSESN",     "Sensex",         "india"),
        ("^NSEBANK",   "Bank Nifty",     "india"),
        ("^CNXIT",     "Nifty IT",       "india"),
        ("^CNXMIDCAP", "Nifty Midcap",   "india"),
        ("^CNXSC",     "Nifty Smallcap", "india"),
        # US indices
        ("^GSPC",    "S&P 500",      "us"),
        ("^IXIC",    "Nasdaq",       "us"),
        ("^DJI",     "Dow Jones",    "us"),
        ("^RUT",     "Russell 2000", "us"),
        ("^VIX",     "VIX",          "us"),
        ("^FTSE",    "FTSE 100",     "us"),
    )

    # Build the USD/INR row manually (it's not an index, just an FX rate)
    usd_row = {"label": "USD/INR", "price": usd_inr, "chg": 0.0, "ticker": "USDINR"}

    # Fetch live quotes for all indices and prepend the USD/INR row
    rows = [usd_row] + get_live_quotes(pulse, usd_inr)
    return rows, usd_inr


# Fetch the live pulse data (cached 5 min)
pulse_data, usd_inr = get_live_pulse()


# ── HERO SECTION ──────────────────────────────────────────────────────────────
now_str = datetime.now(_IST).strftime("%b %d, %Y · %H:%M IST")  # Current timestamp

st.markdown(f"""
<div class="hero">
  <div class="hero-badge a0">🇮🇳 Built for the Indian Global Investor</div>
  <div class="hero-title a1">NIVESH<br><span>TERMINAL</span></div>
  <div class="hero-tagline a2">
    Wealth Intelligence. Indian Roots. Global Vision.<br>
    A Bloomberg-grade platform tracking 220 assets across US &amp; Indian markets —
    free, open, and built for the next generation of Indian investors.
  </div>
  <div class="t-label a3" style="font-size:0.7rem;">{now_str}</div>
</div>
""", unsafe_allow_html=True)


# ── CSS MARQUEE TICKER BAR ───────────────────────────────────────────────────
# Scrolling horizontal ticker strip showing all 12 indices + USD/INR
if pulse_data:
    def _ticker_html(item: dict) -> str:
        """Generate HTML for a single ticker item in the marquee bar."""
        chg = item["chg"]  # Daily % change
        # Choose CSS class based on whether the asset is up, down, or flat
        cls = "t-item-up" if chg > 0 else ("t-item-down" if chg < 0 else "t-item-flat")
        arrow = "▲" if chg > 0 else ("▼" if chg < 0 else "—")  # Up/down/flat arrow
        return (
            f'<span class="t-item">'
            f'<span class="t-item-label">{item["label"]}</span>'
            f'<span class="t-item-price">{item["price"]:,.2f}</span>'
            f'<span class="{cls}">{arrow} {abs(chg):.2f}%</span>'
            f'</span>'
        )

    # Build the marquee HTML: all items concatenated
    items_html = "".join(_ticker_html(r) for r in pulse_data)

    # Duplicate the items for a seamless infinite loop (CSS animation scrolls through first half,
    # then jumps back — the duplicate creates visual continuity)
    st.markdown(
        f'<div class="marquee-wrap">'
        f'<div class="marquee-track">{items_html}{items_html}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

# Spacer between marquee and market selection cards
st.markdown("<div style='height:48px'></div>", unsafe_allow_html=True)


# ── MARKET SELECTION CARDS ───────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center;margin-bottom:36px;">
  <div class="section-sub">Choose Your Market</div>
  <div class="section-title">Two Markets. One Platform.</div>
  <p style="color:var(--text-muted);font-size:0.86rem;max-width:480px;margin:10px auto 0;line-height:1.65;">
    Select a market to enter the full intelligence dashboard — live prices,
    risk analysis, portfolio builder, and 20-year history.
  </p>
</div>
""", unsafe_allow_html=True)


def _idx(ticker: str) -> dict | None:
    """Look up a specific index from the pulse data by its ticker symbol."""
    for r in pulse_data:
        if r.get("ticker") == ticker:
            return r
    return None


def _card_row(label: str, ticker: str) -> str:
    """Generate HTML for one row inside a market card (index name + price + change).

    Uses html.escape() on the label to prevent XSS from untrusted data.
    """
    r = _idx(ticker)  # Look up the index data
    if not r:
        return ""  # Skip if index data not available
    chg = r["chg"]
    cls = "t-item-up" if chg > 0 else ("t-item-down" if chg < 0 else "t-item-flat")
    arrow = "▲" if chg > 0 else ("▼" if chg < 0 else "—")
    return (
        f'<div class="card-index-row">'
        f'<span class="card-index-name">{_html.escape(label)}</span>'
        f'<span class="card-index-price">{r["price"]:,.2f}</span>'
        f'<span class="card-index-chg {cls}">{arrow} {abs(chg):.2f}%</span>'
        f'</div>'
    )


# Build the index rows HTML for the India card
india_rows = (
    _card_row("Nifty 50",       "^NSEI") +
    _card_row("Sensex",         "^BSESN") +
    _card_row("Bank Nifty",     "^NSEBANK") +
    _card_row("Nifty IT",       "^CNXIT") +
    _card_row("Nifty Midcap",   "^CNXMIDCAP") +
    _card_row("Nifty Smallcap", "^CNXSC")
)

# Build the index rows HTML for the US card
us_rows = (
    _card_row("S&P 500",      "^GSPC") +
    _card_row("Nasdaq",       "^IXIC") +
    _card_row("Dow Jones",    "^DJI") +
    _card_row("Russell 2000", "^RUT") +
    _card_row("VIX",          "^VIX") +
    _card_row("FTSE 100",     "^FTSE")
)

# Render the two market cards side by side with a tiny gap column in between
col_india, col_gap, col_us = st.columns([1, 0.06, 1])

with col_india:
    # India market card: flag, title, live indices, stats, button
    st.markdown(f"""
    <div class="market-card">
      <div class="market-card-flag">🇮🇳</div>
      <div class="market-card-title">Indian Market</div>
      <div class="market-card-sub">NSE · BSE · Nifty 100</div>
      <div style="margin-bottom:18px;">{india_rows}</div>
      <div class="market-card-stats">
        <div class="stat-item"><div class="stat-num">100</div><div class="stat-lbl">Nifty 100</div></div>
        <div class="stat-item"><div class="stat-num">10</div><div class="stat-lbl">Top ETFs</div></div>
        <div class="stat-item"><div class="stat-num">20Y</div><div class="stat-lbl">History</div></div>
      </div>
      <div style="color:var(--text-muted);font-size:0.7rem;">📲 Zerodha · Groww · Upstox</div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    # Navigation button — switches to the India dashboard page
    if st.button("🇮🇳  Enter Indian Market →", use_container_width=True, type="primary", key="india_btn"):
        st.switch_page("pages/1_india_market.py")

with col_us:
    # US market card: flag, title, live indices, stats, button
    st.markdown(f"""
    <div class="market-card">
      <div class="market-card-flag">🇺🇸</div>
      <div class="market-card-title">US Market</div>
      <div class="market-card-sub">NYSE · Nasdaq · S&amp;P 500</div>
      <div style="margin-bottom:18px;">{us_rows}</div>
      <div class="market-card-stats">
        <div class="stat-item"><div class="stat-num">100</div><div class="stat-lbl">US Stocks</div></div>
        <div class="stat-item"><div class="stat-num">10</div><div class="stat-lbl">Top ETFs</div></div>
        <div class="stat-item"><div class="stat-num">20Y</div><div class="stat-lbl">History</div></div>
      </div>
      <div style="color:var(--text-muted);font-size:0.7rem;">📲 INDmoney · Vested · Groww Global</div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    # Navigation button — switches to the US dashboard page
    if st.button("🇺🇸  Enter US Market →", use_container_width=True, type="primary", key="us_btn"):
        st.switch_page("pages/2_us_market.py")

# Visual divider between sections
st.markdown('<hr class="divider">', unsafe_allow_html=True)


# ── TODAY'S INTELLIGENCE ─────────────────────────────────────────────────────
# Filter out non-asset rows (USD/INR and VIX are informational, not tradeable)
asset_rows = [r for r in pulse_data if r.get("ticker") not in {"USDINR", "^VIX"}]

if asset_rows:
    # Find the best and worst performers today
    top_g  = max(asset_rows, key=lambda x: x["chg"])   # Top gainer
    top_l  = min(asset_rows, key=lambda x: x["chg"])   # Biggest decliner
    up_n   = sum(1 for r in asset_rows if r["chg"] > 0)  # Count of advancing indices
    dn_n   = sum(1 for r in asset_rows if r["chg"] < 0)  # Count of declining indices
    total  = len(asset_rows)
    breadth_pct = round(up_n / total * 100) if total else 0  # % of indices that are up

    # Determine overall market sentiment
    sentiment = "Bullish" if up_n > dn_n else ("Bearish" if dn_n > up_n else "Mixed")
    sent_color = "insight-chip-green" if sentiment == "Bullish" else ("insight-chip-red" if sentiment == "Bearish" else "")

    # Get VIX for the sentiment chip
    vix_row = _idx("^VIX")
    vix_str = f"VIX {vix_row['price']:.1f}" if vix_row else "VIX N/A"

    # Section header
    st.markdown("""
    <div style="text-align:center;margin-bottom:24px;">
      <div class="section-sub">Live Intelligence</div>
      <div class="section-title">Today's Market Pulse</div>
    </div>
    """, unsafe_allow_html=True)

    # Four insight chips in a row
    c1, c2, c3, c4 = st.columns(4)

    # Chip 1: Top gainer
    with c1:
        st.markdown(f"""
        <div class="insight-chip insight-chip-green">
          <div class="insight-chip-label">Top Gainer Today</div>
          <div class="insight-chip-value">
            <span style="color:var(--accent);font-family:'JetBrains Mono',monospace;">{_html.escape(str(top_g['label']))}</span>
            &nbsp;<span style="color:var(--green);">▲ +{top_g['chg']:.2f}%</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

    # Chip 2: Biggest decline
    with c2:
        st.markdown(f"""
        <div class="insight-chip insight-chip-red">
          <div class="insight-chip-label">Biggest Decline</div>
          <div class="insight-chip-value">
            <span style="color:var(--accent);font-family:'JetBrains Mono',monospace;">{_html.escape(str(top_l['label']))}</span>
            &nbsp;<span style="color:var(--red);">▼ {top_l['chg']:.2f}%</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

    # Chip 3: Market breadth
    with c3:
        st.markdown(f"""
        <div class="insight-chip {sent_color}">
          <div class="insight-chip-label">Market Breadth</div>
          <div class="insight-chip-value">
            <span style="font-family:'JetBrains Mono',monospace;">{breadth_pct}% Up</span>
            &nbsp;<span style="color:var(--text-muted);font-size:0.78rem;">{up_n} adv · {dn_n} dec</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

    # Chip 4: Sentiment + VIX
    with c4:
        st.markdown(f"""
        <div class="insight-chip">
          <div class="insight-chip-label">Sentiment · {vix_str}</div>
          <div class="insight-chip-value">
            <span style="font-family:'JetBrains Mono',monospace;">{sentiment}</span>
            &nbsp;<span style="color:var(--text-muted);font-size:0.78rem;">across {total} assets</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<hr class="divider">', unsafe_allow_html=True)


# ── FEATURES SHOWCASE ─────────────────────────────────────────────────────────
st.markdown("""
<div class="section-sub">What's Inside</div>
<div class="section-title">Everything You Need. Nothing You Don't.</div>
<br>
""", unsafe_allow_html=True)

# Define the 8 feature cards (icon, title, description)
features = [
    ("📊", "Market Overview",     "Live prices + color-coded returns across 1D → 10Y. Market breadth bar. Sharpe star ratings. One-click filters."),
    ("🎯", "Portfolio Builder",   "Modern Portfolio Theory engine. Efficient Frontier with 2,000 Monte Carlo simulations. Correlation heatmap. SIP vs lump-sum projector."),
    ("🔍", "Search & Recommend",  "Intelligence Card: Sharpe, RSI, 52W range, trend signals, verdict. Multi-asset radar chart comparison."),
    ("🔥", "Performance Heatmap", "Treemap · Sector Rotation Sunburst · Calendar Heatmap (GitHub-style). Top movers panel auto-computed."),
    ("📈", "Price History",       "Candlestick + volume. Overlays: SMA 20/50/200, EMA, Bollinger Bands. Sub-charts: RSI or MACD. Period pills 1W → 20Y."),
    ("⚖️", "Risk vs Return",      "Quadrant-labelled scatter. Security Market Line. Portfolio star marker. Drawdown underwater chart for any asset."),
    ("🧮", "Interactive Glossary","Searchable terms. Live Sharpe formula playground. Quick-reference Sharpe interpretation table."),
    ("📋", "Risk Profiler",       "SEBI-aligned 5-stage questionnaire. Filters the entire dashboard to assets matching your exact risk tolerance."),
]

# Render features in 2 rows of 4 cards each
r1 = st.columns(4)  # First row
r2 = st.columns(4)  # Second row
for col, (icon, title, desc) in zip(r1, features[:4]):
    col.markdown(f'<div class="feature-card"><div class="feature-icon">{icon}</div><div class="feature-title">{title}</div><div class="feature-desc">{desc}</div></div>', unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)
for col, (icon, title, desc) in zip(r2, features[4:]):
    col.markdown(f'<div class="feature-card"><div class="feature-icon">{icon}</div><div class="feature-title">{title}</div><div class="feature-desc">{desc}</div></div>', unsafe_allow_html=True)

st.markdown('<hr class="divider">', unsafe_allow_html=True)


# ── HOW IT WORKS ─────────────────────────────────────────────────────────────
st.markdown("""
<div class="section-sub">How It Works</div>
<div class="section-title">Simple. Transparent. Accurate.</div>
<br>
""", unsafe_allow_html=True)

# 4-step onboarding flow
steps = [
    ("01", "Choose Your Market",       "Pick Indian or US. Each is a complete analytical environment with live data."),
    ("02", "Set Your Risk Profile",    "Answer 5 questions. Get your SEBI-aligned profile. The dashboard filters automatically."),
    ("03", "Explore & Analyse",        "Browse 110 assets with 20Y history. Search any ticker. Build and optimise a portfolio."),
    ("04", "Invest with Confidence",   "Use the Intelligence Card, Efficient Frontier, and SIP projector to make data-driven decisions."),
]
for col, (num, title, desc) in zip(st.columns(4), steps):
    col.markdown(f'<div class="step-card"><div class="step-num">{num}</div><div class="step-title">{title}</div><div class="step-desc">{desc}</div></div>', unsafe_allow_html=True)

st.markdown('<hr class="divider">', unsafe_allow_html=True)


# ── WHY NIVESH ─────────────────────────────────────────────────────────────────
st.markdown("""
<div class="section-sub">Why Nivesh Terminal</div>
<div class="section-title">Built Different. On Purpose.</div>
<br>
""", unsafe_allow_html=True)

# 6 differentiator cards in 2 columns
why_items = [
    ("🎯", "Calendar-Accurate Returns",    "pd.DateOffset calendar matching for every period — 1D to 10Y. Never hardcoded offsets. Blank > wrong."),
    ("🧮", "Correct SIP Compounding",      "Actual SIP future value formula, not lump-sum dressed as SIP. The difference is 3–5× over 20 years."),
    ("📐", "SEBI-Aligned Risk Model",      "5-stage profiling grounded in SEBI IAR 2013 and AMFI demographics — not a generic risk slider."),
    ("🇮🇳", "India-First Design",           "All US prices in ₹ via live USD/INR. Zerodha, Groww, INDmoney, Vested context throughout."),
    ("📊", "Two-Dataframe Architecture",   "Daily data for short-term precision. Weekly data for 20Y depth. The same separation used in production fintech."),
    ("🔓", "Free & Open",                  "No paywalls. No ads. No data selling. Nivesh Terminal is a public good for every Indian investor."),
]
w1, w2 = st.columns(2)
for col, items in [(w1, why_items[:3]), (w2, why_items[3:])]:
    with col:
        for icon, title, desc in items:
            st.markdown(f'<div class="why-card"><div class="why-icon">{icon}</div><div><div class="why-title">{title}</div><div class="why-desc">{desc}</div></div></div>', unsafe_allow_html=True)

st.markdown('<hr class="divider">', unsafe_allow_html=True)


# ── FINAL CTA (Call to Action) ────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center;padding:32px 20px 20px;">
  <div class="section-title">Ready to Invest Smarter?</div>
  <p style="color:var(--text-muted);font-size:0.88rem;margin:10px auto 28px;max-width:400px;line-height:1.65;">
    Choose your market and start exploring 20 years of data with institutional-grade analytics.
  </p>
</div>
""", unsafe_allow_html=True)

# Bottom CTA buttons: India | tagline | US
c1, c2, c3 = st.columns([1, 1, 1])
with c1:
    if st.button("🇮🇳  Indian Market", use_container_width=True, type="primary", key="india_cta"):
        st.switch_page("pages/1_india_market.py")
with c2:
    st.markdown(
        '<div style="display:flex;align-items:center;justify-content:center;'
        'height:38px;text-align:center;color:var(--text-muted);font-size:0.76rem;">'
        '220 assets · 20Y history · Free forever</div>',
        unsafe_allow_html=True,
    )
with c3:
    if st.button("🇺🇸  US Market", use_container_width=True, type="primary", key="us_cta"):
        st.switch_page("pages/2_us_market.py")


# ── FOOTER ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="footer">
  <div class="footer-name">Nivesh Terminal</div>
  <div class="footer-desc">Built by Eshan Mandloi · Financial Intelligence Platform for Indian Investors</div>
  <div class="footer-links">
    <a class="footer-link" href="https://www.linkedin.com/in/eshan-mandloi" target="_blank">LinkedIn</a>
    <a class="footer-link" href="https://github.com/eshan2018/Nivesh-Terminal" target="_blank">GitHub</a>
    <a class="footer-link" href="/1_india_market">Indian Market</a>
    <a class="footer-link" href="/2_us_market">US Market</a>
  </div>
  <div class="footer-disclaimer">
    ⚠️ Nivesh Terminal is for educational and informational purposes only.
    Nothing on this platform constitutes financial advice. Past performance does not guarantee future results.
    Please consult a SEBI-registered investment adviser before making investment decisions.
    All signals are quantitative heuristics — not backtested recommendations.
    Data sourced from yfinance and Alpha Vantage. AI analysis generated by Llama 3.3 via Groq — verify independently before acting.
  </div>
</div>
""", unsafe_allow_html=True)
