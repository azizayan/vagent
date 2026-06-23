import { env } from "@/lib/env";

export class ApiError extends Error {
  public readonly fields: Record<string, string> | null;
  public readonly retryAfterSeconds: number | null;

  constructor(
    public readonly status: number,
    public readonly body: unknown,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
    this.fields = extractFields(body);
    this.retryAfterSeconds = extractRetryAfter(body);
  }
}

function extractFields(body: unknown): Record<string, string> | null {
  if (
    typeof body === "object" &&
    body !== null &&
    "fields" in body &&
    typeof (body as { fields: unknown }).fields === "object" &&
    (body as { fields: unknown }).fields !== null
  ) {
    const raw = (body as { fields: Record<string, unknown> }).fields;
    const out: Record<string, string> = {};
    for (const [k, v] of Object.entries(raw)) {
      if (typeof v === "string") out[k] = v;
    }
    return Object.keys(out).length > 0 ? out : null;
  }
  return null;
}

function extractRetryAfter(body: unknown): number | null {
  if (
    typeof body === "object" &&
    body !== null &&
    "retry_after_seconds" in body &&
    typeof (body as { retry_after_seconds: unknown }).retry_after_seconds ===
      "number"
  ) {
    return (body as { retry_after_seconds: number }).retry_after_seconds;
  }
  return null;
}

const request = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const url = `${env.apiBaseUrl}${path.startsWith("/") ? path : `/${path}`}`;
  const res = await fetch(url, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  const text = await res.text();
  const body: unknown = text ? JSON.parse(text) : null;

  if (!res.ok) {
    const message =
      typeof body === "object" &&
      body !== null &&
      "message" in body &&
      typeof body.message === "string"
        ? body.message
        : `Request to ${path} failed: ${res.status}`;
    throw new ApiError(res.status, body, message);
  }

  return body as T;
};

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
};
