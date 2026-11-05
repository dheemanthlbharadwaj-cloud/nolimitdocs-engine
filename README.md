# nolimitdocs-engine
Engine asset storage for NoLimit Docs (soffice.wasm + soffice.data, streamed via CORS worker)

## Worker (`worker/`)
Cloudflare Worker `nolimitdocs-engine` that serves `soffice.wasm` and `soffice.data` for NoLimit Docs from the GitHub release in `ENGINE_RELEASE_URL`.
- Both files are sent as `application/wasm` so Cloudflare compresses them (soffice.data: about 100 MB raw, 27 MB on the wire).
- Deploy: `cd worker && npx wrangler deploy`. Log the version id in nolimitdocs-app `DEPLOYS.md`.
