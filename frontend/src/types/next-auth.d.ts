import type { DefaultSession } from "next-auth";

declare module "next-auth" {
  interface Session {
    user: {
      id: string;
      role: "user" | "analyst" | "admin";
      tier: "free" | "premium";
      isPremium: boolean;
      isVerifiedAnalyst: boolean;
    } & DefaultSession["user"];
  }

  interface User {
    id: string;
    role: "user" | "analyst" | "admin";
    tier: "free" | "premium";
    isPremium: boolean;
    isVerifiedAnalyst: boolean;
    accessToken: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    id: string;
    role: "user" | "analyst" | "admin";
    tier: "free" | "premium";
    isPremium: boolean;
    isVerifiedAnalyst: boolean;
    // Backend API token. Kept inside the encrypted session cookie and never exposed to the browser.
    accessToken: string;
  }
}
