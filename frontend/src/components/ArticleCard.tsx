import Link from "next/link";

import { FORMAT_LABELS, displayName, formatDate } from "@/lib/format";
import type { ArticleListItem } from "@/lib/types";

export function FormatBadge({ article }: { article: Pick<ArticleListItem, "format" | "is_premium"> }) {
  return (
    <span className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wide">
      <span className="text-emerald-700">{FORMAT_LABELS[article.format]}</span>
      {article.is_premium && (
        <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10px] text-amber-800">Premium</span>
      )}
    </span>
  );
}

export function TickerList({ tickers }: { tickers: string[] }) {
  if (!tickers.length) return null;
  return (
    <div className="flex flex-wrap gap-1">
      {tickers.map((ticker) => (
        <Link
          key={ticker}
          href={`/?ticker=${encodeURIComponent(ticker)}`}
          className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs text-slate-700 hover:bg-slate-200"
        >
          ${ticker}
        </Link>
      ))}
    </div>
  );
}

export default function ArticleCard({ article }: { article: ArticleListItem }) {
  return (
    <article className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm transition hover:shadow-md">
      <div className="mb-2 flex items-center justify-between gap-2">
        <FormatBadge article={article} />
        <span className="text-xs text-slate-500">
          {formatDate(article.published_at)} · {article.reading_time_minutes} min read
        </span>
      </div>
      <h2 className="text-lg font-semibold leading-snug text-slate-900">
        <Link href={`/articles/${article.slug}`} className="hover:underline">
          {article.headline}
        </Link>
      </h2>
      <p className="mt-2 line-clamp-3 text-sm text-slate-600">{article.summary}</p>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <TickerList tickers={article.tickers} />
        {article.author && (
          <span className="text-xs text-slate-500">
            by {displayName(article.author)}
            {article.author.is_verified_analyst && <span className="ml-1 text-emerald-600">✔ Verified</span>}
          </span>
        )}
      </div>
    </article>
  );
}
