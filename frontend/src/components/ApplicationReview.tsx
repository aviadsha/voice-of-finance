"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { clientApi } from "@/lib/client-api";
import { formatDate } from "@/lib/format";
import type { AnalystApplication } from "@/lib/types";

export default function ApplicationReview({ application }: { application: AnalystApplication }) {
  const router = useRouter();
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function review(approve: boolean) {
    try {
      await clientApi(`/community/analyst-applications/${application.id}/review`, {
        method: "POST",
        body: JSON.stringify({ approve, review_notes: notes || null }),
      });
      router.refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="rounded-md bg-slate-50 p-3 text-sm">
      <p className="text-xs text-slate-500">
        {formatDate(application.created_at)} · user {application.user_id.slice(0, 8)}
      </p>
      <p className="mt-1 whitespace-pre-line">{application.credentials}</p>
      {application.links && <p className="mt-1 break-all text-slate-500">{application.links}</p>}
      <input
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Review notes"
        className="mt-2 w-full rounded border border-slate-300 p-1.5"
      />
      <div className="mt-2 flex gap-2">
        <button onClick={() => review(true)} className="rounded bg-emerald-600 px-3 py-1 text-white">
          Approve
        </button>
        <button onClick={() => review(false)} className="rounded border border-slate-300 px-3 py-1">
          Reject
        </button>
      </div>
      {error && <p className="mt-1 text-red-600">{error}</p>}
    </div>
  );
}
