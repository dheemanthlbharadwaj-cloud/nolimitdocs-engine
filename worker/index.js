const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
  "Access-Control-Max-Age": "86400"
};
// Pre-compressed engine files (brotli quality 11) stored in KV in chunks under the 25 MB value limit.
// About 49 MB on the wire in total, versus 75 MB with Cloudflare's on-the-fly compression.
const PRE = {
  "soffice.wasm": { keys: ["engine-v1/wasm.br.0", "engine-v1/wasm.br.1"], length: 32968197 },
  "soffice.data": { keys: ["engine-v1/data.br.0"], length: 16149422 }
};
const HEADERS = {
  ...CORS,
  // soffice.data is an opaque binary read with fetch().arrayBuffer(), so its MIME type does not matter to the loader.
  "Content-Type": "application/wasm",
  // Engine payloads are immutable per release tag: cache hard so repeat visits skip the download.
  "Cache-Control": "public, max-age=2592000, immutable",
  "Vary": "Accept-Encoding"
};
function streamKeys(env, keys) {
  const { readable, writable } = new TransformStream();
  (async () => {
    try {
      for (const k of keys) {
        const part = await env.ENGINE_KV.get(k, { type: "stream", cacheTtl: 86400 });
        if (!part) throw new Error("missing " + k);
        await part.pipeTo(writable, { preventClose: true });
      }
      await writable.close();
    } catch (e) { await writable.abort(e); }
  })();
  return readable;
}
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") return new Response(null, { headers: CORS });
    const file = url.pathname.replace(/^\/+/, "");
    if (file !== "soffice.wasm" && file !== "soffice.data") return new Response("not found", { status: 404 });
    const pre = PRE[file];
    if (env.ENGINE_KV && /\bbr\b/.test(request.headers.get("Accept-Encoding") || "")) {
      return new Response(request.method === "HEAD" ? null : streamKeys(env, pre.keys), {
        status: 200,
        encodeBody: "manual",
        headers: { ...HEADERS, "Content-Encoding": "br", "Content-Length": String(pre.length) }
      });
    }
    // Fallback: relay the release file; Cloudflare compresses it on the fly.
    if (!env.ENGINE_RELEASE_URL) return new Response("engine base not configured", { status: 500 });
    const upstream = await fetch(`${env.ENGINE_RELEASE_URL}/${file}`, { redirect: "follow", cf: { cacheEverything: true, cacheTtl: 2592000 } });
    if (!upstream.ok) return new Response(`upstream ${upstream.status}`, { status: 502 });
    return new Response(request.method === "HEAD" ? null : upstream.body, { status: upstream.status, headers: HEADERS });
  }
};
