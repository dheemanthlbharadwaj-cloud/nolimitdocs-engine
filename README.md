# nolimitdocs-engine
Engine asset storage for NoLimit Docs (soffice.wasm + soffice.data, streamed via CORS worker)

## Worker (`worker/`)
Cloudflare Worker `nolimitdocs-engine` that serves `soffice.wasm` and `soffice.data` for NoLimit Docs from the GitHub release in `ENGINE_RELEASE_URL`.
- Browsers that accept Brotli get pre-compressed files (quality 11) from the `ENGINE_KV` namespace, split into chunks under KV's 25 MB value limit: soffice.wasm 147 MB raw to 33 MB, soffice.data 100 MB raw to 16 MB (49 MB total). Others get the release file, compressed on the fly.
- To publish a new engine: compress with brotli q11 (lgwin 24), split into 24 MB chunks, `wrangler kv key put --remote` each chunk, and update `PRE` (keys and total length) in `worker/index.js`.
- Deploy: `cd worker && npx wrangler deploy`. Log the version id in nolimitdocs-app `DEPLOYS.md`.
