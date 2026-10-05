import "server-only";

import { decode } from "next-auth/jwt";
import { cookies } from "next/headers";
import { unstable_rethrow } from "next/navigation";

const AUTH_SCHEME = "Bearer";
const SESSION_COOKIES = ["__Secure-next-auth.session-token", "next-auth.session-token"];

/** Base URL of the FastAPI backend, as reachable from the Next.js server. */
export function backendUrl(path = ""): string {
  const base = (process.env.API_URL ?? "http://localhost:8000").replace(/\/$/, "");
  return `${base}/api/v1${path}`;
}

export function authHeader(token: string | null | undefined): Record<string, string> {
  return token ? { Authorization: `${AUTH_SCHEME} ${token}` } : {};
}

/** Reads the backend access token from the encrypted NextAuth session cookie (server only). */
export async function getAccessToken(): Promise<string | null> {
  const store = await cookies();
  const raw = SESSION_COOKIES.map((name) => store.get(name)?.value).find(Boolean);
  if (!raw || !process.env.NEXTAUTH_SECRET) return null;
  try {
    const token = await decode({ token: raw, secret: process.env.NEXTAUTH_SECRET });
    return token?.accessToken ?? null;
  } catch {
    return null;
  }
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Server-side fetch to the backend, authenticated as the current user when signed in. */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await getAccessToken();
  const response = await fetch(backendUrl(path), {
    ...init,
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...authHeader(token), ...(init.headers ?? {}) },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* ignore */
    }
    throw new ApiError(response.status, detail);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

/** Like apiFetch but returns `null` for 404s and on network errors (useful for pages). */
export async function apiFetchOrNull<T>(path: string): Promise<T | null> {
  try {
    return await apiFetch<T>(path);
  } catch (error) {
    unstable_rethrow(error); // let Next.js handle its internal control-flow errors
    if (error instanceof ApiError && error.status !== 404) console.error(`API ${path}: ${error.message}`);
    if (!(error instanceof ApiError)) console.error(`API ${path} unreachable`, error);
    return null;
  }
}
