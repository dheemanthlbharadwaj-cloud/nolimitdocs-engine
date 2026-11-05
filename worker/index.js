const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
  "Access-Control-Max-Age": "86400"
};
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return new Response(null, { headers: CORS });
    const file = url.pathname.replace(/^\/+/, "");
    if (file !== "soffice.wasm" && file !== "soffice.data") return new Response("not found", { status: 404 });
    if (!env.ENGINE_RELEASE_URL) return new Response("engine base not configured", { status: 500 });
    // Cache the release files at the edge so each visit does not refetch them from GitHub.
    const upstream = await fetch(`${env.ENGINE_RELEASE_URL}/${file}`, { redirect: "follow", cf: { cacheEverything: true, cacheTtl: 2592000 } });
    if (!upstream.ok) return new Response(`upstream ${upstream.status}`, { status: 502 });
    // soffice.data is an opaque binary read with fetch().arrayBuffer(), so its MIME type does not
    // matter to the loader. Cloudflare does not compress application/octet-stream but does compress
    // application/wasm, which shrinks this file from about 100 MB to about 29 MB on the wire.
    return new Response(request.method === "HEAD" ? null : upstream.body, {
      status: upstream.status,
      headers: {
        ...CORS,
        "Content-Type": "application/wasm",
        // Engine payloads are immutable per release tag: cache hard so repeat visits skip the download.
        "Cache-Control": "public, max-age=2592000, immutable"
      }
    });
  }
};
