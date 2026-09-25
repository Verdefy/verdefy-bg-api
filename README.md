# Verdefy background remover API

This replaces the low-detail `u2netp` service with `birefnet-general`, keeps the
original website-image resolution, produces a lossless transparent PNG for the
Instagram workflow, removes edge colour spill, and uses high-quality JPEG output.

## Railway settings

Replace the existing GitHub repository files with this directory and set:

- `API_SECRET` to the same secret used by `bg-tool.php`
- `BG_MODEL=birefnet-general`
- `MAX_UPLOAD_MB=20`

The first build downloads the model. The `/health` response must report
`"model":"birefnet-general"` before testing the tool.

If the Railway plan cannot hold the full model in memory, use
`BG_MODEL=birefnet-general-lite`. It is still a substantial improvement over
`u2netp`.
