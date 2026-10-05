"use client";

import { signOut } from "next-auth/react";

export default function SignOutButton() {
  return (
    <button onClick={() => signOut({ callbackUrl: "/" })} className="text-slate-500 hover:text-slate-900">
      Log out
    </button>
  );
}
