/**
 * Route browser API requests to the FastAPI backend.
 * This configuration runs when Next.js builds the app.
 * Vercel turns the rewrite into an external origin route.
 * The browser remains on the frontend origin.
 * The backend receives the path without the API prefix.
 * Request methods and bodies pass through the rewrite.
 * Response cookies are returned to the browser.
 * The backend supplies the cookie path for the public URL.
 * The backend origin is configured in Vercel.
 * It is not a credential or an access-control boundary.
 * Browser code does not need the backend origin.
 * Changing the origin requires a new deployment.
 * Production Vercel builds must specify an HTTPS origin.
 * Local development defaults to local FastAPI.
 * The local browser client can still call FastAPI directly.
 * No API requests pass through a Vercel Function.
 * No request body is buffered by application code here.
 * Streaming depends on the hosting proxy and upstream.
 * External rewrites have a platform timeout.
 * Backend file size limits remain authoritative.
 * Do not cache private API responses at the edge.
 * Authentication remains the backend's responsibility.
 * All browser calls still go to FastAPI.
 * Azure holds the backend secrets.
 * Vercel holds only the backend origin setting.
 * This setting must not include credentials.
 * It must not include a path, query, or fragment.
 * Avoid exposing provider error details to clients.
 * The frontend and backend deploy independently.
 * Tests can point the rewrite at a fake local server.
 * No additional dependency is needed.
 * Do not use an environment file for automated tests.
 * Run npm test and npm run build to verify changes.
 * Live proxy behavior must be checked after deployment.
 */

const backend = process.env.BACKEND_ORIGIN || "http://localhost:8000";
const url = new URL(backend);
if (url.username || url.password || url.pathname !== "/" || url.search || url.hash ||
    !["http:", "https:"].includes(url.protocol) || (process.env.VERCEL && (!process.env.BACKEND_ORIGIN || url.protocol !== "https:"))) {
  throw new Error("BACKEND_ORIGIN must be a plain HTTP(S) origin; Vercel requires HTTPS.");
}

export default {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${url.origin}/:path*` }];
  },
  async headers() {
    return [{ source: "/api/:path*", headers: [{ key: "x-vercel-enable-rewrite-caching", value: "0" }] }];
  },
};
