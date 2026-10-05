/** Browser-side helper that talks to the backend through the `/api/backend` proxy. */
export async function clientApi<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/backend${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join(", ");
      else if (body.detail?.message) detail = body.detail.message;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}
