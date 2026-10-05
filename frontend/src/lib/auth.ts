import type { NextAuthOptions } from "next-auth";
import { getServerSession } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";

import { authHeader, backendUrl } from "@/lib/api";
import type { TokenResponse, UserMe } from "@/lib/types";

const SESSION_MAX_AGE = 7 * 24 * 60 * 60; // matches the backend token lifetime

function toAuthUser(data: TokenResponse) {
  return {
    id: data.user.id,
    email: data.user.email,
    name: data.user.full_name ?? data.user.email,
    role: data.user.role,
    tier: data.user.tier,
    isPremium: data.user.is_premium,
    isVerifiedAnalyst: data.user.is_verified_analyst,
    accessToken: data.access_token,
  };
}

export const authOptions: NextAuthOptions = {
  session: { strategy: "jwt", maxAge: SESSION_MAX_AGE },
  pages: { signIn: "/login" },
  providers: [
    CredentialsProvider({
      name: "Email",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials.password) return null;
        const response = await fetch(backendUrl("/auth/login"), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: credentials.email, password: credentials.password }),
          cache: "no-store",
        });
        if (!response.ok) return null;
        return toAuthUser((await response.json()) as TokenResponse);
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user, trigger }) {
      if (user) {
        token.id = user.id;
        token.role = user.role;
        token.tier = user.tier;
        token.isPremium = user.isPremium;
        token.isVerifiedAnalyst = user.isVerifiedAnalyst;
        token.accessToken = user.accessToken;
      }
      // `useSession().update()` -> refresh profile (e.g. after upgrading to premium).
      if (trigger === "update" && token.accessToken) {
        const response = await fetch(backendUrl("/users/me"), {
          headers: authHeader(token.accessToken),
          cache: "no-store",
        });
        if (response.ok) {
          const me = (await response.json()) as UserMe;
          token.role = me.role;
          token.tier = me.tier;
          token.isPremium = me.is_premium;
          token.isVerifiedAnalyst = me.is_verified_analyst;
          token.name = me.full_name ?? me.email;
        }
      }
      return token;
    },
    async session({ session, token }) {
      // Never copy `token.accessToken` into the session: it would be readable from the browser.
      session.user = {
        ...session.user,
        id: token.id,
        role: token.role,
        tier: token.tier,
        isPremium: token.isPremium,
        isVerifiedAnalyst: token.isVerifiedAnalyst,
      };
      return session;
    },
  },
};

export function getSession() {
  return getServerSession(authOptions);
}
