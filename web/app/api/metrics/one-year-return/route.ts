/* Server-side proxy to the Nivesh Terminal API (L9) — the strangler seam.
 *
 * Why a proxy rather than fetching the backend from the browser:
 *   - Same-origin. The browser calls /api/metrics/one-year-return on this site, so no
 *     CORS configuration is needed on the backend and none is added by this milestone.
 *   - The backend origin stays private. It is a server-side environment variable, not
 *     a NEXT_PUBLIC_ one baked into the client bundle.
 *   - The strangler stays reversible. This file is the entire coupling between the live
 *     site and the new backend; deleting it returns the site to snapshot-only.
 *
 * It must never take the site down. The API is new and may be unreachable, slow, or
 * absent entirely (NIVESH_API_BASE_URL unset in the current Vercel deployment). Every
 * such case degrades to a JSON body the pane renders as an explicit unavailable state —
 * never a 500, never a thrown exception, never a zero.
 */
import { NextResponse } from "next/server";

// Do not cache: freshness is part of what this endpoint reports.
export const dynamic = "force-dynamic";

const DEFAULT_INSTRUMENT = "reliance";
const TIMEOUT_MS = 4000;

type Unreachable = { status: "UNREACHABLE"; reason: string };

function unreachable(reason: string): NextResponse<Unreachable> {
  // 200 with an explicit unreachable body, not an error status: the *proxy* worked,
  // and the pane needs a shape it can render rather than an exception to catch.
  return NextResponse.json({ status: "UNREACHABLE", reason }, { status: 200 });
}

export async function GET(request: Request) {
  const base = process.env.NIVESH_API_BASE_URL;
  if (!base) {
    // The expected state until the backend is deployed. Say so plainly rather than
    // pretending the metric is merely missing.
    return unreachable("api-not-configured");
  }

  const instrument =
    new URL(request.url).searchParams.get("instrument") ?? DEFAULT_INSTRUMENT;

  // A hung backend must not hold a request open; the site degrades instead.
  const abort = new AbortController();
  const timer = setTimeout(() => abort.abort(), TIMEOUT_MS);

  try {
    const target = `${base.replace(/\/$/, "")}/v1/instruments/${encodeURIComponent(
      instrument
    )}/metrics/one-year-return`;

    const response = await fetch(target, {
      signal: abort.signal,
      cache: "no-store",
      headers: { accept: "application/json" },
    });

    if (response.status === 404) {
      return unreachable("unknown-instrument");
    }
    if (!response.ok) {
      return unreachable(`api-status-${response.status}`);
    }

    // Pass the DTO through unchanged. Reshaping it here would fork the contract:
    // the OpenAPI spec is the source of truth, and this file is a pipe, not a mapper.
    return NextResponse.json(await response.json(), { status: 200 });
  } catch (error) {
    const reason =
      error instanceof Error && error.name === "AbortError"
        ? "api-timeout"
        : "api-unreachable";
    return unreachable(reason);
  } finally {
    clearTimeout(timer);
  }
}
