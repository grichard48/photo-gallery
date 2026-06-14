/**
 * Photo gallery Worker.
 *
 * Serves image requests (/i/... web, /t/... thumbnails) from the R2 bucket,
 * with edge caching. Everything else (index.html, manifest.json, banner.jpg)
 * is served from the static assets bundle.
 *
 * Bindings (see wrangler.jsonc):
 *   BUCKET  - R2 bucket holding the resized images
 *   ASSETS  - static assets (the contents of dist/)
 */

const IMG_PREFIXES = ["/i/", "/t/"];
const IMG_CACHE_CONTROL = "public, max-age=604800, immutable"; // 7 days

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (IMG_PREFIXES.some((p) => path.startsWith(p))) {
      return serveImage(request, env, ctx);
    }
    // Static shell (HTML, manifest, banner) + SPA fallback.
    return env.ASSETS.fetch(request);
  },
};

async function serveImage(request, env, ctx) {
  if (request.method !== "GET" && request.method !== "HEAD") {
    return new Response("Method Not Allowed", { status: 405 });
  }

  const cache = caches.default;
  const cached = await cache.match(request);
  if (cached) return cached;

  const url = new URL(request.url);
  const key = decodeURIComponent(url.pathname.slice(1)); // strip leading "/"

  const object = await env.BUCKET.get(key);
  if (!object) {
    return new Response("Image not found", { status: 404 });
  }

  const headers = new Headers();
  object.writeHttpMetadata(headers); // content-type, etc. from stored metadata
  headers.set("etag", object.httpEtag);
  headers.set("Cache-Control", IMG_CACHE_CONTROL);

  const response = new Response(object.body, { headers });
  // Populate the edge cache for next time (HEAD responses are not cached).
  if (request.method === "GET") {
    ctx.waitUntil(cache.put(request, response.clone()));
  }
  return response;
}
