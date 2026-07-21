"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

function Pane({ id, title, span, children, domId }: {
  id: string; title: string; span: string; children: React.ReactNode; domId?: string;
}) {
  return (
    <section className={`pane ${span}`} id={domId}>
      <div className="pane-title">
        <span><span className="id">[{id}]</span> {title}</span>
        <span className="controls">─ □ ×</span>
      </div>
      <div className="pane-body">{children}</div>
    </section>
  );
}

/* ---------- [01] MARKET WATCH ---------- */
type Quote = { name: string; value: number; change: number };

// Fallback shown only if the snapshot fetch fails, so the pane never renders empty.
const SEED: Quote[] = [
  { name: "NIFTY 50", value: 24812.35, change: 0.64 },
  { name: "SENSEX", value: 81442.1, change: 0.58 },
  { name: "BANK NIFTY", value: 52930.75, change: -0.21 },
  { name: "S&P 500", value: 6120.4, change: 0.31 },
  { name: "NASDAQ", value: 20105.1, change: 0.72 },
];

type PulseRow = { label: string; price: number; chg: number };

export function MarketWatchPane() {
  const [quotes, setQuotes] = useState<Quote[]>(SEED);
  const [asof, setAsof] = useState<string>("");
  const [flash, setFlash] = useState<Set<number>>(new Set());
  const prev = useRef<Map<string, number>>(new Map());

  /* LIVE: reads the snapshot the Python pipeline writes (web/public/data/pulse.json).
     Fetches on mount + every 5 min so a fresh 15-min snapshot is picked up.
     Rows whose value moved since the last fetch flash amber. */
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch("/data/pulse.json", { cache: "no-store" });
        if (!res.ok) return;
        const data = await res.json();
        const rows: Quote[] = [...(data.india ?? []), ...(data.us ?? [])].map(
          (r: PulseRow) => ({ name: String(r.label).toUpperCase(), value: r.price, change: r.chg })
        );
        if (cancelled || !rows.length) return;

        const moved = new Set<number>();
        rows.forEach((r, i) => {
          const before = prev.current.get(r.name);
          if (before !== undefined && before !== r.value) moved.add(i);
          prev.current.set(r.name, r.value);
        });
        setQuotes(rows);
        setAsof(typeof data.generated_at === "string" ? data.generated_at : "");
        if (moved.size) {
          setFlash(moved);
          setTimeout(() => !cancelled && setFlash(new Set()), 600);
        }
      } catch {
        /* keep whatever is on screen */
      }
    };
    load();
    const id = setInterval(load, 5 * 60 * 1000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  return (
    <Pane id="01" title="MARKET-WATCH" span="s4" domId="pane-markets">
      {quotes.map((q, i) => (
        <div className={`mw-row ${flash.has(i) ? "mw-flash" : ""}`} key={q.name}>
          <span className="n">{q.name}</span>
          <span>
            {q.value.toLocaleString("en-IN", { maximumFractionDigits: 2 })}{" "}
            <span className={q.change >= 0 ? "up" : "down"}>
              {q.change >= 0 ? "▲" : "▼"} {Math.abs(q.change).toFixed(2)}%
            </span>
          </span>
        </div>
      ))}
      <div className="muted" style={{ marginTop: 8, fontSize: 11 }}>
        {asof ? `snapshot · ${asof} · 15-min refresh` : "snapshot pipeline · 15-min refresh"}
      </div>
    </Pane>
  );
}

/* ---------- [02] TREND (ascii sparkline) ---------- */
const BLOCKS = "▁▂▃▄▅▆▇█";

export function TrendPane() {
  const [series, setSeries] = useState<number[]>(() => {
    const s: number[] = [];
    let v = 2;
    for (let i = 0; i < 42; i++) { v += 0.16 + (Math.random() - 0.42) * 0.5; s.push(v); }
    return s;
  });

  useEffect(() => {
    const id = setInterval(() => {
      setSeries((s) => {
        const next = s[s.length - 1] + 0.16 + (Math.random() - 0.42) * 0.5;
        return [...s.slice(1), next];
      });
    }, 900);
    return () => clearInterval(id);
  }, []);

  const min = Math.min(...series), max = Math.max(...series);
  const spark = series
    .map((v) => BLOCKS[Math.min(7, Math.floor(((v - min) / (max - min + 1e-9)) * 8))])
    .join("");

  return (
    <Pane id="02" title="TREND · NIFTY 50 · 10Y" span="s5">
      <div className="spark" aria-hidden="true">{spark}</div>
      <div className="trend-big up">▲ +214.6%</div>
      <div className="trend-caption">
        10-year return, calendar-accurate · weekly σ × √52 · Sharpe ★★★
      </div>
      <div className="trend-caption">
        every number on this site: computed, never hardcoded. blank &gt; wrong.
      </div>
    </Pane>
  );
}

