"""Central design system for Nivesh Terminal. Call inject_theme() at top of every page.

This file defines:
1. PLOTLY_THEME — shared dark theme dict applied to every Plotly chart
2. GRID_COLOR — subtle grid line color for chart axes
3. inject_theme() — injects 625 lines of CSS into the Streamlit page

The CSS covers:
- Design tokens (colors, fonts, spacing)
- Global reset (dark background, hidden Streamlit chrome)
- Component styles: cards, pulse bar, metric band, badges, verdict cards,
  intelligence card, insight chips, marquee ticker, hero section, market cards,
  feature cards, steps, footer, dashboard header, widget overrides, period pills,
  quadrant labels, and mobile responsive breakpoints
"""
import streamlit as st  # Streamlit UI framework

# Google Fonts URL — loads 3 font families used throughout the app:
# DM Sans (body text), JetBrains Mono (monospace, for numbers/code),
# Inter (UI labels + titles)
_FONTS = "https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;700&family=JetBrains+Mono:wght@400;700&family=Inter:wght@400;500;600;700;800&display=swap"

# Shared Plotly theme — applied to every chart via fig.update_layout(**PLOTLY_THEME)
PLOTLY_THEME = {
    "paper_bgcolor": "#060a12",  # Chart outer background (matches page)
    "plot_bgcolor":  "#060a12",  # Chart inner plot area background
    "font": {"color": "#f0f6ff", "family": "Inter, DM Sans, sans-serif"},  # Light text on dark bg
}

# Grid line color for chart axes — very subtle so charts feel clean
GRID_COLOR = "rgba(148, 163, 184, 0.1)"


