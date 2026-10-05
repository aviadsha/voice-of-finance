/** Only allow same-site relative callback URLs (prevents open redirects). */
export function safeCallbackUrl(value: string | string[] | undefined, fallback = "/dashboard"): string {
  const url = Array.isArray(value) ? value[0] : value;
  if (!url || !url.startsWith("/") || url.startsWith("//") || url.startsWith("/\\")) return fallback;
  return url;
}