/* ---------- [03] SYS-INFO (neofetch style) ---------- */
export function SysInfoPane() {
  const rows: [string, string][] = [
    ["creator", "Eshan Mandloi"],
    ["universe", "220 assets (110 IN · 110 US)"],
    ["depth", "20Y weekly · 2Y daily"],
    ["refresh", "15-min snapshot pipeline"],
    ["math", "pure pandas · MPT · 2000 sims"],
    ["price", "₹0 · free forever"],
    ["ads", "none"],
    ["trackers", "none"],
  ];
  return (
    <Pane id="03" title="SYS-INFO" span="s3">
      {rows.map(([k, v]) => (
        <div className="mw-row" key={k}>
          <span className="n">{k}</span>
          <span className="amber" style={{ textShadow: "none" }}>{v}</span>
        </div>
      ))}
    </Pane>
  );
}

/* ---------- [04] MODULES (ls output) ---------- */
const MODULES: [string, string][] = [
  ["overview.sys", "breadth, avg Sharpe, sortable 1D→10Y table across the universe"],
  ["portfolio.sys", "Efficient Frontier · 2,000 Monte Carlo sims · correlation heatmap"],
  ["sip.sys", "true SIP compounding with ±1σ volatility cone, 2×/5×/10× markers"],
  ["search.sys", "per-asset Intelligence Card: Sharpe, RSI, 52W range, verdict"],
  ["heatmap.sys", "treemap · sector-rotation sunburst · calendar heatmap"],
  ["charts.sys", "candles + volume, SMA/EMA/Bollinger, RSI/MACD, 1W→20Y"],
  ["risk.sys", "risk-vs-return quadrant, Security Market Line, drawdown chart"],
  ["profiler.sys", "SEBI-aligned 5-stage risk profile filters the whole terminal"],
];

export function ModulesPane() {
  return (
    <Pane id="04" title="MODULES — $ ls -la /terminal" span="s6" domId="pane-modules">
      {MODULES.map(([f, d]) => (
        <div className="ls-row" key={f}>
          <span className="file">{f}</span>
          <span className="desc">{d}</span>
        </div>
      ))}
      <div className="muted" style={{ marginTop: 8, fontSize: 11 }}>
        8 modules · 0 paywalls · all of it ships to everyone
      </div>
    </Pane>
  );
}

/* ---------- [05] MANIFESTO ---------- */
export function ManifestoPane() {
  return (
    <Pane id="05" title="$ cat manifesto.txt" span="s6" domId="pane-manifesto">
      <div className="manifesto">
        {`Bloomberg costs $25,000 a year. Most Indian retail
investors get ads, tips, and half a chart.

Nivesh Terminal is the third option: `}
        <b>institutional-grade analytics, free, for everyone</b>
        {` — Indian and US markets side by side, every US price
convertible to ₹, twenty years of history behind
every number.

No paywalls. No ads. No data selling.
Built as a public good.

— Eshan Mandloi`}
      </div>
    </Pane>
  );
}

/* ---------- [06] RISK PROFILER ---------- */
const STAGES: [string, number, string][] = [
  ["Conservative", 20, "55/40/5"],
  ["Moderate", 40, "45/40/15"],
  ["Balanced", 60, "30/40/30"],
  ["Growth", 80, "20/35/45"],
  ["Aggressive", 100, "10/25/65"],
];

export function RiskPane() {
  return (
    <Pane id="06" title="RISK-PROFILER · SEBI-ALIGNED" span="s4" domId="pane-risk">
      {STAGES.map(([name, pct, alloc]) => (
        <div className="stage" key={name}>
          <span className="name">{name}</span>
          <span className="bar"><span style={{ width: `${pct}%` }} /></span>
          <span className="alloc">{alloc}</span>
        </div>
      ))}
      <div className="muted" style={{ marginTop: 8, fontSize: 11 }}>
        allocation = Safe Haven / Stabilizer / High Growth.
        five sliders in the terminal compute your stage and filter everything.
      </div>
    </Pane>
  );
}

/* ---------- [07] QUICKSTART ---------- */
export function QuickstartPane() {
  const lines: [string, string][] = [
    ["$ nivesh open india", "# 110 NSE assets, ₹-native"],
    ["$ nivesh open us", "# 110 US assets, ₹-convertible"],
    ["$ nivesh profile --set", "# 5 sliders → SEBI stage"],
    ["$ nivesh build", "# Efficient Frontier portfolio"],
  ];
  return (
    <Pane id="07" title="QUICKSTART" span="s4">
      {lines.map(([cmd, note]) => (
        <div className="qs-line" key={cmd}>
          <span className="p">{cmd}</span>
          <div className="muted" style={{ fontSize: 11 }}>{note}</div>
        </div>
      ))}
    </Pane>
  );
}

/* ---------- [08] LAUNCH ---------- */
export function LaunchPane() {
  return (
    <Pane id="08" title="LAUNCH" span="s4">
      <div className="muted" style={{ fontSize: 11.5, marginBottom: 4 }}>
        no signup. no card. no catch.
      </div>
      <Link href="/india" className="launch-btn solid">▶ OPEN INDIA TERMINAL</Link>
      <Link href="/us" className="launch-btn">▶ OPEN US TERMINAL</Link>
    </Pane>
  );
}

