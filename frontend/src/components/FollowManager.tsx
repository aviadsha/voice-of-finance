"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { clientApi } from "@/lib/client-api";
import type { Follow } from "@/lib/types";

export default function FollowManager({ initialFollows }: { initialFollows: Follow[] }) {
  const router = useRouter();
  const [follows, setFollows] = useState(initialFollows);
  const [type, setType] = useState<Follow["follow_type"]>("company");
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function add(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const follow = await clientApi<Follow>("/me/follows", {
        method: "POST",
        body: JSON.stringify({ follow_type: type, value }),
      });
      setFollows((all) => [...all, follow]);
      setValue("");
      router.refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function remove(follow: Follow) {
    try {
      await clientApi(`/me/follows/${follow.id}`, { method: "DELETE" });
      setFollows((all) => all.filter((f) => f.id !== follow.id));
      router.refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="mt-6 rounded-lg border border-slate-200 bg-white p-4">
      <form onSubmit={add} className="flex gap-2">
        <select
          value={type}
          onChange={(e) => setType(e.target.value as Follow["follow_type"])}
          className="rounded-md border border-slate-300 px-2 text-sm"
        >
          <option value="company">Ticker</option>
          <option value="topic">Topic</option>
        </select>
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={type === "company" ? "e.g. NVDA" : "e.g. inflation"}
          className="min-w-0 flex-1 rounded-md border border-slate-300 px-2 py-1.5 text-sm"
          required
        />
        <button className="rounded-md bg-slate-900 px-3 text-sm text-white">Follow</button>
      </form>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      <ul className="mt-4 flex flex-wrap gap-2">
        {follows.map((follow) => (
          <li
            key={follow.id}
            className="flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-700"
          >
            {follow.follow_type === "company" ? `$${follow.value}` : `#${follow.value}`}
            <button onClick={() => remove(follow)} className="ml-1 text-slate-400 hover:text-red-600" aria-label="Unfollow">
              ×
            </button>
          </li>
        ))}
        {follows.length === 0 && <li className="text-sm text-slate-500">You are not following anything yet.</li>}
      </ul>
    </div>
  );
}
