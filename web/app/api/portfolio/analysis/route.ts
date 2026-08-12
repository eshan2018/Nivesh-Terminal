/* Server-side proxy to POST /v1/portfolio/analysis (L9) — the M6c strangler seam.
 *
 * Same reasoning as the one-year-return proxy (ED-014), plus one specific to this
 * endpoint: **holdings are personal financial data.** They travel in a request body,
 * never a query string, so they stay out of server logs, browser history, referrer
 * headers and proxy caches. Nothing is persisted at either end.
 *
 * It must never take the site down. An unset base URL, a timeout, a non-200 or an
 * unreachable host all degrade to a body the pane renders as an explicit offline
 * state — never a 500, never a thrown exception, never a fabricated number.
 */
import { NextResponse } from "next/server";

// Do not cache: freshness is part of what this endpoint reports.
export const dynamic = "force-dynamic";

const TIMEOUT_MS = 4000;

function unreachable(reason: string) {
  // 200 with an explicit unreachable body, not an error status: the *proxy* worked,
  // and the pane needs a shape it can render rather than an exception to catch.
  return NextResponse.json({ status: "UNREACHABLE", reason }, { status: 200 });
}

export async function POST(request: Request) {
  const base = process.env.NIVESH_API_BASE_URL;
  if (!base) {
    // The expected state until the backend is deployed. Say so plainly.
    return unreachable("api-not-configured");
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return unreachable("malformed-request");
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(`${base}/v1/portfolio/analysis`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
      cache: "no-store",
    });
    if (!response.ok) return unreachable(`api-status-${response.status}`);
    // A pipe, not a mapper: the OpenAPI contract stays the single source of truth.
    return NextResponse.json(await response.json(), { status: 200 });
  } catch {
    return unreachable("api-unreachable");
  } finally {
    clearTimeout(timer);
  }
}
