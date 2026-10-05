import type { NextRequest } from "next/server";

import { authHeader, backendUrl, getAccessToken } from "@/lib/api";

/**
 * Same-origin proxy to the FastAPI backend.
 *
 * Browser code calls `/api/backend/<path>`; this handler attaches the user's backend
 * access token (stored server-side in the encrypted NextAuth cookie) so it is never
 * exposed to client-side JavaScript, and avoids CORS in the browser.
 */
const SEGMENT = /^[A-Za-z0-9_-][A-Za-z0-9._-]*$/;
const MUTATING = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function isSameOrigin(origin: string, host: string | null): boolean {
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

async function proxy(request: NextRequest, ctx: RouteContext<"/api/backend/[...path]">) {
  const { path } = await ctx.params;
  if (!path.length || !path.every((segment) => SEGMENT.test(segment) && segment !== "..")) {
    return Response.json({ detail: "Invalid path" }, { status: 400 });
  }

  // CSRF defence-in-depth (the session cookie is already SameSite=Lax).
  if (MUTATING.has(request.method)) {
    const origin = request.headers.get("origin");
    if (origin && !isSameOrigin(origin, request.headers.get("host"))) {
      return Response.json({ detail: "Cross-origin request blocked" }, { status: 403 });
    }
  }

  const target = backendUrl(`/${path.join("/")}${request.nextUrl.search}`);
  const token = await getAccessToken();
  const headers: Record<string, string> = { ...authHeader(token) };
  const contentType = request.headers.get("content-type");
  if (contentType) headers["Content-Type"] = contentType;

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: MUTATING.has(request.method) ? await request.text() : undefined,
      cache: "no-store",
    });
  } catch {
    return Response.json({ detail: "Backend unavailable" }, { status: 502 });
  }

  return new Response(upstream.status === 204 ? null : upstream.body, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
  });
}

export { proxy as DELETE, proxy as GET, proxy as PATCH, proxy as POST, proxy as PUT };
