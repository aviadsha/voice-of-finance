"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { signIn } from "next-auth/react";
import { useState } from "react";

import { clientApi } from "@/lib/client-api";

export default function AuthForm({ mode, callbackUrl }: { mode: "login" | "signup"; callbackUrl: string }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "signup") {
        await clientApi("/auth/signup", {
          method: "POST",
          body: JSON.stringify({ email, password, full_name: fullName || null }),
        });
      }
      const result = await signIn("credentials", { email, password, redirect: false });
      if (!result || result.error) throw new Error("Incorrect email or password");
      router.push(callbackUrl);
      router.refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const input = "mt-1 w-full rounded-md border border-slate-300 px-3 py-2";
  return (
    <div className="mx-auto max-w-md rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
      <h1 className="text-2xl font-bold">{mode === "login" ? "Welcome back" : "Create your free account"}</h1>
      <p className="mt-1 text-sm text-slate-500">
        {mode === "login"
          ? "Log in to follow companies, join discussions and read premium analysis."
          : "Free members get article summaries, a personalised feed and community access."}
      </p>
      <form onSubmit={submit} className="mt-6 space-y-4">
        {mode === "signup" && (
          <label className="block text-sm font-medium">
            Display name
            <input value={fullName} onChange={(e) => setFullName(e.target.value)} className={input} maxLength={200} />
          </label>
        )}
        <label className="block text-sm font-medium">
          Email
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={input}
            autoComplete="email"
          />
        </label>
        <label className="block text-sm font-medium">
          Password
          <input
            type="password"
            required
            minLength={mode === "signup" ? 8 : undefined}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={input}
            autoComplete={mode === "login" ? "current-password" : "new-password"}
          />
        </label>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          disabled={busy}
          className="w-full rounded-md bg-slate-900 py-2 font-semibold text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {busy ? "Please wait..." : mode === "login" ? "Log in" : "Sign up"}
        </button>
      </form>
      <p className="mt-6 text-center text-sm text-slate-600">
        {mode === "login" ? (
          <>
            New here?{" "}
            <Link href="/signup" className="text-emerald-700 hover:underline">
              Create an account
            </Link>
          </>
        ) : (
          <>
            Already a member?{" "}
            <Link href="/login" className="text-emerald-700 hover:underline">
              Log in
            </Link>
          </>
        )}
      </p>
    </div>
  );
}
