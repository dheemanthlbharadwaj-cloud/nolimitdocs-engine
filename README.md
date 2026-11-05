# nolimitdocs-engine
Engine asset storage for NoLimit Docs (soffice.wasm + soffice.data, streamed via CORS worker)

## Worker (`worker/`)
Cloudflare Worker `nolimitdocs-engine` that serves `soffice.wasm` and `soffice.data` for NoLimit Docs from the GitHub release in `ENGINE_RELEASE_URL`.
- Both files are sent as `application/wasm` so Cloudflare compresses them on the fly (about 75 MB on the wire in total).
- Do NOT serve the engine from KV by concatenating chunks: tried on 2026-11-05 (version 3f6664d5), the browser intermittently received a truncated soffice.wasm and the engine failed with a CompileError. Rolled back to version 315f278c.
