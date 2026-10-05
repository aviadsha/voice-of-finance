import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { cache } from "react";
import ReactMarkdown from "react-markdown";

import { FormatBadge, TickerList } from "@/components/ArticleCard";
import CommentsSection from "@/components/CommentsSection";
import { apiFetchOrNull } from "@/lib/api";
import { getSession } from "@/lib/auth";
import { displayName, formatDate, formatTimestamp } from "@/lib/format";
import type { Article, Comment } from "@/lib/types";

// Deduplicate the request between generateMetadata and the page (views are counted once).
const getArticle = cache((slug: string) => apiFetchOrNull<Article>(`/articles/${encodeURIComponent(slug)}`));

export async function generateMetadata(props: PageProps<"/articles/[slug]">): Promise<Metadata> {
  const { slug } = await props.params;
  const article = await getArticle(slug);
  if (!article) return { title: "Article not found" };
  return {
    title: article.headline,
    description: article.meta_description,
    keywords: [...article.tags, ...article.tickers],
    openGraph: {
      title: article.headline,
      description: article.meta_description,
      type: "article",
      publishedTime: article.published_at ?? undefined,
    },
    twitter: { card: "summary", title: article.headline, description: article.meta_description },
  };
}

export default async function ArticlePage(props: PageProps<"/articles/[slug]">) {
  const { slug } = await props.params;
  const [article, session] = await Promise.all([getArticle(slug), getSession()]);
  if (!article) notFound();
  const comments = (await apiFetchOrNull<Comment[]>(`/articles/${encodeURIComponent(slug)}/comments`)) ?? [];

  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_320px]">
      <article className="min-w-0">
        <FormatBadge article={article} />
        <h1 className="mt-2 text-3xl font-bold leading-tight text-slate-900 sm:text-4xl">{article.headline}</h1>
        <div className="mt-3 flex flex-wrap items-center gap-3 text-sm text-slate-500">
          <span>{formatDate(article.published_at)}</span>
          <span>· {article.reading_time_minutes} min read</span>
          {article.author ? (
            <span>
              · by {displayName(article.author)}
              {article.author.is_verified_analyst && <span className="ml-1 text-emerald-600">✔ Verified analyst</span>}
            </span>
          ) : (
            <span>· AI-generated from the source interview</span>
          )}
        </div>
        <div className="mt-3">
          <TickerList tickers={article.tickers} />
        </div>

        <p className="mt-6 rounded-lg bg-white p-4 text-lg text-slate-700 shadow-sm">{article.summary}</p>

        {article.is_locked ? (
          <div className="mt-8 rounded-xl border-2 border-dashed border-amber-300 bg-amber-50 p-8 text-center">
            <h2 className="text-xl font-semibold text-slate-900">This is a Premium article</h2>
            <p className="mt-2 text-slate-600">
              Upgrade to read the full {article.format === "analysis" ? "analysis" : "deep dive"}, every verified
              citation and the complete interview transcript.
            </p>
            <div className="mt-4 flex justify-center gap-3">
              <Link
                href="/pricing"
                className="rounded-md bg-emerald-600 px-4 py-2 font-semibold text-white hover:bg-emerald-700"
              >
                Go Premium
              </Link>
              {!session && (
                <Link href={`/login?callbackUrl=/articles/${slug}`} className="rounded-md px-4 py-2 text-slate-700">
                  Log in
                </Link>
              )}
            </div>
          </div>
        ) : (
          <div className="prose-article mt-6 text-slate-800">
            <ReactMarkdown>{article.content ?? ""}</ReactMarkdown>
          </div>
        )}

        {article.tags.length > 0 && (
          <div className="mt-8 flex flex-wrap gap-2">
            {article.tags.map((tag) => (
              <Link
                key={tag}
                href={`/?tag=${encodeURIComponent(tag)}`}
                className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600 hover:bg-slate-200"
              >
                #{tag}
              </Link>
            ))}
          </div>
        )}

        <CommentsSection slug={slug} initialComments={comments} signedIn={!!session} currentUserId={session?.user.id} />
      </article>

      <aside className="space-y-6">
        {article.source_url && (
          <div className="rounded-lg border border-slate-200 bg-white p-4">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Source interview</h3>
            <a href={article.source_url} target="_blank" rel="noopener noreferrer" className="mt-2 block font-medium text-emerald-700 hover:underline">
              {article.source_title ?? "Watch on YouTube"} ↗
            </a>
            {article.interview_id && (
              <Link href={`/interviews/${article.interview_id}`} className="mt-2 block text-sm text-slate-600 hover:underline">
                Key quotes &amp; insights →
              </Link>
            )}
          </div>
        )}

        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Sources &amp; citations</h3>
          {article.citation_accuracy !== null && (
            <p className="mt-1 text-xs text-slate-500">
              {Math.round(article.citation_accuracy * 100)}% of quotes verified verbatim against the transcript
            </p>
          )}
          <ul className="mt-3 space-y-3">
            {article.citations.map((citation, index) => (
              <li key={index} className="text-sm">
                <blockquote className="border-l-2 border-slate-300 pl-2 italic text-slate-700">
                  &ldquo;{citation.quote}&rdquo;
                </blockquote>
                <div className="mt-1 flex items-center gap-2 text-xs">
                  {citation.speaker && <span className="text-slate-500">— {citation.speaker}</span>}
                  <a href={citation.url} target="_blank" rel="noopener noreferrer" className="text-emerald-700 hover:underline">
                    {citation.timestamp !== null ? `▶ ${formatTimestamp(citation.timestamp)}` : "source"}
                  </a>
                  {citation.verified ? (
                    <span className="text-emerald-600" title="Found verbatim in the transcript">✔ verified</span>
                  ) : (
                    <span className="text-amber-600" title="Could not be matched verbatim">⚠ unverified</span>
                  )}
                </div>
              </li>
            ))}
            {article.citations.length === 0 && <li className="text-sm text-slate-500">No citations.</li>}
          </ul>
          {article.is_locked && (
            <p className="mt-3 text-xs text-slate-500">Premium members see every citation.</p>
          )}
        </div>
      </aside>
    </div>
  );
}
