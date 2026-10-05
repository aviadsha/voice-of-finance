import type { Metadata } from "next";
import Link from "next/link";

import AutoRefresh from "@/components/AutoRefresh";
import IngestForm from "@/components/IngestForm";
import { apiFetchOrNull } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { requireSession } from "@/lib/guards";
import type { InterviewListItem, Page } from "@/lib/types";

export const metadata: Metadata = { title: "Ingest interviews" };

const STATUS_STYLES: Record<string, string> = {
  completed: "bg-emerald-100 text-emerald-800",
  failed: "bg-red-100 text-red-800",
};

export default async function IngestPage() {
  const session = await requireSession("/admin/ingest");
  // Mirrors the backend's `require_analyst` dependency.
  const allowed =
    session.user.role === "admin" || (session.user.role === "analyst" && session.user.isVerifiedAnalyst);
  if (!allowed) {
    return (
      <p className="mx-auto max-w-xl rounded-md bg-white p-6 text-slate-600">
        Only admins and verified analysts can submit interviews for processing.
      </p>
    );
  }

  const interviews = await apiFetchOrNull<Page<InterviewListItem>>("/interviews?limit=50");
  const inProgress = (interviews?.items ?? []).some((i) => i.status !== "completed" && i.status !== "failed");

  return (
    <div className="space-y-8">
      <section className="rounded-xl border border-slate-200 bg-white p-6">
        <h1 className="text-2xl font-bold">Ingest a YouTube interview</h1>
        <p className="mt-1 text-sm text-slate-500">
          The extraction agent downloads the audio, transcribes it with Whisper and extracts topics, quotes and insights.
          The article agent then writes the selected formats with Claude.
        </p>
        <IngestForm />
      </section>

      <section>
        <h2 className="text-xl font-semibold">Interviews</h2>
        {inProgress && <AutoRefresh intervalMs={5000} />}
        <table className="mt-4 w-full overflow-hidden rounded-lg bg-white text-sm shadow-sm">
          <thead className="bg-slate-100 text-left text-slate-600">
            <tr>
              <th className="p-2">Title</th>
              <th className="p-2">Channel</th>
              <th className="p-2">Status</th>
              <th className="p-2">Submitted</th>
            </tr>
          </thead>
          <tbody>
            {(interviews?.items ?? []).map((interview) => (
              <tr key={interview.id} className="border-t border-slate-100">
                <td className="p-2">
                  <Link href={`/interviews/${interview.id}`} className="font-medium hover:underline">
                    {interview.title ?? interview.youtube_url}
                  </Link>
                </td>
                <td className="p-2 text-slate-600">{interview.channel ?? "—"}</td>
                <td className="p-2">
                  <span
                    className={`rounded px-2 py-0.5 text-xs font-semibold ${STATUS_STYLES[interview.status] ?? "bg-amber-100 text-amber-800"}`}
                  >
                    {interview.status}
                  </span>
                </td>
                <td className="p-2 text-slate-500">{formatDate(interview.created_at)}</td>
              </tr>
            ))}
            {!interviews?.items.length && (
              <tr>
                <td colSpan={4} className="p-4 text-center text-slate-500">
                  No interviews yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
