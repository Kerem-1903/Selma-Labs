"""
Typed exception hierarchy.

Only the branches needed for script generation are defined in Sprint 1.
Voice, video, subtitle, and upload branches get added in the sprints that
introduce those modules — this file grows with the roadmap, it is not
pre-built ahead of need.

Why typed exceptions instead of a generic try/except: callers (and later,
Celery's retry logic) need to distinguish "safe to retry" (timeouts, rate
limits) from "will never succeed unmodified" (auth failure, empty topic).
A single catch-all Exception can't express that distinction.
"""


class SelmaError(Exception):
    """Base class for all SELMA Labs domain/application errors."""


class ProviderError(SelmaError):
    """Base class for errors raised by external provider adapters."""


class ProviderAuthError(ProviderError):
    """Credentials are missing, invalid, or expired. Do not retry."""


class ProviderTimeoutError(ProviderError):
    """The provider did not respond in time. Safe to retry with backoff."""


class ProviderConnectionError(ProviderError):
    """Could not reach the provider at all (DNS, connection refused, network
    down) — distinct from a timeout, where a connection was made but the
    provider was too slow to respond. Safe to retry with backoff."""


class ProviderQuotaExceededError(ProviderError):
    """Rate limit or quota hit. Safe to retry with backoff."""


class InvalidVoiceConfigurationError(ProviderError):
    """The requested voice id/name or generation parameters were rejected
    by the provider as invalid. Do not retry unmodified — the configuration
    itself needs to change."""


class ScriptGenerationError(SelmaError):
    """The generated script failed validation (empty, wrong length, etc.),
    or the request to generate one was invalid. Do not retry blindly —
    inspect the message first."""


class NarrativeQualityError(SelmaError):
    """A fact-checked script broke its hook, answer, density, or payoff contract."""


class FactCheckError(SelmaError):
    """Script claims could not be sourced or failed factual verification."""


class PremiumQualityError(SelmaError):
    """A premium render failed the pre-render creative quality gate."""


class BackgroundMusicError(SelmaError):
    """No valid, licensed thematic background track could be selected."""


class AudioMixError(SelmaError):
    """Narration and background music could not be mixed safely."""


class AudioSourceError(SelmaError):
    """A local or remote audio source could not be acquired or inspected."""


class UnsupportedAudioFormatError(AudioSourceError):
    """The supplied audio source is not a supported, probeable audio file."""


class AudioLicenseError(AudioSourceError):
    """The source does not have the rights required for autonomous publishing."""


class HighlightSelectionError(SelmaError):
    """An audio asset could not produce a structurally valid highlight."""


class LowConfidenceHighlightError(HighlightSelectionError):
    """The selected highlight did not satisfy autonomous quality policy."""


class WordAlignmentError(SelmaError):
    """A transcription or forced-alignment adapter could not align words."""


class AlignmentQualityError(SelmaError):
    """Word-level timing failed a required premium subtitle quality policy."""


class CuePartitioningError(SelmaError):
    """Word timings cannot be partitioned into readable karaoke cues."""


class KaraokeFormattingError(SelmaError):
    """A word-timed subtitle cue cannot be represented safely as ASS."""


class CaptionUxError(SelmaError):
    """Caption layout or timing violates the configured mobile safe zone."""


class TrendDiscoveryError(SelmaError):
    """Trending video data could not produce a safe original topic."""


class VoiceGenerationError(SelmaError):
    """The request to generate narration was invalid (e.g. empty script
    text), or the provider's output failed validation (e.g. zero-length
    audio). Do not retry blindly — inspect the message first."""


class StorageError(SelmaError):
    """Persisting or retrieving an asset via StoragePort failed."""


class VideoSearchError(SelmaError):
    """The search request was invalid (empty query, max_results out of the
    supported range), or the provider returned zero results for an
    otherwise valid query. Do not retry blindly — inspect the message
    first."""


class AssetDownloadError(SelmaError):
    """A selected asset's binary content failed to download or validate
    (e.g. a non-200 response, or an empty body). Distinct from
    StorageError, which covers failures persisting bytes that were already
    downloaded successfully."""


