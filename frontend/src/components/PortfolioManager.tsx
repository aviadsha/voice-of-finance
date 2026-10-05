"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { clientApi } from "@/lib/client-api";
import type { Holding } from "@/lib/types";

const money = (value: number) => value.toLocaleString("en-US", { style: "currency", currency: "USD" });

export default function PortfolioManager({
  initialHoldings,
  totalCostBasis,
}: {
  initialHoldings: Holding[];
  totalCostBasis: string;
}) {
  const router = useRouter();
  const [ticker, setTicker] = useState("");
  const [shares, setShares] = useState("");
  const [cost, setCost] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await clientApi<Holding>("/me/portfolio", {
        method: "POST",
        body: JSON.stringify({ ticker, shares, average_cost: cost || null }),
      });
      setTicker("");
      setShares("");
      setCost("");
      router.refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function remove(holding: Holding) {
    try {
      await clientApi(`/me/portfolio/${holding.id}`, { method: "DELETE" });
      router.refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const input = "min-w-0 rounded-md border border-slate-300 px-2 py-1.5 text-sm";
  return (
    <div className="mt-4 space-y-4">
      <form onSubmit={save} className="grid grid-cols-[1fr_1fr_1fr_auto] gap-2">
        <input className={input} placeholder="Ticker" value={ticker} onChange={(e) => setTicker(e.target.value)} required />
        <input
          className={input}
          placeholder="Shares"
          type="number"
          step="any"
          min="0"
          value={shares}
          onChange={(e) => setShares(e.target.value)}
          required
        />
        <input
          className={input}
          placeholder="Avg cost"
          type="number"
          step="any"
          min="0"
          value={cost}
          onChange={(e) => setCost(e.target.value)}
        />
        <button className="rounded-md bg-slate-900 px-3 text-sm text-white">Save</button>
      </form>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <table className="w-full overflow-hidden rounded-lg bg-white text-sm shadow-sm">
        <thead className="bg-slate-100 text-left text-slate-600">
          <tr>
            <th className="p-2">Ticker</th>
            <th className="p-2 text-right">Shares</th>
            <th className="p-2 text-right">Avg cost</th>
            <th className="p-2 text-right">Cost basis</th>
            <th className="p-2" />
          </tr>
        </thead>
        <tbody>
          {initialHoldings.map((holding) => {
            const avg = holding.average_cost ? Number(holding.average_cost) : null;
            return (
              <tr key={holding.id} className="border-t border-slate-100">
                <td className="p-2 font-mono font-semibold">{holding.ticker}</td>
                <td className="p-2 text-right">{Number(holding.shares).toLocaleString()}</td>
                <td className="p-2 text-right">{avg !== null ? money(avg) : "—"}</td>
                <td className="p-2 text-right">{avg !== null ? money(avg * Number(holding.shares)) : "—"}</td>
                <td className="p-2 text-right">
                  <button onClick={() => remove(holding)} className="text-slate-400 hover:text-red-600">
                    Remove
                  </button>
                </td>
              </tr>
            );
          })}
          {initialHoldings.length === 0 && (
            <tr>
              <td colSpan={5} className="p-4 text-center text-slate-500">
                Add your first holding above.
              </td>
            </tr>
          )}
        </tbody>
        <tfoot>
          <tr className="border-t border-slate-200 font-semibold">
            <td className="p-2" colSpan={3}>
              Total cost basis
            </td>
            <td className="p-2 text-right">{money(Number(totalCostBasis))}</td>
            <td />
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
