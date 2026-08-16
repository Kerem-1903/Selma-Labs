# Operator-Reviewed Visual Library

Use this library when automated visual analysis is unavailable or when a
production uses owned, generated, or manually selected footage.

Each collection needs a `license_manifest.json` with `schema_version: 1`,
`operator_approved: true`, and at least one unique local clip per visual beat.
Every asset must include `file`, `attribution`, and `license`. Paths are resolved
inside the manifest directory; traversal outside it is rejected.

Run a topic with:

```powershell
python scripts/run_factory.py --topic "..." --visual-manifest assets/visuals/my-topic/license_manifest.json
```

Changing the manifest or any clip changes the durable-run fingerprint. To
replace visuals on an existing run, use `--reprocess-from VISION_SEARCH` with
`--accept-configuration-change`.
