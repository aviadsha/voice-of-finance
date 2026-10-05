import type { Metadata } from "next";
import Link from "next/link";

import AnalystApplicationForm from "@/components/AnalystApplicationForm";
import ApplicationReview from "@/components/ApplicationReview";
import { apiFetchOrNull } from "@/lib/api";
import { getSession } from "@/lib/auth";
import { displayName, formatDate } from "@/lib/format";
import type { AnalystApplication, UserPublic } from "@/lib/types";

export const metadata: Metadata = { title: "Community" };

export default async function CommunityPage() {
  const session = await getSession();
  const [leaders, applications] = await Promise.all([
    apiFetchOrNull<UserPublic[]>("/community/leaderboard?limit=25"),
    session ? apiFetchOrNull<AnalystApplication[]>("/community/analyst-applications") : Promise.resolve(null),
  ]);
  const isAdmin = session?.user.role === "admin";
  const pending = (applications ?? []).filter((a) => a.status === "pending");

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_360px]">
      <section>
        <h1 className="text-2xl font-bold">Community leaderboard</h1>
        <p className="mt-1 text-sm text-slate-500">
          Reputation is earned when other members upvote your comments. Top contributors can apply to become verified
          analysts and publish insights on articles.
        </p>
        <ol className="mt-6 divide-y divide-slate-100 rounded-lg bg-white shadow-sm">
          {(leaders ?? []).map((user, index) => (
            <li key={user.id} className="flex items-center gap-4 p-4">
              <span className="w-6 text-right font-mono text-slate-400">{index + 1}</span>
              <div className="flex-1">
                <p className="font-semibold">
                  {displayName(user)}
                  {user.is_verified_analyst && (
                    <span className="ml-2 rounded bg-emerald-100 px-1.5 py-0.5 text-xs text-emerald-800">
                      ✔ Verified analyst
                    </span>
                  )}
                </p>
                {user.bio && <p className="text-sm text-slate-500">{user.bio}</p>}
              </div>
              <span className="font-semibold text-slate-700">{user.reputation} rep</span>
            </li>
          ))}
          {!leaders?.length && <li className="p-4 text-slate-500">No members yet.</li>}
        </ol>
      </section>

      <aside className="space-y-6">
        {isAdmin ? (
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="font-semibold">Pending analyst applications</h2>
            <div className="mt-4 space-y-4">
              {pending.map((application) => (
                <ApplicationReview key={application.id} application={application} />
              ))}
              {pending.length === 0 && <p className="text-sm text-slate-500">Nothing to review.</p>}
            </div>
          </div>
        ) : session ? (
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="font-semibold">Become a verified analyst</h2>
            {session.user.isVerifiedAnalyst ? (
              <p className="mt-2 text-sm text-emerald-700">You are a verified analyst. Thank you!</p>
            ) : (
              <>
                <AnalystApplicationForm />
                {(applications ?? []).length > 0 && (
                  <ul className="mt-4 space-y-2 text-sm">
                    {applications!.map((a) => (
                      <li key={a.id} className="rounded bg-slate-50 p-2">
                        {formatDate(a.created_at)} — <b className="capitalize">{a.status}</b>
                        {a.review_notes && <p className="text-slate-500">{a.review_notes}</p>}
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </div>
        ) : (
          <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
            <Link href="/signup?callbackUrl=/community" className="text-emerald-700 hover:underline">
              Join the community
            </Link>{" "}
            to comment on articles and build your reputation.
          </div>
        )}
      </aside>
    </div>
  );
}