def inject_theme(hide_sidebar: bool = False) -> None:
    """Inject the full CSS design system into the current Streamlit page.

    Args:
        hide_sidebar: If True, completely hides the sidebar (used on the home page).
    """
    # Conditionally add CSS to hide the sidebar
    sidebar_hide = "[data-testid='stSidebar']{display:none!important;}" if hide_sidebar else ""

    st.markdown(f"""
<style>
/* Import Google Fonts (DM Sans, JetBrains Mono, Inter) */
@import url('{_FONTS}');

/* ══════════════════════════════════════════════════════════════════════════
   DESIGN TOKENS — CSS custom properties (variables) for the entire app.
   All colors, backgrounds, and accents are defined here so the whole UI
   can be restyled by changing these 11 values.
   ══════════════════════════════════════════════════════════════════════════ */
:root {{
  --bg-base:        #060a12;              /* Deepest background (page level) */
  --bg-surface:     #0d1526;              /* Card / panel background */
  --bg-elevated:    #111d33;              /* Hover / raised surface */
  --border:         #1e2d45;              /* Default border color */
  --border-active:  #ffb300;              /* Active / focused border (amber) */
  --text-primary:   #f0f6ff;             /* Main text color (near-white) */
  --text-secondary: #8da4c4;             /* Secondary text (muted blue-grey) */
  --text-muted:     #4a6080;             /* Least prominent text */
  --accent:         #ffb300;              /* Primary accent color (amber) */
  --accent-dim:     rgba(255,179,0,0.12); /* Faint accent background */
  --green:          #00e676;              /* Positive / gain color */
  --green-dim:      rgba(0,230,118,0.12); /* Faint green background */
  --red:            #f44336;              /* Negative / loss color */
  --red-dim:        rgba(244,67,54,0.12); /* Faint red background */
  --gold:           #ffd700;              /* Warning / neutral accent */
  --gold-dim:       rgba(255,215,0,0.12); /* Faint gold background */
  --purple:         #b388ff;              /* Secondary accent (used for volatility) */
  --purple-dim:     rgba(179,136,255,0.12); /* Faint purple background */
}}

/* ══════════════════════════════════════════════════════════════════════════
   GLOBAL RESET — set dark background and font on all Streamlit containers.
   Hide Streamlit's default hamburger menu, footer, and header.
   ══════════════════════════════════════════════════════════════════════════ */
html, body, [data-testid="stAppViewContainer"], .stApp {{
    background-color: var(--bg-base) !important;  /* Dark background everywhere */
    color: var(--text-primary);                    /* Light text */
    font-family: 'DM Sans', sans-serif;            /* Default body font */
}}
.main .block-container {{
    padding-top: 0;              /* Remove top padding for tighter layout */
    max-width: 1440px;           /* Cap content width on ultra-wide screens */
    padding-left: 1.5rem;       /* Horizontal padding */
    padding-right: 1.5rem;
}}
#MainMenu, footer, header {{ visibility: hidden; }}  /* Hide Streamlit chrome */
[data-testid="stToolbar"] {{ display: none; }}        /* Hide the toolbar */

/* Make all column children stretch to equal height (for market cards) */
[data-testid="stColumns"] {{
    align-items: stretch !important;
}}
[data-testid="stColumn"] > div {{
    height: 100%;
}}
{sidebar_hide}  /* Conditionally hide the sidebar */

/* ── Sidebar styling ──────────────────────────────────────────────────── */
[data-testid="stSidebar"] {{
    background: #08111f !important;         /* Even darker than page bg */
    border-right: 1px solid var(--border);  /* Subtle border */
}}

/* ══════════════════════════════════════════════════════════════════════════
   TYPOGRAPHY HELPERS — reusable CSS classes for text styling.
   ══════════════════════════════════════════════════════════════════════════ */
.t-display {{
    font-family: 'Inter', sans-serif;        /* Bold sans-serif for hero titles */
    font-weight: 800;
    color: var(--text-primary);
    line-height: 1.1;
}}
.t-label {{
    font-family: 'Inter', sans-serif;        /* Clean sans-serif for labels */
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.14em;                  /* Wide letter spacing for caps */
    text-transform: uppercase;
    color: var(--text-muted);
}}
.t-mono  {{ font-family: 'JetBrains Mono', monospace; }}  /* Monospace for numbers */
.t-accent {{ color: var(--accent); }}    /* Cyan accent color */
.t-green  {{ color: var(--green); }}     /* Green (positive) */
.t-red    {{ color: var(--red); }}       /* Red (negative) */
.t-gold   {{ color: var(--gold); }}      /* Gold (warning/neutral) */
.t-muted  {{ color: var(--text-muted); }}  /* Low-emphasis text */
.up       {{ color: var(--green) !important; }}   /* Force green */
.down     {{ color: var(--red) !important; }}     /* Force red */
.flat     {{ color: var(--text-secondary) !important; }}  /* Unchanged */

/* ══════════════════════════════════════════════════════════════════════════
   TABS — custom styling for Streamlit's tab component (the 7 dashboard tabs).
   ══════════════════════════════════════════════════════════════════════════ */
.stTabs [data-baseweb="tab-list"] {{
    background: var(--bg-surface);       /* Dark tab bar background */
    border-radius: 8px 8px 0 0;         /* Rounded top corners */
    padding: 4px 4px 0 4px;
    gap: 2px;                            /* Small gap between tabs */
    border-bottom: 2px solid var(--border);
}}
.stTabs [data-baseweb="tab"] {{
    background: transparent;             /* Inactive tab = no background */
    color: var(--text-muted);            /* Muted text for inactive tabs */
    font-family: 'Inter', sans-serif;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    padding: 9px 18px;
    border-radius: 6px 6px 0 0;
    border: none !important;
    transition: all 0.15s ease;          /* Smooth hover transition */
}}
.stTabs [aria-selected="true"] {{
    background: var(--bg-elevated) !important;    /* Active tab = raised bg */
    color: var(--accent) !important;              /* Cyan text */
    border-bottom: 2px solid var(--accent) !important;  /* Cyan underline */
}}

/* ══════════════════════════════════════════════════════════════════════════
   CARDS — generic card component with hover effect.
   Used as a base for feature cards, market cards, etc.
   ══════════════════════════════════════════════════════════════════════════ */
.card {{
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 20px;
    transition: all 0.2s cubic-bezier(0.4,0,0.2,1);  /* Smooth hover */
}}
.card:hover {{
    border-color: var(--border-active);               /* Cyan border on hover */
    background: var(--bg-elevated);                    /* Slightly lighter bg */
    box-shadow: 0 8px 32px rgba(255,179,0,0.07);     /* Subtle glow */
}}
.card-accent {{ border-top: 2px solid var(--accent); }}  /* Accent-topped cards */
.card-gold   {{ border-top: 2px solid var(--gold); }}
.card-green  {{ border-top: 2px solid var(--green); }}
.card-red    {{ border-top: 2px solid var(--red); }}

/* ══════════════════════════════════════════════════════════════════════════
   PULSE BAR — horizontal KPI strip on the Market Overview tab.
   Shows 5 metrics (breadth, avg Sharpe, avg return, positive count, total).
   ══════════════════════════════════════════════════════════════════════════ */
.pulse-bar {{
    display: flex;                       /* Horizontal layout */
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
    margin-bottom: 18px;
}}
.pulse-item {{
    flex: 1;                             /* Equal width for each item */
    padding: 13px 16px;
    border-right: 1px solid var(--border);  /* Divider between items */
    text-align: center;
}}
.pulse-item:last-child {{ border-right: none; }}  /* No divider after last item */
.pulse-label {{
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 5px;
}}
.pulse-value {{
    font-family: 'JetBrains Mono', monospace;  /* Monospace for numbers */
    font-size: 1.12rem;
    font-weight: 700;
    color: var(--text-primary);
}}
.pulse-delta {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem;
    margin-top: 3px;
}}

/* ══════════════════════════════════════════════════════════════════════════
   METRIC BAND — left-accent-bordered info box.
   Used for "Total Capital Deployed", period return annotations, Sharpe playground.
   ══════════════════════════════════════════════════════════════════════════ */
.metric-band {{
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent);  /* Thick left accent bar */
    border-radius: 6px;
    padding: 14px 18px;
    margin-bottom: 12px;
}}
.metric-band .m-label {{
    font-size: 0.64rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 4px;
}}
.metric-band .m-value {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.35rem;
    font-weight: 700;
    color: var(--text-primary);
}}

/* ══════════════════════════════════════════════════════════════════════════
   BADGES — small pill-shaped labels (equity, ETF, buy, hold, avoid).
   ══════════════════════════════════════════════════════════════════════════ */
.badge {{
    display: inline-block;
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 0.64rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    font-family: 'Inter', sans-serif;
}}
.badge-equity  {{ background: rgba(56,189,248,0.15);  color: #38bdf8; }}   /* Blue for equity */
.badge-etf     {{ background: var(--gold-dim);         color: var(--gold); }}  /* Gold for ETF */
.badge-fund    {{ background: var(--purple-dim);       color: var(--purple); }}  /* Purple for funds */
.badge-buy     {{ background: var(--green-dim);        color: var(--green); }}   /* Green for buy */
.badge-hold    {{ background: var(--gold-dim);         color: var(--gold); }}    /* Gold for hold */
.badge-avoid   {{ background: var(--red-dim);          color: var(--red); }}     /* Red for avoid */

/* ══════════════════════════════════════════════════════════════════════════
   VERDICT CARD — coloured box showing the quantitative signal verdict.
   Used in the Search tab's Intelligence Card.
   ══════════════════════════════════════════════════════════════════════════ */
.verdict-card {{
    border-radius: 8px;
    padding: 16px 22px;
    margin-top: 16px;
}}
/* Directional verdict styles (legacy — kept for backwards compatibility) */
.verdict-buy      {{ background: var(--green-dim); border: 1px solid rgba(0,230,118,0.3); }}
.verdict-hold     {{ background: var(--gold-dim);  border: 1px solid rgba(255,215,0,0.3); }}
.verdict-avoid    {{ background: var(--red-dim);   border: 1px solid rgba(244,67,54,0.3); }}
/* Non-directional signal classes (current — avoids implying buy/sell advice) */
.verdict-strong   {{ background: var(--green-dim); border: 1px solid rgba(0,230,118,0.3); }}
.verdict-moderate {{ background: rgba(56,189,248,0.08); border: 1px solid rgba(56,189,248,0.3); }}
.verdict-weak     {{ background: var(--gold-dim);  border: 1px solid rgba(255,215,0,0.3); }}
.verdict-low      {{ background: var(--red-dim);   border: 1px solid rgba(244,67,54,0.3); }}
.verdict-label {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.66rem;
    font-weight: 700;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    margin-bottom: 6px;
}}
.verdict-text       {{ font-size: 1.05rem; font-weight: 700; }}
.verdict-reason     {{ font-size: 0.82rem; color: var(--text-secondary); margin-top: 6px; line-height: 1.5; }}
.verdict-disclaimer {{ font-size: 0.72rem; color: var(--text-muted); margin-top: 10px; line-height: 1.4; font-style: italic; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 8px; }}

/* ══════════════════════════════════════════════════════════════════════════
   INTELLIGENCE CARD — the full-width ticker analysis card on the Search tab.
   Contains header (ticker + price), 3-column metrics grid, and verdict.
   ══════════════════════════════════════════════════════════════════════════ */
.intel-card {{
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 24px 28px;
    margin-top: 18px;
}}
.intel-header {{
    display: flex;
    justify-content: space-between;   /* Ticker left, price right */
    align-items: flex-start;
    margin-bottom: 18px;
    padding-bottom: 14px;
    border-bottom: 1px solid var(--border);
}}
.intel-ticker {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--accent);             /* Cyan ticker symbol */
}}
.intel-name {{
    font-size: 0.88rem;
    color: var(--text-secondary);
    margin-top: 3px;
}}
.intel-price {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.35rem;
    font-weight: 700;
    text-align: right;
}}
.intel-section-title {{
    font-size: 0.62rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 10px;
    padding-bottom: 4px;
    border-bottom: 1px solid var(--border);
}}
.intel-row {{
    display: flex;
    justify-content: space-between;   /* Label left, value right */
    padding: 5px 0;
    font-size: 0.85rem;
    border-bottom: 1px solid rgba(30,45,69,0.5);  /* Faint row divider */
}}
.intel-row:last-child {{ border-bottom: none; }}
.intel-row-label {{ color: var(--text-muted); font-size: 0.8rem; }}
.intel-row-value {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--text-primary);
}}

/* ══════════════════════════════════════════════════════════════════════════
   INSIGHT CHIPS — small info cards on the home page "Today's Intelligence".
   Each chip has a left accent bar, label, and value.
   ══════════════════════════════════════════════════════════════════════════ */
.insight-chip {{
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-left: 3px solid var(--accent);  /* Default cyan accent */
    border-radius: 6px;
    padding: 12px 16px;
}}
.insight-chip-gold  {{ border-left-color: var(--gold); }}   /* Override accent to gold */
.insight-chip-green {{ border-left-color: var(--green); }}  /* Override accent to green */
.insight-chip-red   {{ border-left-color: var(--red); }}    /* Override accent to red */
.insight-chip-label {{
    font-size: 0.6rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--text-muted);
    margin-bottom: 5px;
}}
.insight-chip-value {{
    font-size: 0.88rem;
    font-weight: 600;
    color: var(--text-primary);
    line-height: 1.4;
}}

/* ══════════════════════════════════════════════════════════════════════════
   MARQUEE TICKER — auto-scrolling horizontal ticker strip on the home page.
   Uses CSS animation (no JavaScript). Duplicated content creates seamless loop.
   ══════════════════════════════════════════════════════════════════════════ */
.marquee-wrap {{
    overflow: hidden;                    /* Clip the overflow */
    background: var(--bg-surface);
    border-top: 1px solid var(--border);
    border-bottom: 1px solid var(--border);
    padding: 9px 0;
    position: relative;
}}
/* Gradient fades on left and right edges for a polished look */
.marquee-wrap::before,
.marquee-wrap::after {{
    content: '';
    position: absolute;
    top: 0;
    width: 100px;
    height: 100%;
    z-index: 2;
    pointer-events: none;
}}
.marquee-wrap::before {{ left:0;  background: linear-gradient(to right, var(--bg-surface), transparent); }}
.marquee-wrap::after  {{ right:0; background: linear-gradient(to left,  var(--bg-surface), transparent); }}
.marquee-track {{
    display: flex;
    animation: marquee-scroll 50s linear infinite;  /* 50-second full loop */
    width: max-content;
}}
.marquee-track:hover {{ animation-play-state: paused; }}  /* Pause on hover for readability */
@keyframes marquee-scroll {{
    0%   {{ transform: translateX(0); }}
    100% {{ transform: translateX(-50%); }}  /* Scroll exactly half (the duplicate takes over) */
}}
.t-item {{
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 0 24px;
    border-right: 1px solid var(--border);  /* Divider between ticker items */
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.76rem;
    white-space: nowrap;
}}
.t-item-label {{ color: var(--text-muted); font-weight: 700; }}   /* Index name */
.t-item-price {{ color: var(--text-primary); }}                    /* Current price */
.t-item-up    {{ color: var(--green); }}                           /* Positive change */
.t-item-down  {{ color: var(--red); }}                             /* Negative change */
.t-item-flat  {{ color: var(--text-secondary); }}                  /* No change */

/* ══════════════════════════════════════════════════════════════════════════
   HERO — the big landing section with animated entrance.
   Radial gradient creates a subtle spotlight effect.
   ══════════════════════════════════════════════════════════════════════════ */
.hero {{
    text-align: center;
    padding: 80px 24px 60px;
    background: radial-gradient(ellipse at top, #0d1f3c 0%, #060a12 65%);  /* Spotlight gradient */
    border-bottom: 1px solid var(--border);
}}
.hero-badge {{
    display: inline-block;
    background: var(--accent-dim);
    border: 1px solid rgba(255,179,0,0.3);
    color: var(--accent);
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    padding: 6px 20px;
    border-radius: 20px;
    margin-bottom: 24px;
}}
.hero-title {{
    font-family: 'Inter', sans-serif;
    font-size: 4.2rem;
    font-weight: 800;
    color: var(--text-primary);
    line-height: 1.08;
    margin-bottom: 18px;
}}
.hero-title span {{ color: var(--accent); }}  /* "TERMINAL" in amber */
.hero-tagline {{
    font-size: 1.12rem;
    color: var(--text-secondary);
    font-weight: 300;
    margin-bottom: 44px;
    max-width: 600px;
    margin-left: auto;
    margin-right: auto;
    line-height: 1.65;
}}

/* ── Hero entrance animations (staggered fade-in from bottom) ──────── */
@keyframes fadeInUp {{
    from {{ opacity: 0; transform: translateY(22px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
}}
@keyframes fadeIn {{
    from {{ opacity: 0; }}
    to   {{ opacity: 1; }}
}}
.a0 {{ animation: fadeInUp 0.55s ease 0.00s both; }}  /* Badge: immediate */
.a1 {{ animation: fadeInUp 0.55s ease 0.15s both; }}  /* Title: 150ms delay */
.a2 {{ animation: fadeInUp 0.55s ease 0.28s both; }}  /* Tagline: 280ms delay */
.a3 {{ animation: fadeIn  0.70s ease 0.45s both; }}   /* Timestamp: 450ms fade */

/* ══════════════════════════════════════════════════════════════════════════
   MARKET CARDS — the India / US selection cards on the home page.
   Hover lifts the card up with a shadow effect.
   ══════════════════════════════════════════════════════════════════════════ */
.market-card {{
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 32px 28px;
    text-align: center;
    transition: all 0.22s cubic-bezier(0.4,0,0.2,1);
    height: 100%;
    min-height: 560px;                 /* Consistent card height */
    display: flex;
    flex-direction: column;
    justify-content: space-between;   /* Push content to top and bottom */
}}
.market-card:hover {{
    border-color: var(--accent);
    background: var(--bg-elevated);
    transform: translateY(-4px);       /* Lift up on hover */
    box-shadow: 0 20px 44px rgba(255,179,0,0.09);  /* Amber glow */
}}
/* Equal-height cards: the India/US columns already stretch to the same height,
   but each card only takes its own content height (footer/subtitle text
   differs). Make the card's wrapper chain a growing flex column so the card
   fills its column — both cards then render identically regardless of text. */
[data-testid="stColumn"] [data-testid="stElementContainer"]:has(.market-card),
[data-testid="stColumn"] [data-testid="stElementContainer"]:has(.market-card) .stMarkdown,
[data-testid="stColumn"] [data-testid="stElementContainer"]:has(.market-card) [data-testid="stMarkdownContainer"] {{
    display: flex;
    flex-direction: column;
    flex: 1 1 auto;
}}
.market-card-flag  {{ font-size: 3.2rem; margin-bottom: 14px; }}
.market-card-title {{ font-family: 'Inter', sans-serif; font-size: 1.55rem; font-weight: 700; color: var(--text-primary); margin-bottom: 6px; }}
.market-card-sub   {{ color: var(--text-muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.14em; font-weight: 700; margin-bottom: 18px; }}
.market-card-desc  {{ color: var(--text-secondary); font-size: 0.86rem; line-height: 1.6; margin-bottom: 20px; }}
.market-card-stats {{ display: flex; justify-content: center; gap: 20px; margin-bottom: 20px; }}
.stat-item         {{ text-align: center; }}
.stat-num  {{ font-family: 'JetBrains Mono', monospace; font-size: 1.25rem; font-weight: 700; color: var(--accent); }}
.stat-lbl  {{ font-size: 0.62rem; text-transform: uppercase; letter-spacing: 0.1em; color: var(--text-muted); font-weight: 700; margin-top: 2px; }}

/* ── Live index mini-table inside each market card ──────────────────── */
.card-index-row {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 0;
    border-bottom: 1px solid var(--border);
    font-size: 0.82rem;
    gap: 8px;
}}
.card-index-row:last-child {{ border-bottom: none; }}
.card-index-name  {{ color: var(--text-secondary); font-weight: 600; flex: 0 0 110px; text-align: left; }}
.card-index-price {{ font-family: 'JetBrains Mono', monospace; color: var(--text-primary); flex: 1; text-align: right; }}
.card-index-chg   {{ font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; flex: 0 0 72px; text-align: right; }}

/* ══════════════════════════════════════════════════════════════════════════
   FEATURE CARDS — 8 cards in 2×4 grid showing what the app offers.
   ══════════════════════════════════════════════════════════════════════════ */
.feature-card {{
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-top: 2px solid var(--accent);  /* Cyan accent line at top */
    border-radius: 6px;
    padding: 22px 18px;
    height: 100%;
    min-height: 240px;  /* Force equal heights across the 2x4 grid */
    display: flex;
    flex-direction: column;
    transition: all 0.18s ease;
}}
.feature-card:hover {{
    background: var(--bg-elevated);
    transform: translateY(-2px);           /* Subtle lift on hover */
}}
.feature-icon  {{ font-size: 1.7rem; margin-bottom: 10px; }}
.feature-title {{ font-weight: 700; font-size: 0.92rem; color: var(--text-primary); margin-bottom: 7px; }}
.feature-desc  {{ color: var(--text-muted); font-size: 0.8rem; line-height: 1.6; }}

/* ══════════════════════════════════════════════════════════════════════════
   SECTION CHROME — centered section headers and horizontal dividers.
   ══════════════════════════════════════════════════════════════════════════ */
.section-title {{ font-family: 'Inter', sans-serif; font-size: 1.9rem; font-weight: 700; color: var(--text-primary); text-align: center; margin-bottom: 6px; }}
.section-sub   {{ color: var(--text-muted); font-size: 0.72rem; text-align: center; text-transform: uppercase; letter-spacing: 0.14em; font-weight: 700; margin-bottom: 32px; }}
.divider {{ border: none; border-top: 1px solid var(--border); margin: 52px 0; }}

/* ══════════════════════════════════════════════════════════════════════════
   WHY CARDS — horizontal icon + text cards in the "Why Nivesh" section.
   ══════════════════════════════════════════════════════════════════════════ */
.why-card {{
    background: var(--bg-surface);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 18px;
    display: flex;
    gap: 14px;
    align-items: flex-start;
    margin-bottom: 10px;
    min-height: 110px;  /* Equalise card heights across the 3x2 grid */
    transition: all 0.18s ease;
}}
.why-card:hover {{ background: var(--bg-elevated); border-color: var(--border-active); }}
.why-icon  {{ font-size: 1.35rem; flex-shrink: 0; }}
.why-title {{ font-weight: 700; color: var(--text-primary); font-size: 0.88rem; margin-bottom: 4px; }}
.why-desc  {{ color: var(--text-muted); font-size: 0.78rem; line-height: 1.5; }}

/* ══════════════════════════════════════════════════════════════════════════
   STEPS — numbered onboarding cards (01, 02, 03, 04).
   ══════════════════════════════════════════════════════════════════════════ */
.step-card  {{ text-align: center; padding: 18px; }}
.step-num   {{ font-family: 'JetBrains Mono', monospace; font-size: 1.9rem; font-weight: 700; color: rgba(255,179,0,0.28); margin-bottom: 10px; }}  /* Faint amber number */
.step-title {{ font-weight: 700; color: var(--text-primary); margin-bottom: 6px; font-size: 0.9rem; }}
.step-desc  {{ color: var(--text-muted); font-size: 0.8rem; line-height: 1.6; }}

/* ══════════════════════════════════════════════════════════════════════════
   FOOTER — bottom section with credits, links, and SEBI disclaimer.
   ══════════════════════════════════════════════════════════════════════════ */
.footer {{
    background: #050810;                    /* Even darker than page bg */
    border-top: 1px solid var(--border);
    padding: 40px 60px;
    text-align: center;
    margin-top: 48px;
}}
.footer-name {{ font-family: 'Inter', sans-serif; font-size: 1.35rem; color: var(--accent); margin-bottom: 7px; }}
.footer-desc {{ color: var(--text-muted); font-size: 0.8rem; margin-bottom: 18px; }}
.footer-links {{ display: flex; justify-content: center; gap: 22px; flex-wrap: wrap; margin-bottom: 18px; }}
.footer-link {{ color: var(--text-muted); font-size: 0.76rem; text-decoration: none; transition: color 0.15s; }}
.footer-link:hover {{ color: var(--accent); }}
.footer-disclaimer {{ color: #2a3a52; font-size: 0.67rem; max-width: 600px; margin: 0 auto; line-height: 1.65; }}

/* ══════════════════════════════════════════════════════════════════════════
   DASHBOARD HEADER — title and subtitle at the top of each market page.
   ══════════════════════════════════════════════════════════════════════════ */
.dash-title {{ font-size: 1.45rem; font-weight: 800; color: var(--text-primary); font-family: 'Inter', sans-serif; }}
.dash-sub   {{ font-size: 0.72rem; color: var(--text-muted); font-family: 'JetBrains Mono', monospace; margin-top: 2px; }}

/* ══════════════════════════════════════════════════════════════════════════
   STREAMLIT WIDGET OVERRIDES — force dark theme on dropdowns, inputs, tables.
   ══════════════════════════════════════════════════════════════════════════ */
.stSelectbox > div > div,
.stMultiSelect > div > div {{
    background: var(--bg-surface) !important;
    border-color: var(--border) !important;
}}
.stNumberInput input,
.stTextInput input {{
    background: var(--bg-surface) !important;
    border-color: var(--border) !important;
    color: var(--text-primary) !important;
    font-family: 'JetBrains Mono', monospace !important;
}}
.stDataFrame {{
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
}}

/* ══════════════════════════════════════════════════════════════════════════
   PERIOD PILLS — small rounded buttons for period selection (1W, 1M, etc.).
   ══════════════════════════════════════════════════════════════════════════ */
.period-pills {{ display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }}
.pill {{
    padding: 5px 14px;
    border-radius: 20px;                 /* Fully rounded */
    font-family: 'Inter', sans-serif;
    font-size: 0.75rem;
    font-weight: 600;
    cursor: pointer;
    border: 1px solid var(--border);
    color: var(--text-muted);
    background: transparent;
    transition: all 0.15s;
}}
.pill-active {{
    background: var(--accent-dim);       /* Active pill gets cyan bg */
    border-color: var(--accent);
    color: var(--accent);
}}

/* ── Quadrant labels (Risk vs Return scatter plot) ─────────────────── */
.quadrant-label {{
    font-family: 'Inter', sans-serif;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    opacity: 0.45;
}}

/* ══════════════════════════════════════════════════════════════════════════
   PRIMARY BUTTONS — the amber "Enter Market" CTAs. Amber is a light accent,
   so white label text is low-contrast; force near-black label + bold weight.
   ══════════════════════════════════════════════════════════════════════════ */
.stButton > button[kind="primary"],
[data-testid="stBaseButton-primary"] {{
    color: #0a0f1a !important;            /* Near-black text on amber */
    font-weight: 700 !important;
}}
.stButton > button[kind="primary"] *,
[data-testid="stBaseButton-primary"] * {{
    color: #0a0f1a !important;            /* Cover inner span/markdown */
}}
.stButton > button[kind="primary"]:hover,
.stButton > button[kind="primary"]:active,
.stButton > button[kind="primary"]:focus,
[data-testid="stBaseButton-primary"]:hover {{
    color: #0a0f1a !important;            /* Keep black across all states */
}}

/* ══════════════════════════════════════════════════════════════════════════
   ACCESSIBILITY — keyboard focus states for buttons, inputs, tabs.
   Ensures keyboard-only users see where focus is. WCAG 2.1 requirement.
   ══════════════════════════════════════════════════════════════════════════ */
button:focus-visible,
[role="button"]:focus-visible,
input:focus-visible,
select:focus-visible,
textarea:focus-visible,
.stTabs [data-baseweb="tab"]:focus-visible,
[data-testid="stFormSubmitButton"] button:focus-visible {{
    outline: 2px solid var(--accent) !important;
    outline-offset: 2px !important;
    box-shadow: 0 0 0 4px rgba(0, 212, 255, 0.15) !important;
}}

/* ══════════════════════════════════════════════════════════════════════════
   TABLE OVERFLOW — ensures dataframes scroll horizontally on narrow screens
   instead of overflowing the page. WCAG horizontal-scroll requirement.
   ══════════════════════════════════════════════════════════════════════════ */
[data-testid="stDataFrame"],
[data-testid="stTable"] {{
    overflow-x: auto !important;
    max-width: 100% !important;
}}

/* ══════════════════════════════════════════════════════════════════════════
   TABLET RESPONSIVE — adjustments for tablet-sized screens (769-1024px).
   ══════════════════════════════════════════════════════════════════════════ */
@media (min-width: 769px) and (max-width: 1024px) {{
    .hero-title {{ font-size: 3rem; }}          /* Slightly smaller hero */
    .hero-tagline {{ font-size: 1.05rem; }}
    .dash-title {{ font-size: 1.3rem; }}
    .main .block-container {{ padding-left: 1rem; padding-right: 1rem; }}
}}

/* ══════════════════════════════════════════════════════════════════════════
   MOBILE RESPONSIVE — adjustments for screens narrower than 768px.
   ══════════════════════════════════════════════════════════════════════════ */
@media (max-width: 768px) {{
    /* Pulse bar: wrap from horizontal strip to 2-column grid */
    .pulse-bar {{ flex-wrap: wrap; }}
    .pulse-item {{
        flex: 1 1 45%;                   /* 2 items per row */
        border-right: none !important;
        border-bottom: 1px solid var(--border);
    }}
    .pulse-item:last-child {{ border-bottom: none; }}

    /* Market cards: remove fixed height so they don't clip on narrow screens */
    .market-card {{ min-height: auto !important; }}

    /* Dashboard title: smaller on mobile */
    .dash-title {{ font-size: 1.1rem; }}

    /* Hero section: reduce padding and font sizes */
    .hero {{ padding: 48px 16px 40px; }}
    .hero-title {{ font-size: 2.4rem; }}
    .hero-tagline {{ font-size: 0.95rem; }}

    /* Intel card: collapse 3-column grid to 1 column on mobile */
    .intel-card > div[style*="grid-template-columns:1fr 1fr 1fr"] {{
        grid-template-columns: 1fr !important;
    }}

    /* Footer: less horizontal padding on mobile */
    .footer {{ padding: 32px 20px; }}

    /* Card index table: tighter fonts on small screens */
    .card-index-name  {{ font-size: 0.74rem; flex: 0 0 80px; }}
    .card-index-price {{ font-size: 0.74rem; }}
    .card-index-chg   {{ font-size: 0.7rem; flex: 0 0 58px; }}
}}
</style>
""", unsafe_allow_html=True)
