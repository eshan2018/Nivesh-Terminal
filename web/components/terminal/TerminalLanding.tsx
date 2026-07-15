"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import "./terminal.css";
import {
  MarketWatchPane, TrendPane, SysInfoPane, ModulesPane,
  ManifestoPane, RiskPane, QuickstartPane, LaunchPane,
} from "./Panes";

/* ---------------- boot sequence ---------------- */
const BOOT_LINES: { text: string; cls?: string }[] = [
  { text: "NIVESH TERMINAL v2.0.0 — boot sequence" },
  { text: "> mounting universe .......... 220 assets", cls: "ok" },
  { text: "> history depth .............. 20Y weekly / 2Y daily", cls: "ok" },
  { text: "> fx engine (USD/INR) ........ ONLINE", cls: "ok" },
  { text: "> risk-free rate (IN 10Y) .... LOADED", cls: "ok" },
  { text: "> snapshot pipeline .......... 15-MIN REFRESH", cls: "ok" },
  { text: "> paywalls ................... NOT FOUND", cls: "warn" },
  { text: "> ads ........................ NOT FOUND", cls: "warn" },
  { text: "> data selling ............... NOT FOUND", cls: "warn" },
  { text: "READY. type `help` in the command bar, or scroll." },
];

function Boot({ onDone }: { onDone: () => void }) {
  const [visible, setVisible] = useState(0);
  const [fading, setFading] = useState(false);

  useEffect(() => {
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) { onDone(); return; }
    let i = 0;
    const id = setInterval(() => {
      i++;
      setVisible(i);
      if (i >= BOOT_LINES.length) {
        clearInterval(id);
        setTimeout(() => { setFading(true); setTimeout(onDone, 480); }, 500);
      }
    }, 170);
    const skip = () => { clearInterval(id); setFading(true); setTimeout(onDone, 300); };
    window.addEventListener("keydown", skip);
    window.addEventListener("click", skip);
    return () => {
      clearInterval(id);
      window.removeEventListener("keydown", skip);
      window.removeEventListener("click", skip);
    };
  }, [onDone]);

  return (
    <div className={`boot ${fading ? "done" : ""}`} aria-hidden={fading}>
      {BOOT_LINES.slice(0, visible).map((l, i) => (
        <div className="boot-line" key={i}>
          {l.cls ? (
            <>
              {l.text.split(/(?<=\.\.\.\s?)/)[0]}
              <span className={l.cls}>{l.text.match(/[A-Z0-9 \-]+$/)?.[0] ?? ""}</span>
            </>
          ) : l.text}
        </div>
      ))}
      {visible < BOOT_LINES.length && <span className="cursor" />}
      <div className="boot-skip">press any key to skip</div>
    </div>
  );
}

