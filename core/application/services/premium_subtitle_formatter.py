"""ASS formatter for word-timed, karaoke-style Shorts captions."""
from __future__ import annotations

from collections.abc import Sequence

from core.domain.exceptions import KaraokeFormattingError
from core.domain.value_objects.caption_ux import CaptionSafeZoneProfile
from core.domain.value_objects.subtitle_cue import SubtitleCue
from core.domain.value_objects.visual_intent import VisualIntent


class PremiumSubtitleFormatter:
    """Formats word-timed subtitle cues as safe-zone-aware ASS dialogue."""

    _ACTIVE_SETTLE_MS = 120

    _HEADER_TEMPLATE = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: KaraokeBase,Arial Black,{font_size},&H00FFFFFF,&H00FFFFFF,&H00101010,&H78000000,-1,0,0,0,100,100,0,0,1,{outline_width},2,2,{margin_left},{margin_right},{margin_v},1
Style: KaraokeActive,Arial Black,{font_size},&H0000D7FF,&H0000D7FF,&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,{outline_width},2,2,{margin_left},{margin_right},{margin_v},1
Style: VisualLabel,Arial Black,52,&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,-1,0,0,0,100,100,1,0,3,2,0,8,140,140,240,1
Style: VisualAccent,Arial Black,38,&H0000D7FF,&H0000D7FF,&H00101010,&H00000000,-1,0,0,0,100,100,1,0,1,3,1,8,140,140,320,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""

    def __init__(self, profile: CaptionSafeZoneProfile | None = None, style_name: str = "hormozi") -> None:
        self._profile = profile or CaptionSafeZoneProfile()
        self._style_name = style_name

    def format(
        self,
        cues: Sequence[SubtitleCue],
        visual_intents: Sequence[VisualIntent] = (),
    ) -> str:
        """Return an ASS document using ``\\k`` centisecond word durations.

        One base event keeps the complete phrase readable. A short overlay
        event for each word uses transparent placeholder glyphs so the active
        word stays in its original horizontal position, turns yellow, and
        scales to 110%. When the overlay ends the white base phrase is visible
        again, producing an active-word-only karaoke treatment.
        """
        events = [event for cue in cues for event in self._format_cue_events(cue)]
        events.extend(self._format_visual_explanations(visual_intents))
        font_name = "Arial Black"
        active_color = "&H0000D7FF" # Default Yellow
        outline_w = self._profile.outline_width

        style_name = getattr(self, "_style_name", "hormozi")
        if style_name == "hormozi":
            font_name = "Impact"
            active_color = "&H0000D7FF" # Gold
            outline_w = self._profile.outline_width * 1.5
        elif style_name == "mrbeast":
            font_name = "ObelixPro" # Or Komika
            active_color = "&H0000FF00" # Green
            outline_w = self._profile.outline_width * 2
        elif style_name == "cinematic":
            font_name = "Helvetica Neue"
            active_color = "&H00FFFFFF" # White
            outline_w = 0 # No outline

        header = self._HEADER_TEMPLATE.format(
            font_size=self._profile.font_size,
            outline_width=outline_w,
            margin_left=self._profile.margin_left,
            margin_right=self._profile.margin_right,
            margin_v=self._profile.canvas_height - self._profile.caption_baseline_y,
        ).replace("Arial Black", font_name).replace("&H0000D7FF", active_color)
        return header + ("\n" + "\n".join(events) if events else "\n")

    def _format_visual_explanations(
        self,
        visual_intents: Sequence[VisualIntent],
    ) -> list[str]:
        """Render concise diagram labels above captions for semantic evidence beats."""
        merged: list[tuple[int, int, tuple[str, ...], str]] = []
        for intent in visual_intents:
            if not intent.explanatory_required or not intent.overlay_labels:
                continue
            labels = tuple(intent.overlay_labels[:3])
            if (
                merged
                and merged[-1][2] == labels
                and merged[-1][3] == intent.visual_job
                and intent.start_ms <= merged[-1][1] + 50
            ):
                start_ms, _, previous_labels, visual_job = merged[-1]
                merged[-1] = (
                    start_ms,
                    intent.end_ms,
                    previous_labels,
                    visual_job,
                )
            else:
                merged.append(
                    (intent.start_ms, intent.end_ms, labels, intent.visual_job)
                )

        events: list[str] = []
        for start_ms, end_ms, labels, visual_job in merged:
            for label_index, label in enumerate(labels):
                staggered_start_ms = max(
                    start_ms,
                    min(end_ms - 10, start_ms + label_index * 90),
                )
                start = self._centiseconds_for_timestamp(staggered_start_ms)
                end = max(start + 1, self._centiseconds_for_timestamp(end_ms))
                y_position = 240 + label_index * 78
                animation = self._visual_label_animation(y_position, visual_job)
                events.append(
                    "Dialogue: 3,"
                    f"{self._format_timecode(start)},"
                    f"{self._format_timecode(end)},"
                    f"VisualLabel,,0,0,0,,{animation}{self._escape(label)}"
                )
            events.extend(
                self._format_semantic_accent(
                    start_ms,
                    end_ms,
                    labels,
                    visual_job,
                )
            )
        return events

    @staticmethod
    def _visual_label_animation(y_position: int, visual_job: str) -> str:
        horizontal_offset = -36 if visual_job in {"locate_part", "demonstrate_mechanism"} else 0
        start_x = 540 + horizontal_offset
        return (
            rf"{{\an8\move({start_x},{y_position + 34},540,{y_position},0,220)"
            rf"\fscx94\fscy94\t(0,170,\fscx104\fscy104)"
            rf"\t(170,290,\fscx100\fscy100)\fad(70,120)}}"
        )

    def _format_semantic_accent(
        self,
        start_ms: int,
        end_ms: int,
        labels: tuple[str, ...],
        visual_job: str,
    ) -> list[str]:
        symbol = {
            "locate_part": "◎",
            "demonstrate_mechanism": "→",
            "compare_states": "↔",
            "show_consequence": "↓",
            "deliver_payoff": "✓",
        }.get(visual_job, "")
        if not symbol:
            digit = next(
                (character for label in labels for character in label if character.isdigit()),
                "",
            )
            symbol = f"● {digit}" if digit else ""
        if not symbol:
            return []
        start = self._centiseconds_for_timestamp(start_ms)
        end = max(start + 1, self._centiseconds_for_timestamp(end_ms))
        accent_y = 330 + max(0, len(labels) - 1) * 78
        if visual_job == "demonstrate_mechanism":
            animation = (
                rf"{{\an8\move(455,{accent_y},625,{accent_y},120,760)"
                rf"\fad(60,140)}}"
            )
        else:
            animation = (
                rf"{{\an8\pos(540,{accent_y})\fscx82\fscy82"
                r"\t(0,180,\fscx118\fscy118)"
                r"\t(180,310,\fscx100\fscy100)\fad(60,140)}"
            )
        return [
            "Dialogue: 2,"
            f"{self._format_timecode(start)},"
            f"{self._format_timecode(end)},"
            f"VisualAccent,,0,0,0,,{animation}{symbol}"
        ]

    def _format_cue_events(self, cue: SubtitleCue) -> list[str]:
        """Create one persistent phrase plus exact-timed active overlays."""
        if not cue.words:
            raise KaraokeFormattingError(
                "Premium ASS formatting requires word-timed SubtitleCue values."
            )
        if len(cue.words) > 4:
            raise KaraokeFormattingError(
                "Premium karaoke cues must contain no more than four words."
            )

        cue_start = self._centiseconds_for_timestamp(cue.start_ms)
        cue_end = self._centiseconds_for_timestamp(cue.end_ms)
        if cue_end <= cue_start:
            cue_end = cue_start + 1
        base_text = " ".join(self._escape(word.text) for word in cue.words)
        entry_animation = (
            rf"{{\an2\move({self._profile.canvas_width // 2},"
            rf"{self._profile.caption_baseline_y + 16},"
            rf"{self._profile.canvas_width // 2},"
            rf"{self._profile.caption_baseline_y},0,140)"
            r"\blur1.1\t(0,120,\blur0)\fad(45,70)}"
        )
        events = [
            "Dialogue: 0,"
            f"{self._format_timecode(cue_start)},"
            f"{self._format_timecode(cue_end)},"
            f"KaraokeBase,,0,0,0,,{entry_animation}{base_text}"
        ]

        for active_index, word in enumerate(cue.words):
            start_centiseconds = self._centiseconds_for_timestamp(word.start_ms)
            end_centiseconds = self._centiseconds_for_timestamp(word.end_ms)
            if end_centiseconds <= start_centiseconds:
                end_centiseconds = start_centiseconds + 1
            settle_ms = min(self._ACTIVE_SETTLE_MS, word.end_ms - word.start_ms)
            scale_enabled = (
                word.end_ms - word.start_ms
                >= self._profile.minimum_scaled_emphasis_ms
            )
            overlay_text = self._active_overlay_text(
                cue,
                active_index,
                settle_ms,
                scale_enabled=scale_enabled,
            )
            events.append(
                "Dialogue: 1,"
                f"{self._format_timecode(start_centiseconds)},"
                f"{self._format_timecode(end_centiseconds)},"
                f"KaraokeActive,,0,0,0,,{overlay_text}"
            )
        return events

    def _active_overlay_text(
        self,
        cue: SubtitleCue,
        active_index: int,
        settle_ms: int,
        *,
        scale_enabled: bool,
    ) -> str:
        rendered_words: list[str] = []
        for index, word in enumerate(cue.words):
            escaped = self._escape(word.text)
            if index == active_index:
                if scale_enabled:
                    rendered_words.append(
                        rf"{{\alpha&H00&\1c&H0000D7FF&"
                        rf"\fscy{self._profile.active_scale_percent}"
                        rf"\t(0,{settle_ms},\fscy100)}}{escaped}"
                    )
                else:
                    rendered_words.append(
                        rf"{{\alpha&H00&\1c&H0000D7FF&}}{escaped}"
                    )
            else:
                rendered_words.append(rf"{{\alpha&HFF&}}{escaped}")
        return " ".join(rendered_words)

    @staticmethod
    def _centiseconds_for_timestamp(milliseconds: int) -> int:
        return (milliseconds + 5) // 10

    @staticmethod
    def _format_timecode(total_centiseconds: int) -> str:
        hours, remainder = divmod(total_centiseconds, 360_000)
        minutes, remainder = divmod(remainder, 6_000)
        seconds, centiseconds = divmod(remainder, 100)
        return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"

    @staticmethod
    def _escape(text: str) -> str:
        return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")
