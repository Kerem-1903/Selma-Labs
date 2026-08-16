"""
SubtitleFormatter — pure, dependency-free translation of a SubtitleTrack's
domain data into external caption-file syntax.

Lives in the application layer, not the domain layer, and not as a method
on SubtitleTrack itself -- see SubtitleTrack's own docstring for the full
reasoning. In short: SRT and WebVTT are external text formats with their
own timecode punctuation and header conventions, not domain concepts: a
frozen domain entity has no business knowing what a comma-vs-period
timecode separator is, the same way Script has no business knowing it
will eventually be serialized as an LLM API payload.

Both ``format_srt``/``format_vtt`` are ``@staticmethod``: deterministic,
no I/O, no injected dependencies, no instance state -- SubtitleFormatter
is never constructed, only called. This mirrors why SubtitleService's own
``generate()`` is a plain (non-async) method: nothing here ever awaits
anything.

Deliberately NOT a Port. See SubtitleService's module docstring (ADR-008)
for the full argument: with exactly one deterministic implementation per
format and no external system behind either method, a
``SubtitleFormatterPort`` would be a Port with no swappable boundary to
hide -- the premature abstraction this project's MVP philosophy
consistently rejects (SceneAssetMatchingService rejected the same shape
of decision for query-building; TimelineService, for asset selection).

--------------------------------------------------------------------------
Future extension point: SubtitleStyle (NOT implemented in this sprint)
--------------------------------------------------------------------------
Neither format method accepts any styling input today -- output is plain
text cues only. A future ``SubtitleStyle`` value object is anticipated
(not built) to eventually carry presentation concerns orthogonal to the
timing/text this sprint owns:

  - font family / size
  - text alignment (e.g. bottom-center vs. top-third for platforms that
    reserve bottom screen space for their own UI chrome)
  - text/background/outline colors
  - outline width, drop shadow
  - reveal animation (fade, typewriter)
  - karaoke-style per-word highlighting (would additionally require the
    word-level timing this sprint deliberately does not have -- see
    SubtitleService's module docstring)
  - platform-specific presets (e.g. a TikTok-safe-area preset vs. a
    YouTube Shorts preset)

None of this is implemented, guessed at in a schema, or referenced by any
method signature in this sprint. WebVTT's cue-settings syntax (the
``position``/``align``/``line`` attributes on a cue timing line) would be
the natural encoding target for a subset of the list above once
``SubtitleStyle`` exists; SRT has no native equivalent and would need a
platform-specific extension or would simply not support the styled
subset. This paragraph exists so a future sprint has a named landing spot
-- not to commit today's format methods to any shape they'd need to
change to support it later, since neither method reads or writes styling
data now.
"""
from __future__ import annotations

from core.domain.entities.subtitle_track import SubtitleTrack
from core.domain.value_objects.subtitle_cue import SubtitleCue


