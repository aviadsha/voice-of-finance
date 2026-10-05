"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { clientApi } from "@/lib/client-api";

export default function AnalystApplicationForm() {
  const router = useRouter();
  const [credentials, setCredentials] = useState("");
  const [links, setLinks] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    try {
      await clientApi("/community/analyst-applications", {
        method: "POST",
        body: JSON.stringify({ credentials, links: links || null }),
      });
      setCredentials("");
      setLinks("");
      setMessage({ ok: true, text: "Application submitted. An admin will review it shortly." });
      router.refresh();
    } catch (err) {
      setMessage({ ok: false, text: (err as Error).message });
    }
  }

  return (
    <form onSubmit={submit} className="mt-3 space-y-2">
      <textarea
        value={credentials}
        onChange={(e) => setCredentials(e.target.value)}
        placeholder="Your background, certifications (CFA, CPA...) and experience"
        className="h-28 w-full rounded-md border border-slate-300 p-2 text-sm"
        minLength={20}
        required
      />
      <input
        value={links}
        onChange={(e) => setLinks(e.target.value)}
        placeholder="LinkedIn / publications (optional)"
        className="w-full rounded-md border border-slate-300 p-2 text-sm"
      />
      <button className="rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white">Apply</button>
      {message && <p className={`text-sm ${message.ok ? "text-emerald-700" : "text-red-600"}`}>{message.text}</p>}
    </form>
  );
}
