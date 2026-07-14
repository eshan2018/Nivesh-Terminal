import fs from "node:fs";
import path from "node:path";

// Revalidate every 15 min so the page picks up fresh snapshots (matches the
// batch job cadence). This is the whole point of the snapshot architecture:
// the page reads pre-computed JSON — no per-request market fetch.
export const revalidate = 900;

type Quote = {
  ticker: string;
  label: string;
  price: number;
  chg: number;
  asof: string;
};
type Pulse = { generated_at: string; india: Quote[]; us: Quote[] };

function loadPulse(): Pulse {
  const file = path.join(process.cwd(), "public", "data", "pulse.json");
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function fmt(n: number) {
  return n.toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function Row({ q }: { q: Quote }) {
  const cls = q.chg > 0 ? "up" : q.chg < 0 ? "down" : "flat";
  const arrow = q.chg > 0 ? "▲" : q.chg < 0 ? "▼" : "—";
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "10px 0",
        borderBottom: "1px solid var(--border)",
      }}
    >
      <span style={{ fontWeight: 600 }}>{q.label}</span>
      <span style={{ display: "flex", gap: 16, alignItems: "center" }}>
        <span className="mono">{fmt(q.price)}</span>
        <span className={`mono ${cls}`} style={{ minWidth: 88, textAlign: "right" }}>
          {arrow} {Math.abs(q.chg).toFixed(2)}%
        </span>
      </span>
    </div>
  );
}

function Card({ title, sub, rows }: { title: string; sub: string; rows: Quote[] }) {
  return (
    <div
      style={{
        flex: 1,
        background: "var(--bg-surface)",
        border: "1px solid var(--border)",
        borderRadius: 10,
        padding: "28px 24px",
      }}
    >
      <h2 style={{ fontSize: "1.4rem", fontWeight: 700 }}>{title}</h2>
      <div
        style={{
          color: "var(--text-muted)",
          fontSize: "0.7rem",
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          fontWeight: 700,
          margin: "6px 0 16px",
        }}
      >
        {sub}
      </div>
      {rows.map((q) => (
        <Row key={q.ticker} q={q} />
      ))}
    </div>
  );
}

export default function Home() {
  const pulse = loadPulse();
  return (
    <main style={{ maxWidth: 1100, margin: "0 auto", padding: "64px 24px" }}>
      <div style={{ textAlign: "center", marginBottom: 48 }}>
        <h1 style={{ fontSize: "3rem", fontWeight: 800, lineHeight: 1.1 }}>
          NIVESH <span style={{ color: "var(--accent)" }}>TERMINAL</span>
        </h1>
        <p style={{ color: "var(--text-secondary)", marginTop: 12 }}>
          Wealth Intelligence. Indian Roots. Global Vision.
        </p>
        <p
          className="mono"
          style={{ color: "var(--text-muted)", fontSize: "0.72rem", marginTop: 16 }}
        >
          snapshot · {pulse.generated_at}
        </p>
      </div>
      <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
        <Card title="Indian Market" sub="NSE · BSE · Nifty 100" rows={pulse.india} />
        <Card title="US Market" sub="NYSE · NASDAQ · S&P 500" rows={pulse.us} />
      </div>
    </main>
  );
}
