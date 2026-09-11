# Anime visual and animation readiness

SELMA has two separate production gates:

1. Visual generation runs locally and produces approved characters,
   backgrounds, poses, and start/end keyframes.
2. Animation consumes a locked episode package on a rented GPU. It does not
   invent missing story, timing, identity, or camera decisions.

Run the offline checks:

    python scripts/check_anime_readiness.py --stage visual
    python scripts/check_anime_readiness.py --stage animation --episode-root output/production/series/<series>/<episode>

Use --full-model-hash before a real visual-production batch. The normal check
uses locked file sizes for speed; the full check verifies SHA-256.

The animation worker is intentionally not committed as ready. Copy
config/production/wan2.2-worker.example.json to
config/production/wan2.2-worker.json only when a rental instance exists. Pin
the container image and model revision. Never mark a template worker READY.

An episode becomes animation-ready only when all files and non-empty asset
directories listed in anime-animation-requirements.json exist and every shot
obeys the render-manifest contract.
