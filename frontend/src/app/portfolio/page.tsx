import type { Metadata } from "next";
import Link from "next/link";

import ArticleCard from "@/components/ArticleCard";
import PortfolioManager from "@/components/PortfolioManager";
import { apiFetchOrNull } from "@/lib/api";
import { requireSession } from "@/lib/guards";
import type { Portfolio } from "@/lib/types";

export const metadata: Metadata = { title: "Portfolio" };

export default async function PortfolioPage() {
  const session = await requireSession("/portfolio");

  if (!session.user.isPremium) {
    return (
      <div className="mx-auto max-w-xl rounded-xl border-2 border-dashed border-amber-300 bg-amber-50 p-8 text-center">
        <h1 className="text-2xl font-bold">Portfolio tracking is a Premium feature</h1>
        <p className="mt-2 text-slate-600">
          Track your holdings and get every interview and analysis that mentions the companies you own.
        </p>
        <Link
          href="/pricing"
          className="mt-4 inline-block rounded-md bg-emerald-600 px-4 py-2 font-semibold text-white hover:bg-emerald-700"
        >
          Upgrade to Premium
        </Link>
      </div>
    );
  }

  const portfolio = await apiFetchOrNull<Portfolio>("/me/portfolio");
  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <section>
        <h1 className="text-2xl font-bold">My portfolio</h1>
        <PortfolioManager
          initialHoldings={portfolio?.holdings ?? []}
          totalCostBasis={portfolio?.total_cost_basis ?? "0"}
        />
      </section>
      <section>
        <h2 className="text-xl font-semibold">Coverage of your holdings</h2>
        <div className="mt-4 grid gap-4">
          {portfolio?.related_articles.map((article) => <ArticleCard key={article.id} article={article} />)}
          {!portfolio?.related_articles.length && (
            <p className="rounded-md bg-white p-6 text-slate-600">No articles mention your holdings yet.</p>
          )}
        </div>
      </section>
    </div>
  );
}
