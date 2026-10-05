import type { Metadata } from "next";
import { redirect } from "next/navigation";

import AuthForm from "@/components/AuthForm";
import { getSession } from "@/lib/auth";
import { safeCallbackUrl } from "@/lib/redirect";

export const metadata: Metadata = { title: "Log in" };

export default async function LoginPage(props: PageProps<"/login">) {
  const callbackUrl = safeCallbackUrl((await props.searchParams).callbackUrl);
  if (await getSession()) redirect(callbackUrl);
  return <AuthForm mode="login" callbackUrl={callbackUrl} />;
}
