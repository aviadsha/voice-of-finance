"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSession } from "next-auth/react";
import { useState } from "react";

import { clientApi } from "@/lib/client-api";

interface Props {
  tier: "free" | "premium";
  currentTier?: "free" | "premium";
  signedIn: boolean;
}

export default function UpgradeButton({ tier, currentTier, signedIn }: Props) {
  const router = useRouter();
  const { update } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!signedIn) {
    return (
      <Link
        href={`/signup?callbackUrl=/pricing`}
        className="block w-full rounded-md bg-slate-900 py-2 text-center font-semibold text-white hover:bg-slate-700"
      >
        {tier === "free" ? "Sign up free" : "Sign up to upgrade"}
      </Link>
    );
  }
  if (tier === currentTier) {
    return <p className="rounded-md bg-slate-100 py-2 text-center text-sm font-semibold text-slate-600">Current plan</p>;
  }

  async function change() {
    setBusy(true);
    setError(null);
    try {
      await clientApi(tier === "premium" ? "/subscription/upgrade" : "/subscription/cancel", { method: "POST" });
      await update(); // refresh tier stored in the session
      router.refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <button
        onClick={change}
        disabled={busy}
        className={`w-full rounded-md py-2 font-semibold disabled:opacity-50 ${tier === "premium" ? "bg-emerald-600 text-white hover:bg-emerald-700" : "border border-slate-300 text-slate-700 hover:bg-slate-50"}`}
      >
        {busy ? "Please wait..." : tier === "premium" ? "Upgrade to Premium" : "Downgrade to Free"}
      </button>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </div>
  );
}
