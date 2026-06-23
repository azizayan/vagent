/**
 * Client-safe env access.
 *
 * Centralizes reads from `process.env` so the rest of the app never touches it.
 * `NEXT_PUBLIC_API_URL` is baked in at build time by Next.js, so this module is
 * safe to import from both server and client components.
 */

const readApiBaseUrl = (): string => {
  const raw = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (!raw) {
    throw new Error(
      "NEXT_PUBLIC_API_URL is not set. Define it in .env (default '/api') before building.",
    );
  }
  return raw.endsWith("/") ? raw.slice(0, -1) : raw;
};

export const env = {
  apiBaseUrl: readApiBaseUrl(),
} as const;
