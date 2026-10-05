import type { Metadata } from "next";
import { redirect } from "next/navigation";

import AuthForm from "@/components/AuthForm";
import { getSession } from "@/lib/auth";
import { safeCallbackUrl } from "@/lib/redirect";

export const metadata: Metadata = { title: "Sign up" };

export default async function SignupPage(props: PageProps<"/signup">) {
  const callbackUrl = safeCallbackUrl((await props.searchParams).callbackUrl);
  if (await getSession()) redirect(callbackUrl);
  return <AuthForm mode="signup" callbackUrl={callbackUrl} />;
}
