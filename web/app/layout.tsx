import type { Metadata } from "next";
import { JetBrains_Mono, Inter } from "next/font/google";
import "./globals.css";

// JetBrains Mono powers the terminal aesthetic (terminal.css reads --font-jetbrains).
// Inter is kept for any non-terminal surfaces (dashboards, etc.).
const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  display: "swap",
});
const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Nivesh Terminal — Wealth Intelligence. Indian Roots. Global Vision.",
  description:
    "A free, Bloomberg-grade market analytics terminal. 220 Indian and US assets, 20 years of history, MPT portfolio builder, SIP projector, SEBI-aligned risk profiling. No paywalls. No ads. No data selling.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${jetbrains.variable} ${inter.variable}`}>
      <body>{children}</body>
    </html>
  );
}
