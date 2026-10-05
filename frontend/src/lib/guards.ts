import "server-only";

import { redirect } from "next/navigation";

import { getSession } from "@/lib/auth";

/** Redirects anonymous visitors to the login page and returns the session otherwise. */
export async function requireSession(callbackUrl: string) {
  const session = await getSession();
  if (!session) redirect(`/login?callbackUrl=${encodeURIComponent(callbackUrl)}`);
  return session;
}
