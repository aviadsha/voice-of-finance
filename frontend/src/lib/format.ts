import type { ArticleFormat } from "@/lib/types";

export const FORMAT_LABELS: Record<ArticleFormat, string> = {
  summary: "Summary",
  deep_dive: "Deep Dive",
  analysis: "Analysis",
};

export function formatDate(value: string | null): string {
  if (!value) return "";
  return new Date(value).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
}

export function formatTimestamp(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return "";
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => n.toString().padStart(2, "0");
  return h ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

export function displayName(user: { full_name: string | null; id: string }): string {
  return user.full_name || `member-${user.id.slice(0, 6)}`;
}
