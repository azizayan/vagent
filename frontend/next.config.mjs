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

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
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
