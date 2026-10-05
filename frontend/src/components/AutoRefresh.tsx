"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/** Periodically re-renders the current server component tree (used while interviews are processing). */
export default function AutoRefresh({ intervalMs }: { intervalMs: number }) {
  const router = useRouter();
  useEffect(() => {
    const timer = setInterval(() => router.refresh(), intervalMs);
    return () => clearInterval(timer);
  }, [router, intervalMs]);
  return <p className="mt-1 text-xs text-slate-500">Processing… this page refreshes automatically.</p>;
}