/* ---------------- status bar ---------------- */
function useISTClock() {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    const t = () => setNow(new Date());
    t();
    const id = setInterval(t, 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

function marketStatus(now: Date | null) {
  if (!now) return { nse: false, nyse: false };
  const ist = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const day = ist.getDay(); // 0 Sun
  const mins = ist.getHours() * 60 + ist.getMinutes();
  const weekday = day >= 1 && day <= 5;
  const nse = weekday && mins >= 555 && mins <= 930;          // 09:15–15:30 IST
  const nyse = weekday && (mins >= 1140 || mins <= 90);       // 19:00–01:30 IST (approx, DST varies)
  return { nse, nyse };
}

function StatusBar() {
  const now = useISTClock();
  const { nse, nyse } = marketStatus(now);
  const time = now
    ? now.toLocaleString("en-IN", {
        weekday: "short", day: "2-digit", month: "short",
        hour: "2-digit", minute: "2-digit", second: "2-digit",
        timeZone: "Asia/Kolkata",
      }) + " IST"
    : "…";
  return (
    <div className="statusbar">
      <span className="brand amber">▮ NIVESH TERMINAL</span>
      <span className="sep">│</span>
      <span suppressHydrationWarning>{time}</span>
      <span className="sep">│</span>
      <span className={nse ? "badge-open" : "badge-closed"}>NSE {nse ? "● OPEN" : "○ CLOSED"}</span>
      <span className={nyse ? "badge-open" : "badge-closed"}>NYSE {nyse ? "● OPEN" : "○ CLOSED"}</span>
      <div className="right">
        <span className="muted">220 ASSETS · 20Y · FREE</span>
        <span className="muted">v2.0</span>
      </div>
    </div>
  );
}

/* ---------------- command bar ---------------- */
const HELP = `available commands:
  india      → open the India terminal
  us         → open the US terminal
  modules    → jump to module list        markets   → jump to market watch
  manifesto  → why this exists            risk      → the SEBI risk profiler
  whoami     → identify user              clear     → clear output
  sebi       → read the disclaimer`;

export function useCommands() {
  const router = useRouter();
  return (raw: string): string => {
    const cmd = raw.trim().toLowerCase();
    const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
    switch (cmd) {
      case "": return "";
      case "help": return HELP;
      case "india": router.push("/india"); return "launching india terminal…";
      case "us": router.push("/us"); return "launching us terminal…";
      case "modules": scrollTo("pane-modules"); return "→ [04] MODULES";
      case "markets": scrollTo("pane-markets"); return "→ [01] MARKET-WATCH";
      case "manifesto": scrollTo("pane-manifesto"); return "→ [05] MANIFESTO";
      case "risk": scrollTo("pane-risk"); return "→ [06] RISK-PROFILER";
      case "whoami": return "retail_investor (no Bloomberg budget detected)";
      case "clear": return "\u0000CLEAR";
      case "sebi": return "Educational tool. Not investment advice. Not a SEBI-registered adviser. Markets carry risk — read all related documents carefully.";
      case "sudo make-money": return "permission denied: markets don't work that way";
      default: return `command not found: ${cmd} — try \`help\``;
    }
  };
}

function CommandBar() {
  const [value, setValue] = useState("");
  const [output, setOutput] = useState("");
  const [hint, setHint] = useState("");
  const run = useCommands();
  const inputRef = useRef<HTMLInputElement>(null);

  // auto-typing placeholder hints
  useEffect(() => {
    const hints = ["help", "india", "us", "modules", "manifesto"];
    let h = 0, c = 0;
    const id = setInterval(() => {
      c++;
      if (c > hints[h].length + 8) { c = 0; h = (h + 1) % hints.length; }
      setHint(hints[h].slice(0, Math.min(c, hints[h].length)));
    }, 160);
    return () => clearInterval(id);
  }, []);

  const submit = () => {
    const res = run(value);
    setOutput(res === "\u0000CLEAR" ? "" : res);
    setValue("");
  };

  return (
    <>
      <div className="cmdbar" onClick={() => inputRef.current?.focus()}>
        <span className="prompt">nivesh@terminal:~$</span>
        <input
          ref={inputRef}
          value={value}
          placeholder={hint}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          aria-label="Terminal command input"
          autoComplete="off"
          spellCheck={false}
        />
        <span className="cursor" />
      </div>
      {output && <div className="cmd-output">{output}</div>}
    </>
  );
}

/* ---------------- root ---------------- */
export default function TerminalLanding() {
  const [booted, setBooted] = useState(false);
  return (
    <div className="term-root">
      {!booted && <Boot onDone={() => setBooted(true)} />}
      <StatusBar />
      <CommandBar />
      <div className="pane-grid">
        <MarketWatchPane />
        <TrendPane />
        <SysInfoPane />
        <ModulesPane />
        <ManifestoPane />
        <RiskPane />
        <QuickstartPane />
        <LaunchPane />
      </div>
      <footer className="term-footer">
        <div className="byline">
          built by Eshan Mandloi ·{" "}
          <a href="https://www.linkedin.com/" target="_blank" rel="noopener noreferrer">linkedin</a> ·{" "}
          <a href="https://github.com/" target="_blank" rel="noopener noreferrer">github</a>
        </div>
        DISCLAIMER: Nivesh Terminal is an educational and informational tool. It is not investment
        advice, and its creator is not a SEBI-registered investment adviser. Market data may be
        delayed up to 15 minutes and is provided without warranty. Past performance does not
        guarantee future returns. Investments in securities markets are subject to market risks;
        read all related documents carefully before investing.
      </footer>
    </div>
  );
}
