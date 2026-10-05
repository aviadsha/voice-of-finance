"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { clientApi } from "@/lib/client-api";
import { FORMAT_LABELS } from "@/lib/format";
import type { ArticleFormat } from "@/lib/types";

const FORMATS = Object.keys(FORMAT_LABELS) as ArticleFormat[];

export default function IngestForm() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [formats, setFormats] = useState<ArticleFormat[]>(FORMATS);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  function toggle(format: ArticleFormat) {
    setFormats((all) => (all.includes(format) ? all.filter((f) => f !== format) : [...all, format]));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      await clientApi("/interviews", {
        method: "POST",
        body: JSON.stringify({ youtube_url: url, generate_articles: formats.length > 0, formats }),
      });
      setUrl("");
      setMessage({ ok: true, text: "Queued! Processing usually takes a few minutes." });
      router.refresh();
    } catch (err) {
      setMessage({ ok: false, text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-4 space-y-3">
      <input
        type="url"
        required
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="https://www.youtube.com/watch?v=..."
        className="w-full rounded-md border border-slate-300 px-3 py-2"
      />
      <div className="flex flex-wrap items-center gap-4 text-sm">
        <span className="text-slate-600">Generate:</span>
        {FORMATS.map((format) => (
          <label key={format} className="flex items-center gap-1">
            <input type="checkbox" checked={formats.includes(format)} onChange={() => toggle(format)} />
            {FORMAT_LABELS[format]}
          </label>
        ))}
      </div>
      <button
        disabled={busy}
        className="rounded-md bg-emerald-600 px-4 py-2 font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
      >
        {busy ? "Submitting..." : "Process interview"}
      </button>
      {message && <p className={`text-sm ${message.ok ? "text-emerald-700" : "text-red-600"}`}>{message.text}</p>}
    </form>
  );
}
