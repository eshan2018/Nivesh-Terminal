import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "US Terminal — Nivesh Terminal",
};

// Placeholder until the US dashboard (P3) lands.
export default function USTerminal() {
  return (
    <main
      style={{
        minHeight: "100vh",
        background: "#060a12",
        color: "#d8e2f3",
        fontFamily: "var(--font-jetbrains), monospace",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: 14,
        padding: 24,
        textAlign: "center",
      }}
    >
      <div style={{ color: "#ffb300", fontSize: "1.5rem", letterSpacing: "0.08em", textShadow: "0 0 8px rgba(255,179,0,0.4)" }}>
        ▮ US TERMINAL
      </div>
      <div style={{ color: "#8da4c4" }}>110 US assets · ₹-convertible · 20 years of history</div>
      <div style={{ color: "#4a6080", fontSize: 12 }}>
        $ status: building — overview, portfolio, charts &amp; risk modules ship next
      </div>
      <Link
        href="/"
        style={{ color: "#ffb300", textDecoration: "underline", marginTop: 10, fontSize: 13 }}
      >
        ← back to terminal
      </Link>
    </main>
  );
}
