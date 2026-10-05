import Link from "next/link";

import ArticleCard from "@/components/ArticleCard";
import { apiFetchOrNull } from "@/lib/api";
import { FORMAT_LABELS } from "@/lib/format";
import type { ArticleFormat, ArticleListItem, Page } from "@/lib/types";

const FORMATS = Object.keys(FORMAT_LABELS) as ArticleFormat[];

export default async function HomePage(props: PageProps<"/">) {
  const searchParams = await props.searchParams;
  const pick = (key: string) => (typeof searchParams[key] === "string" ? (searchParams[key] as string) : undefined);
  const format = FORMATS.find((f) => f === pick("format"));
  const ticker = pick("ticker");
  const tag = pick("tag");
  const q = pick("q");

  const params = new URLSearchParams({ limit: "30" });
  if (format) params.set("format", format);
  if (ticker) params.set("ticker", ticker);
  if (tag) params.set("tag", tag);
  if (q) params.set("q", q);
  const page = await apiFetchOrNull<Page<ArticleListItem>>(`/articles?${params}`);

  const tabClass = (active: boolean) =>
    `rounded-full px-3 py-1 text-sm ${active ? "bg-slate-900 text-white" : "bg-white text-slate-600 hover:bg-slate-100"}`;

  return (
    <div className="space-y-8">
      <section className="rounded-2xl bg-gradient-to-br from-slate-900 to-emerald-900 px-6 py-10 text-white">
        <h1 className="text-3xl font-bold sm:text-4xl">What the smartest voices in finance are saying.</h1>
        <p className="mt-3 max-w-2xl text-slate-200">
          We listen to finance interviews on YouTube so you don&apos;t have to. Our AI extracts the key quotes and
          insights, then writes fact-checked articles with timestamped links back to the source.
        </p>
        <form action="/" className="mt-6 flex max-w-lg gap-2">
          <input
            name="q"
            defaultValue={q}
            placeholder="Search headlines..."
            className="flex-1 rounded-md px-3 py-2 text-slate-900"
          />
          <button className="rounded-md bg-emerald-500 px-4 py-2 font-semibold hover:bg-emerald-400">Search</button>
        </form>
      </section>

      <div className="flex flex-wrap items-center gap-2">
        <Link href="/" className={tabClass(!format)}>
          All
        </Link>
        {FORMATS.map((f) => (
          <Link key={f} href={`/?format=${f}`} className={tabClass(format === f)}>
            {FORMAT_LABELS[f]}
          </Link>
        ))}
        {(ticker || tag || q) && (
          <span className="ml-2 text-sm text-slate-500">
            Filtered by {ticker && <b>${ticker}</b>} {tag && <b>#{tag}</b>} {q && <b>&ldquo;{q}&rdquo;</b>} ·{" "}
            <Link href="/" className="text-emerald-700 hover:underline">
              clear
            </Link>
          </span>
        )}
      </div>

      {page === null ? (
        <p className="rounded-md bg-red-50 p-4 text-red-700">
          Could not reach the Voice of Finance API. Is the backend running?
        </p>
      ) : page.items.length === 0 ? (
        <p className="rounded-md bg-white p-6 text-slate-600">
          No articles yet. Admins can ingest an interview from the <Link href="/admin/ingest">Ingest</Link> page, or run{" "}
          <code className="rounded bg-slate-100 px-1">python -m app.cli seed</code> for demo content.
        </p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {page.items.map((article) => (
            <ArticleCard key={article.id} article={article} />
          ))}
        </div>
      )}
    </div>
  );
}
