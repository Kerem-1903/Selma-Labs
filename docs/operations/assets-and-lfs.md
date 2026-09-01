# Assets and Git LFS

SELMA Labs keeps source code and small reference material in Git. Large binary
media is tracked through Git LFS so normal clones and code review remain usable.

## Tracked with Git LFS

- Video: `.mp4`, `.mov`, `.webm`
- Audio: `.wav`, `.mp3`
- Model weights: `.pt`, `.pth`, `.ckpt`, `.safetensors`

Install Git LFS before cloning or contributing media:

```bash
git lfs install
git clone https://github.com/Kerem-1903/Selma-Labs.git
```

The quality workflow may intentionally check out pointer files without downloading
the full media library. Automated tests must create their own temporary fixtures or
skip provider-backed work explicitly; they must not silently depend on large demo
assets.

## Contribution rules

1. Do not commit generated output, caches, logs, private footage, or downloaded
   provider models unless the repository explicitly owns and documents them.
2. Add source, license, attribution, and content hashes to the appropriate asset
   manifest before contributing publishable media.
3. Prefer a reproducible download/bootstrap command for redistributable model
   weights rather than adding a new weight file.
4. Do not rewrite shared Git history to migrate binaries without a separate,
   reviewed maintenance plan.
5. Check new binary tracking with `git lfs status` before pushing.

Existing historical media remains available for reproducible Remotion demos. New
demo projects should keep only the smallest representative asset set required for
their tests and documentation.