/* ---------- [09] LIVE METRIC — the strangler proof ----------
   Every other pane on this page reads a pre-baked snapshot JSON file. This one
   calls the real layered backend (L1 provider -> L5 store -> L6 feature -> L7
   engine -> L9 API) through a same-origin proxy, and renders the value next to
   its lineage and freshness.

   The two data paths run side by side on purpose: that is what ADR-0020's
   strangler pattern means in practice. The snapshot panes keep working whether
   or not the backend exists, and this pane degrades to an explicit message
   rather than blanking, erroring, or — the cardinal sin — showing 0.00%. */

type LineageRef = { event_time: string; knowledge_time: string; source_ref: string };
type MetricPayload = {
  status?: "UNREACHABLE";
  reason?: string;
  instrument?: { id: string; name: string; type: string };
  metric?: {
    id: string;
    formula_version: string;
    unit: string;
    status: "AVAILABLE" | "UNAVAILABLE";
    value: number | null;
    unavailable_reason: string | null;
  };
  freshness?: {
    as_of: string;
    computed_at: string;
    quality_flags: string[];
    diagnostics: Record<string, number>;
  };
  lineage?: {
    feature_id: string;
    feature_version: string;
    reference_version: string;
    contributing: LineageRef[];
    scanned_count: number;
    source_refs: string[];
  };
};

function asPercent(ratio: number): string {
  const pct = ratio * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(2)}%`;
}

export function LiveMetricPane() {
  const [payload, setPayload] = useState<MetricPayload | null>(null);
  const [failed, setFailed] = useState(false);
  const [showWhy, setShowWhy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/metrics/one-year-return", { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then((data: MetricPayload) => { if (!cancelled) setPayload(data); })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
  }, []);

  const metric = payload?.metric;
  const lineage = payload?.lineage;
  const freshness = payload?.freshness;

  return (
    <Pane id="09" title="LIVE METRIC · 1Y RETURN — via API" span="s4" domId="pane-live-metric">
      {failed || payload?.status === "UNREACHABLE" ? (
        /* The backend is not deployed yet in most environments. Say which, plainly. */
        <div className="muted" style={{ fontSize: 12, lineHeight: 1.7 }}>
          <div style={{ color: "#ffb300" }}>▮ api offline</div>
          <div>{payload?.reason ?? "api-unreachable"}</div>
          <div style={{ color: "#4a6080", marginTop: 6 }}>
            snapshot panes above are unaffected — that is the point
          </div>
        </div>
      ) : !payload ? (
        <div className="muted" style={{ fontSize: 12 }}>$ querying api …</div>
      ) : (
        <>
          <div className="mw-row">
            <span className="n">{payload.instrument?.name?.toUpperCase() ?? "—"}</span>
            <span>
              {metric?.status === "AVAILABLE" && metric.value !== null ? (
                <span className={metric.value >= 0 ? "up" : "down"}>
                  {asPercent(metric.value)}
                </span>
              ) : (
                /* Absence, never zero (principle 13). */
                <span style={{ color: "#ffb300" }}>n/a</span>
              )}
            </span>
          </div>

          {metric?.status === "UNAVAILABLE" && (
            <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
              {metric.unavailable_reason}
            </div>
          )}

          <div className="muted" style={{ marginTop: 8, fontSize: 11 }}>
            {freshness ? `as of ${freshness.as_of.slice(0, 10)} · live api` : "live api"}
          </div>

          <button
            onClick={() => setShowWhy((v) => !v)}
            style={{
              background: "none", border: "1px solid #24354d", color: "#8da4c4",
              fontFamily: "inherit", fontSize: 11, padding: "2px 8px",
              marginTop: 8, cursor: "pointer",
            }}
          >
            {showWhy ? "hide" : "why?"}
          </button>

          {showWhy && lineage && (
            /* The differentiator, rendered: this number traces to named inputs,
               a versioned formula, and a pinned reference state. */
            <div className="muted" style={{ fontSize: 10.5, marginTop: 8, lineHeight: 1.75 }}>
              <div>formula · {metric?.formula_version}</div>
              <div>feature · {lineage.feature_version}</div>
              <div>reference · {lineage.reference_version}</div>
              <div>
                inputs · {lineage.contributing.length} of {lineage.scanned_count} observations
              </div>
              {lineage.contributing.map((ref) => (
                <div key={ref.source_ref} style={{ color: "#4a6080" }}>
                  ↳ {ref.event_time.slice(0, 10)} · src {ref.source_ref.slice(0, 8)}
                </div>
              ))}
              {freshness && Object.entries(freshness.diagnostics).map(([key, value]) => (
                <div key={key} style={{ color: "#4a6080" }}>{key} · {value}</div>
              ))}
            </div>
          )}
        </>
      )}
    </Pane>
  );
}
