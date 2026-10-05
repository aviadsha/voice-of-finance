import type { Metadata } from "next";

import ArticleCard from "@/components/ArticleCard";
import FollowManager from "@/components/FollowManager";
import { apiFetchOrNull } from "@/lib/api";
import { requireSession } from "@/lib/guards";
import type { ArticleListItem, Follow } from "@/lib/types";

export const metadata: Metadata = { title: "My feed" };

export default async function DashboardPage() {
  const session = await requireSession("/dashboard");
  const [follows, feed] = await Promise.all([
    apiFetchOrNull<Follow[]>("/me/follows"),
    apiFetchOrNull<ArticleListItem[]>("/me/feed?limit=50"),
  ]);

  return (
    <div className="grid gap-8 lg:grid-cols-[320px_minmax(0,1fr)]">
      <aside>
        <h1 className="text-2xl font-bold">Hi {session.user.name}</h1>
        <p className="mt-1 text-sm text-slate-500">
          Follow companies and topics to build your personalised feed.
        </p>
        <FollowManager initialFollows={follows ?? []} />
      </aside>
      <section>
        <h2 className="text-xl font-semibold">Your feed</h2>
        {feed && feed.length > 0 ? (
          <div className="mt-4 grid gap-4">
            {feed.map((article) => (
              <ArticleCard key={article.id} article={article} />
            ))}
          </div>
        ) : (
          <p className="mt-4 rounded-md bg-white p-6 text-slate-600">
            Nothing here yet. Follow a ticker such as <b>NVDA</b> or a topic such as <b>inflation</b>.
          </p>
        )}
      </section>
    </div>
  );
}
