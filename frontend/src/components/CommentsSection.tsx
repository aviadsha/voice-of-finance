"use client";

import Link from "next/link";
import { useState } from "react";

import { clientApi } from "@/lib/client-api";
import { displayName, formatDate } from "@/lib/format";
import type { Comment } from "@/lib/types";

interface Props {
  slug: string;
  initialComments: Comment[];
  signedIn: boolean;
  currentUserId?: string;
}

function CommentForm({
  slug,
  parentId,
  onCreated,
  placeholder = "Share your take...",
}: {
  slug: string;
  parentId?: string;
  onCreated: (comment: Comment) => void;
  placeholder?: string;
}) {
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!body.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const comment = await clientApi<Comment>(`/articles/${encodeURIComponent(slug)}/comments`, {
        method: "POST",
        body: JSON.stringify({ body, parent_id: parentId ?? null }),
      });
      onCreated(comment);
      setBody("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-2">
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder={placeholder}
        maxLength={5000}
        rows={parentId ? 2 : 3}
        className="w-full rounded-md border border-slate-300 p-2 text-sm"
      />
      {error && <p className="text-sm text-red-600">{error}</p>}
      <button
        disabled={busy || !body.trim()}
        className="rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
      >
        {busy ? "Posting..." : parentId ? "Reply" : "Post comment"}
      </button>
    </form>
  );
}

export default function CommentsSection({ slug, initialComments, signedIn, currentUserId }: Props) {
  const [comments, setComments] = useState<Comment[]>(initialComments);
  const [replyTo, setReplyTo] = useState<string | null>(null);
  const [myVotes, setMyVotes] = useState<Record<string, number>>({});
  const [error, setError] = useState<string | null>(null);

  const replace = (updated: Comment) => setComments((all) => all.map((c) => (c.id === updated.id ? updated : c)));

  async function vote(comment: Comment, direction: 1 | -1) {
    const value = myVotes[comment.id] === direction ? 0 : direction;
    try {
      const updated = await clientApi<Comment>(`/comments/${comment.id}/vote`, {
        method: "POST",
        body: JSON.stringify({ value }),
      });
      replace(updated);
      setMyVotes((votes) => ({ ...votes, [comment.id]: value }));
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function remove(comment: Comment) {
    try {
      await clientApi(`/comments/${comment.id}`, { method: "DELETE" });
      replace({ ...comment, is_deleted: true, body: "[deleted]" });
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const topLevel = comments.filter((c) => !c.parent_id);
  const repliesOf = (id: string) => comments.filter((c) => c.parent_id === id);

  const renderComment = (comment: Comment, depth = 0) => (
    <li key={comment.id} className={depth ? "ml-6 border-l border-slate-200 pl-4" : ""}>
      <div className="flex items-center gap-2 text-xs text-slate-500">
        <span className="font-semibold text-slate-700">{displayName(comment.user)}</span>
        {comment.user.is_verified_analyst && <span className="text-emerald-600">✔ Verified analyst</span>}
        <span>· {comment.user.reputation} rep</span>
        <span>· {formatDate(comment.created_at)}</span>
      </div>
      <p className={`mt-1 whitespace-pre-line text-sm ${comment.is_deleted ? "italic text-slate-400" : "text-slate-800"}`}>
        {comment.body}
      </p>
      {!comment.is_deleted && (
        <div className="mt-1 flex items-center gap-3 text-xs text-slate-500">
          <button
            disabled={!signedIn || comment.user.id === currentUserId}
            onClick={() => vote(comment, 1)}
            className={`disabled:opacity-40 ${myVotes[comment.id] === 1 ? "text-emerald-600" : ""}`}
            aria-label="Upvote"
          >
            ▲
          </button>
          <span className="font-semibold">{comment.score}</span>
          <button
            disabled={!signedIn || comment.user.id === currentUserId}
            onClick={() => vote(comment, -1)}
            className={`disabled:opacity-40 ${myVotes[comment.id] === -1 ? "text-red-600" : ""}`}
            aria-label="Downvote"
          >
            ▼
          </button>
          {signedIn && depth === 0 && (
            <button onClick={() => setReplyTo(replyTo === comment.id ? null : comment.id)} className="hover:underline">
              Reply
            </button>
          )}
          {comment.user.id === currentUserId && (
            <button onClick={() => remove(comment)} className="hover:underline">
              Delete
            </button>
          )}
        </div>
      )}
      {replyTo === comment.id && (
        <div className="mt-2">
          <CommentForm
            slug={slug}
            parentId={comment.id}
            placeholder="Write a reply..."
            onCreated={(created) => {
              setComments((all) => [...all, created]);
              setReplyTo(null);
            }}
          />
        </div>
      )}
      {repliesOf(comment.id).length > 0 && (
        <ul className="mt-3 space-y-3">{repliesOf(comment.id).map((reply) => renderComment(reply, depth + 1))}</ul>
      )}
    </li>
  );

  return (
    <section className="mt-12 border-t border-slate-200 pt-8">
      <h2 className="text-xl font-semibold">Discussion ({comments.filter((c) => !c.is_deleted).length})</h2>
      <div className="mt-4">
        {signedIn ? (
          <CommentForm slug={slug} onCreated={(created) => setComments((all) => [created, ...all])} />
        ) : (
          <p className="text-sm text-slate-600">
            <Link href={`/login?callbackUrl=/articles/${slug}`} className="text-emerald-700 hover:underline">
              Log in
            </Link>{" "}
            to join the discussion and build your reputation.
          </p>
        )}
      </div>
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      <ul className="mt-6 space-y-5">{topLevel.map((comment) => renderComment(comment))}</ul>
    </section>
  );
}
