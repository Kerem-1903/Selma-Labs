# Sprint 9 Package Notes

This archive contains all **new files** from Sprint 9 (Multilingual Subtitle
Translation), placed in the correct package paths so they can be dropped
directly into the `selma-labs` project root:

- core/domain/entities/translated_subtitle_track.py
- core/domain/ports/translation_port.py
- core/application/services/subtitle_translation_service.py
- infrastructure/providers/translation/__init__.py
- infrastructure/providers/translation/claude_translation_provider.py
- infrastructure/providers/translation/caching_translation_provider.py
- scripts/translate_subtitles.py
- tests/unit/test_subtitle_translation_service.py
- tests/unit/test_claude_translation_provider.py
- tests/unit/test_caching_translation_provider.py

It also includes best-effort **reconstructed** versions of the modified
`__init__.py` / `exceptions.py` files (built from the diff context you
provided), located at their normal package paths:

- core/domain/entities/__init__.py
- core/domain/ports/__init__.py
- core/domain/exceptions.py
- core/application/services/__init__.py

⚠️ Note: `core/domain/exceptions.py` in the diff only showed the addition of
`SubtitleTranslationError`, but `claude_translation_provider.py` also imports
`ProviderAuthError`, `ProviderQuotaExceededError`, and `ProviderTimeoutError`,
which must already exist in your real codebase. I added minimal stub
definitions for these three so the reconstructed file is self-consistent —
**replace this file with your real one** if it has more content, or just
apply the diffs below by hand.

For **config/settings.py**, **config/provider_registry.py**, **README.md**,
**CURRENT_STATUS.md**, and **ARCHITECTURE_REVIEW.md** — only diffs (not full
original files) were provided, so I could not safely reconstruct the entire
file without risking overwriting unrelated content. Instead, the raw `.diff`
patches are included under `patches/`. Apply them from your project root with:

```bash
patch -p0 < patches/config_settings.py.diff
patch -p0 < patches/config_provider_registry.py.diff
patch -p0 < patches/README.md.diff
patch -p0 < patches/CURRENT_STATUS.md.diff
patch -p0 < patches/ARCHITECTURE_REVIEW.md.diff
```

(or apply them by hand — they're short.)
