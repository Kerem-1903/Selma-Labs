# Licensed Music Library

Place licensed `.mp3`, `.wav`, or `.m4a` tracks in this directory and copy
`license_manifest.example.json` to `license_manifest.json`. Schema v2 requires
the source URL, commercial/YouTube permission, evidence reference, attribution
policy, and SHA-256 checksum. A checksum mismatch blocks the track. Do not add
unlicensed audio.

Topic factory runs select from this manifest automatically. You can override
the theme with `--music-theme`, select a specific manifest entry with
`--music-track`, or disable the bed with `--no-background-music`. When the
manifest or a licensed file is absent, the factory records `narration_only` and
continues without background music.

The included `Space Curiosity Bed` is generated inside the project from simple
synthesized oscillators and is recorded as an original project asset. It can be
selected explicitly with `--music-track space-curiosity-bed`.

The default bed gain is `BACKGROUND_MUSIC_VOLUME=0.16`. Final rendering applies
time-coded gain automation, speech-driven ducking, fade-in/fade-out, semantic
effects, ambience, limiting, and -14 LUFS normalization in one FFmpeg pass.