def _format_srt_timecode(seconds: float) -> str:
    """``HH:MM:SS,mmm`` -- SRT's comma-separated millisecond timecode."""
    total_ms = round(seconds * 1000)
    hours, remainder_ms = divmod(total_ms, 3_600_000)
    minutes, remainder_ms = divmod(remainder_ms, 60_000)
    secs, ms = divmod(remainder_ms, 1_000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _format_vtt_timecode(seconds: float) -> str:
    """``HH:MM:SS.mmm`` -- WebVTT's period-separated millisecond timecode."""
    total_ms = round(seconds * 1000)
    hours, remainder_ms = divmod(total_ms, 3_600_000)
    minutes, remainder_ms = divmod(remainder_ms, 60_000)
    secs, ms = divmod(remainder_ms, 1_000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"


def _format_ass_timecode(seconds: float) -> str:
    total_cs = round(seconds * 100)
    hours, remainder_cs = divmod(total_cs, 360_000)
    minutes, remainder_cs = divmod(remainder_cs, 6_000)
    secs, centiseconds = divmod(remainder_cs, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


class SubtitleFormatter:
    """Formats a SubtitleTrack's cues as SRT or WebVTT text. Stateless --
    every method is a ``@staticmethod``; this class is never
    instantiated."""

    @staticmethod
    def format_srt(track: SubtitleTrack) -> str:
        """Render ``track`` as SubRip (``.srt``) text.

        Each cue becomes a four-line block: a 1-based sequence number, a
        timecode line, the (already line-wrapped) cue text, then a blank
        line separating it from the next block -- standard SRT structure.
        Cue ``index`` values are used directly as the sequence number
        (SubtitleService.generate() already renumbers them 1..len(cues)
        across the whole track, not reset per scene).

        Returns:
            The complete ``.srt`` file content as one string, or an empty
            string if ``track`` has no cues.
        """
        blocks: list[str] = []
        for cue in track.cues:
            blocks.append(
                f"{cue.index}\n"
                f"{_format_srt_timecode(cue.start_time)} --> "
                f"{_format_srt_timecode(cue.end_time)}\n"
                f"{cue.text}\n"
            )
        return "\n".join(blocks)

    @staticmethod
    def format_vtt(track: SubtitleTrack) -> str:
        """Render ``track`` as WebVTT (``.vtt``) text.

        Starts with the mandatory ``WEBVTT`` header line followed by a
        blank line, then one cue block per cue (timecode line, text,
        blank line) -- standard WebVTT structure. Unlike SRT, WebVTT does
        not require a numeric cue identifier; none is emitted, consistent
        with keeping output minimal until SubtitleStyle-driven cue
        settings (see module docstring) give a reason to add one.

        Returns:
            The complete ``.vtt`` file content as one string. Always
            starts with the ``WEBVTT`` header followed by a blank line,
            even if ``track`` has no cues -- an empty-but-header-only file
            (``"WEBVTT\\n\\n"``) is a valid, minimal WebVTT document;
            omitting the header would not be.
        """
        blocks: list[str] = ["WEBVTT"]
        for cue in track.cues:
            blocks.append(
                f"{_format_vtt_timecode(cue.start_time)} --> "
                f"{_format_vtt_timecode(cue.end_time)}\n"
                f"{cue.text}"
            )
        return "\n\n".join(blocks) + "\n\n"

    @staticmethod
    def format_ass(track: SubtitleTrack) -> str:
        header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Premium,Arial,64,&H00FFFFFF,&H0000D7FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,80,80,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""
        events = []
        for cue in track.cues:
            text = cue.text.replace("\n", " ").replace("{", r"\{").replace("}", r"\}")
            words = text.split()
            if not words:
                continue
            emoji = SubtitleFormatter._contextual_emoji(text)
            word_duration = (cue.end_time - cue.start_time) / len(words)
            for index in range(len(words)):
                highlighted_words = list(words)
                highlighted_words[index] = (
                    r"{\c&H0000D7FF&\fscx112\fscy112}"
                    + highlighted_words[index]
                    + r"{\c&H00FFFFFF&\fscx100\fscy100}"
                )
                styled_text = (
                    r"{\fad(45,45)}"
                    + " ".join(highlighted_words)
                    + (f" {emoji}" if emoji and index == len(words) - 1 else "")
                )
                start = cue.start_time + word_duration * index
                end = cue.end_time if index == len(words) - 1 else start + word_duration
                events.append(
                    "Dialogue: 0,"
                    f"{_format_ass_timecode(start)},"
                    f"{_format_ass_timecode(end)},"
                    f"Premium,,0,0,0,,{styled_text}"
                )
        return header + ("\n" + "\n".join(events) if events else "\n")

    @staticmethod
    def _contextual_emoji(text: str) -> str:
        normalized = text.casefold()
        mappings = (
            (("ocean", "sea", "underwater"), "🌊"),
            (("space", "planet", "star"), "🚀"),
            (("fire", "heat", "volcano"), "🔥"),
            (("ice", "cold", "frozen"), "❄️"),
            (("kangaroo", "animal", "wildlife"), "🦘"),
            (("brain", "intelligence", "learn"), "🧠"),
            (("light", "glow", "bioluminescence"), "✨"),
        )
        for keywords, emoji in mappings:
            if any(keyword in normalized for keyword in keywords):
                return emoji
        return ""
