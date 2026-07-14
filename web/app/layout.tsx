import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Nivesh Terminal — Wealth Intelligence",
  description:
    "Bloomberg-grade platform tracking 220 assets across US & Indian markets.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
