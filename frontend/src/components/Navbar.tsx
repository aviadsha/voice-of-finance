import Link from "next/link";

import SignOutButton from "@/components/SignOutButton";
import { getSession } from "@/lib/auth";

export default async function Navbar() {
  const session = await getSession();
  const user = session?.user;
  const canIngest = user && (user.role === "admin" || (user.role === "analyst" && user.isVerifiedAnalyst));

  return (
    <header className="border-b border-slate-200 bg-white">
      <nav className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-3">
        <Link href="/" className="text-xl font-bold tracking-tight text-slate-900">
          Voice<span className="text-emerald-600">of</span>Finance
        </Link>
        <div className="flex flex-wrap items-center gap-4 text-sm font-medium text-slate-600">
          <Link href="/" className="hover:text-slate-900">
            Latest
          </Link>
          <Link href="/community" className="hover:text-slate-900">
            Community
          </Link>
          <Link href="/pricing" className="hover:text-slate-900">
            Pricing
          </Link>
          {user && (
            <>
              <Link href="/dashboard" className="hover:text-slate-900">
                My Feed
              </Link>
              <Link href="/portfolio" className="hover:text-slate-900">
                Portfolio
              </Link>
            </>
          )}
          {canIngest && (
            <Link href="/admin/ingest" className="hover:text-slate-900">
              Ingest
            </Link>
          )}
          {user ? (
            <div className="flex items-center gap-3">
              {user.isPremium ? (
                <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
                  Premium
                </span>
              ) : (
                <Link
                  href="/pricing"
                  className="rounded-full bg-emerald-600 px-3 py-1 text-xs font-semibold text-white hover:bg-emerald-700"
                >
                  Upgrade
                </Link>
              )}
              <span className="hidden text-slate-500 sm:inline">{user.name}</span>
              <SignOutButton />
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <Link href="/login" className="hover:text-slate-900">
                Log in
              </Link>
              <Link
                href="/signup"
                className="rounded-md bg-slate-900 px-3 py-1.5 text-white hover:bg-slate-700"
              >
                Sign up
              </Link>
            </div>
          )}
        </div>
      </nav>
    </header>
  );
}
