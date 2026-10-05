import type { Metadata } from "next";

import UpgradeButton from "@/components/UpgradeButton";
import { apiFetchOrNull } from "@/lib/api";
import { getSession } from "@/lib/auth";
import type { Plan } from "@/lib/types";

export const metadata: Metadata = { title: "Pricing" };

export default async function PricingPage() {
  const [plans, session] = await Promise.all([apiFetchOrNull<Plan[]>("/subscription/plans"), getSession()]);
  const currentTier = session?.user.tier;

  return (
    <div>
      <div className="text-center">
        <h1 className="text-3xl font-bold">Simple pricing</h1>
        <p className="mt-2 text-slate-600">Start free. Upgrade when you want the full picture.</p>
      </div>
      <div className="mx-auto mt-10 grid max-w-4xl gap-6 md:grid-cols-2">
        {(plans ?? []).map((plan) => (
          <div
            key={plan.tier}
            className={`rounded-2xl border bg-white p-8 shadow-sm ${plan.tier === "premium" ? "border-emerald-500 ring-2 ring-emerald-100" : "border-slate-200"}`}
          >
            <h2 className="text-xl font-semibold">{plan.name}</h2>
            <p className="mt-2 text-4xl font-bold">
              ${plan.price_monthly_usd}
              <span className="text-base font-normal text-slate-500">/month</span>
            </p>
            <ul className="mt-6 space-y-2 text-sm text-slate-700">
              {plan.features.map((feature) => (
                <li key={feature}>✔ {feature}</li>
              ))}
            </ul>
            <div className="mt-8">
              <UpgradeButton tier={plan.tier} currentTier={currentTier} signedIn={!!session} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