class ScenePlanningError(SelmaError):
    """Raised in two situations, same dual role ScriptGenerationError plays
    for script generation: (1) the input was invalid (empty narration
    text, or an invalid VoiceTrack duration), or (2) the provider's output
    failed validation (empty scene list, a scene missing narration or
    search_keywords) -- including the case where the provider's raw
    response could not even be parsed into scenes at all (e.g. invalid
    JSON), since that's a content problem rather than a connectivity one.
    Do not retry blindly -- inspect the message first."""


class SceneAssetMatchingError(SelmaError):
    """The input to scene asset matching was invalid -- specifically, a
    ScenePlan with no scenes to match. Deliberately narrower in scope than
    ScriptGenerationError/ScenePlanningError's dual role: a single scene
    returning zero matching assets is NOT this exception -- that is a
    normal, expected business outcome recorded on the resulting
    AssetMatchPlan (see SceneAssetMatch.has_matches), not a failure. Only
    a structurally invalid request (nothing to match against at all)
    raises this."""


class RenderError(SelmaError):
    """Raised when a Timeline cannot be rendered into a video file --
    specifically: the Timeline has no clips, the narration audio path is
    missing/empty/unreadable, or the underlying render engine (FFmpeg,
    subprocess-invoked) fails or produces no output. Distinct from
    StorageError, which covers failures persisting bytes that were already
    rendered successfully. Do not retry blindly -- inspect the message
    first; an engine failure usually means a malformed input asset or a
    missing binary, not a transient condition."""


class RenderExecutionError(RenderError):
    """FFmpeg could not produce a valid Shorts render from supplied media."""


class TimelineCreationError(SelmaError):
    """Raised when a Timeline cannot be created from an AssetMatchPlan --
    specifically: the plan has no scene matches at all, or one or more
    scenes have no candidate assets (SceneAssetMatch.has_matches is False).

    Deliberately fail-fast, unlike SceneAssetMatchingError's tolerance for
    per-scene emptiness: an unmatched scene was an acceptable, recordable
    outcome for an AssetMatchPlan (ranking is exploratory), but a Timeline
    is the direct input to rendering -- a scene with no selected asset
    would become a hole in the final video (e.g. a black frame), which is
    worse than stopping now and naming exactly which scenes need
    attention. Do not retry blindly -- inspect the message first; the
    scenes it names need new/broader search keywords or a fallback asset
    before Timeline creation can succeed."""


class VisualAssetNotFoundError(SelmaError):
    """No visual candidate passed the autonomous visual-quality policy."""


class LowVisionConfidenceError(VisualAssetNotFoundError):
    """Vision analysis was too uncertain to safely choose a background asset."""


class AssetDiversityError(VisualAssetNotFoundError):
    """Every relevant candidate exceeded the perceptual reuse budget."""


class EditorialRhythmError(SelmaError):
    """A storyboard contains unresolved timing or low-motion rhythm defects."""


class PipelineRunStateError(SelmaError):
    """A durable pipeline run attempted an invalid lifecycle transition."""


class PipelineRunNotFoundError(SelmaError):
    """The requested durable pipeline run does not exist in the repository."""


class CharacterBibleStateError(SelmaError):
    """Persisted character-bible metadata is corrupt or incompatible."""


class CharacterBibleNotFoundError(SelmaError):
    """The requested character bible does not exist in the repository."""


class SubtitleGenerationError(SelmaError):
    """Raised when a SubtitleTrack cannot be generated from a ScenePlan --
    specifically: the plan has no scenes at all, or one or more scenes
    have empty/whitespace-only narration text.

    Same fail-fast posture TimelineCreationError already established for
    an analogous situation: a scene with nothing to caption would become
    either a missing cue or a fabricated one, and a fabricated cue is
    worse than stopping now and naming exactly which scene is at fault.
    Do not retry blindly -- inspect the message first; the scenes it
    names need real narration text before subtitle generation can
    succeed."""


class SubtitleTranslationError(SelmaError):
    """Raised when subtitle translation or cue synchronization fails."""


class UploadPreparationError(SelmaError):
    """Raised when a rendered video cannot become an upload-ready package."""


class PerformanceDataError(SelmaError):
    """Published-video metrics are corrupt, incompatible, or locked too long."""
