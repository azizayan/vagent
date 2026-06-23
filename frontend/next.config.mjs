/**
 * Next.js production config.
 *
 * - `output: "standalone"` produces a minimal runtime bundle that the Docker
 *   runner stage copies in. Keeps the final image small and lets us run
 *   `node server.js` directly instead of carrying the full repo.
 * - The `/api/*` rewrite proxies browser requests to the backend container on
 *   the docker-compose network. The browser sees same-origin requests, so the
 *   Cloudflare tunnel only has to publish the frontend (port 3000) and the
 *   backend stays unexposed. Override `BACKEND_INTERNAL_URL` only if your
 *   backend service has a different name on the docker network.
 */
const backendInternalUrl = process.env.BACKEND_INTERNAL_URL || "http://backend:8000";

const contentSecurityPolicy = [
  "default-src 'self'",
  "base-uri 'self'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  "object-src 'none'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self'",
  "media-src 'self' blob:",
  "worker-src 'self' blob:",
  "connect-src 'self' https://*.daily.co wss://*.daily.co https://*.daily-video.co wss://*.daily-video.co",
].join("; ");

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: contentSecurityPolicy },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(self), geolocation=()",
          },
        ],
      },
    ];
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendInternalUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;
