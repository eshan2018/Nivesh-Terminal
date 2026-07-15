import type { Metadata } from "next";
import TerminalLanding from "@/components/terminal/TerminalLanding";

export const metadata: Metadata = {
  title: "Nivesh Terminal — Wealth Intelligence. Indian Roots. Global Vision.",
  description:
    "A free, Bloomberg-grade market analytics terminal. 220 Indian and US assets, 20 years of history, MPT portfolio builder, SIP projector, SEBI-aligned risk profiling. No paywalls. No ads. No data selling.",
};

export default function Home() {
  return <TerminalLanding />;
}
