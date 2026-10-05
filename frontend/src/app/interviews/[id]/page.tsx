import type { Metadata } from "next";
import Image from "next/image";
import { notFound } from "next/navigation";
import { cache } from "react";

import ArticleCard from "@/components/ArticleCard";
import { apiFetchOrNull } from "@/lib/api";
import { formatDate, formatTimestamp } from "@/lib/format";
import type { ArticleListItem, Interview, Page } from "@/lib/types";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const getInterview = cache(async (id: string) =>
  UUID_RE.test(id) ? apiFetchOrNull<Interview>(`/interviews/${id}`) : null,
);

export async function generateMetadata(props: PageProps<"/interviews/[id]">): Promise<Metadata> {
  const interview = await getInterview((await props.params).id);
  return { title: interview?.title ?? "Interview", description: interview?.summary ?? undefined };
}

function videoUrl(interview: Interview, seconds: number | null) {
  if (seconds === null) return interview.youtube_url;
  const url = new URL(interview.youtube_url);
  url.searchParams.set("t", `${Math.floor(seconds)}s`);
  return url.toString();
}

export default async function InterviewPage(props: PageProps<"/interviews/[id]">) {
  const { id } = await props.params;
  const interview = await getInterview(id);
  if (!interview) notFound();
  const articles = await apiFetchOrNull<Page<ArticleListItem>>(`/articles?interview_id=${interview.id}&limit=10`);

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_320px]">
      <article>
        <p className="text-sm text-slate-500">
          {interview.channel} {interview.published_at && `· ${formatDate(interview.published_at)}`}
          {interview.sentiment && ` · sentiment: ${interview.sentiment}`}
        </p>
        <h1 className="mt-1 text-3xl font-bold">{interview.title ?? "Processing interview…"}</h1>
        {interview.status !== "completed" && (
          <p className="mt-3 rounded bg-amber-50 p-3 text-sm text-amber-800">
            Status: {interview.status}
            {interview.error_message && ` — ${interview.error_message}`}
          </p>
        )}
        {interview.summary && <p className="mt-4 text-lg text-slate-700">{interview.summary}</p>}

        {interview.key_quotes.length > 0 && (
          <section className="mt-8">
            <h2 className="text-xl font-semibold">Key quotes</h2>
            <div className="mt-3 space-y-4">
              {interview.key_quotes.map((quote, index) => (
                <blockquote key={index} className="border-l-4 border-emerald-500 bg-white p-4">
                  <p className="italic">“{quote.quote}”</p>
                  <footer className="mt-2 text-sm text-slate-500">
                    {quote.speaker ?? "Speaker"}
                    {quote.timestamp !== null && (
                      <>
                        {" · "}
                        <a href={videoUrl(interview, quote.timestamp)} target="_blank" rel="noopener noreferrer" className="text-emerald-700 hover:underline">
                          {formatTimestamp(quote.timestamp)}
                        </a>
                      </>
                    )}
                    {quote.verified ? (
                      <span className="ml-2 text-emerald-700">✔ verified in transcript</span>
                    ) : (
                      <span className="ml-2 text-amber-700">unverified</span>
                    )}
                  </footer>
                </blockquote>
              ))}
            </div>
          </section>
        )}

        {interview.insights.length > 0 && (
          <section className="mt-8">
            <h2 className="text-xl font-semibold">Insights</h2>
            <ul className="mt-3 list-disc space-y-2 pl-5">
              {interview.insights.map((insight, index) => (
                <li key={index}>
                  {insight.insight}
                  {insight.category && <span className="ml-2 text-xs text-slate-500">({insight.category})</span>}
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="mt-8">
          <h2 className="text-xl font-semibold">Articles from this interview</h2>
          <div className="mt-3 grid gap-4">
            {articles?.items.map((article) => <ArticleCard key={article.id} article={article} />)}
            {!articles?.items.length && <p className="text-slate-500">No published articles yet.</p>}
          </div>
        </section>
      </article>

      <aside className="space-y-6">
        {interview.thumbnail_url && (
          <a href={interview.youtube_url} target="_blank" rel="noopener noreferrer">
            <Image
              src={interview.thumbnail_url}
              alt={interview.title ?? "Video thumbnail"}
              width={640}
              height={360}
              className="rounded-lg"
              unoptimized
            />
          </a>
        )}
        <a
          href={interview.youtube_url}
          target="_blank"
          rel="noopener noreferrer"
          className="block rounded-md bg-red-600 py-2 text-center font-semibold text-white hover:bg-red-700"
        >
          Watch on YouTube
        </a>
        {interview.speakers.length > 0 && (
          <div className="rounded-lg bg-white p-4">
            <h3 className="font-semibold">Speakers</h3>
            <ul className="mt-2 text-sm">
              {interview.speakers.map((s) => (
                <li key={s.name}>
                  {s.name}
                  {s.role && <span className="text-slate-500"> — {s.role}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
        {interview.companies.length > 0 && (
          <div className="rounded-lg bg-white p-4">
            <h3 className="font-semibold">Companies</h3>
            <ul className="mt-2 flex flex-wrap gap-2 text-sm">
              {interview.companies.map((c) => (
                <li key={c.name} className="rounded bg-slate-100 px-2 py-0.5">
                  {c.name} {c.ticker && <span className="font-mono text-slate-500">${c.ticker}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
        {interview.topics.length > 0 && (
          <div className="rounded-lg bg-white p-4">
            <h3 className="font-semibold">Topics</h3>
            <ul className="mt-2 flex flex-wrap gap-2 text-sm">
              {interview.topics.map((t) => (
                <li key={t.slug} className="rounded bg-slate-100 px-2 py-0.5">
                  #{t.name}
                </li>
              ))}
            </ul>
          </div>
        )}
      </aside>
    </div>
  );
}
