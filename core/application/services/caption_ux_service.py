"""Deterministic mobile-caption measurement, validation, and preview sizing."""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from PIL import Image, ImageFont

from core.domain.exceptions import CaptionUxError
from core.domain.value_objects.caption_ux import (
    CaptionPreviewSample,
    CaptionSafeZoneProfile,
    CaptionUxReport,
)
from core.domain.value_objects.subtitle_cue import SubtitleCue
from core.domain.value_objects.word_timing import WordTiming


class CaptionUxService:
    """Measure the exact animated-caption envelope before paid visual stages."""

    _HARD_ENDINGS = (".", "?", "!")

    def __init__(
        self,
        profile: CaptionSafeZoneProfile | None = None,
        *,
        font_path: str | None = None,
    ) -> None:
        self.profile = profile or CaptionSafeZoneProfile()
        self._font = self._load_font(font_path, self.profile.font_size)

    def evaluate(self, cues: Sequence[SubtitleCue]) -> CaptionUxReport:
        if not cues:
            raise CaptionUxError("Caption UX validation requires subtitle cues.")
        hard_violations: list[int] = []
        horizontal_overflow: list[int] = []
        vertical_overflow: list[int] = []
        short_words: list[str] = []
        cue_widths: list[tuple[SubtitleCue, float]] = []
        widest_words: list[tuple[SubtitleCue, str, float, int]] = []

        for cue in cues:
            if any(self._ends_sentence(word.text) for word in cue.words[:-1]):
                hard_violations.append(cue.index)
            maximum_width = 0.0
            for word in cue.words:
                styled_width = self._styled_line_width(cue, word.text)
                maximum_width = max(maximum_width, styled_width)
                widest_words.append((cue, word.text, styled_width, word.start_ms))
                if word.end_ms - word.start_ms < self.profile.minimum_scaled_emphasis_ms:
                    short_words.append(word.text)
            cue_widths.append((cue, maximum_width))
            if maximum_width > self.profile.safe_width:
                horizontal_overflow.append(cue.index)
            if not self._vertical_fit():
                vertical_overflow.append(cue.index)

        maximum_styled_width = max((width for _, width in cue_widths), default=0.0)
        invalid_cues = set(hard_violations + horizontal_overflow + vertical_overflow)
        score = round(max(0.0, 10.0 - 2.0 * len(invalid_cues)), 1)
        report = CaptionUxReport(
            profile_name=self.profile.name,
            safe_width=self.profile.safe_width,
            maximum_styled_width=maximum_styled_width,
            hard_boundary_violations=tuple(hard_violations),
            horizontal_overflow_cues=tuple(horizontal_overflow),
            vertical_overflow_cues=tuple(vertical_overflow),
            short_words_without_scale=tuple(dict.fromkeys(short_words)),
            preview_samples=self._preview_samples(cue_widths, widest_words),
            score=score,
        )
        if not report.passed:
            raise CaptionUxError(
                "Mobile caption UX gate failed: "
                f"hard_boundaries={list(report.hard_boundary_violations)}, "
                f"horizontal_overflow={list(report.horizontal_overflow_cues)}, "
                f"vertical_overflow={list(report.vertical_overflow_cues)}, "
                f"score={report.score:.1f}."
            )
        return report

    def words_fit(self, words: Sequence[WordTiming]) -> bool:
        """Return whether every active-word state fits the styled safe width."""
        if not words:
            return False
        cue = SubtitleCue.from_words(list(words))
        return all(
            self._styled_line_width(cue, word.text) <= self.profile.safe_width
            for word in cue.words
        )

    def _styled_line_width(self, cue: SubtitleCue, active_text: str) -> float:
        del active_text
        phrase_width = self._text_width(" ".join(word.text for word in cue.words))
        # Active words pop vertically only. Keeping horizontal metrics stable
        # prevents the colored overlay from swallowing the spaces around it.
        outline = 2 * self.profile.outline_width
        return phrase_width + outline

    def _vertical_fit(self) -> bool:
        bbox = self._font.getbbox("AğÜç")
        glyph_height = (bbox[3] - bbox[1]) * self.profile.active_scale_percent / 100
        envelope = glyph_height + 2 * self.profile.outline_width
        top = self.profile.caption_baseline_y - envelope
        bottom = self.profile.caption_baseline_y + self.profile.outline_width
        return (
            top >= self.profile.unsafe_top
            and bottom <= self.profile.canvas_height - self.profile.unsafe_bottom
        )

    def _preview_samples(
        self,
        cue_widths: Sequence[tuple[SubtitleCue, float]],
        widest_words: Sequence[tuple[SubtitleCue, str, float, int]],
    ) -> tuple[CaptionPreviewSample, ...]:
        longest_cue, longest_width = max(cue_widths, key=lambda item: item[1])
        widest_cue, widest_word, widest_width, word_start = max(
            widest_words,
            key=lambda item: item[2],
        )
        lowest_cue = max((cue for cue, _ in cue_widths), key=lambda cue: cue.end_ms)
        lowest_width = next(width for cue, width in cue_widths if cue is lowest_cue)
        return (
            CaptionPreviewSample(
                "longest_line",
                longest_cue.index,
                (longest_cue.start_ms + longest_cue.end_ms) // 2,
                longest_cue.text,
                longest_width,
            ),
            CaptionPreviewSample(
                "widest_active_word",
                widest_cue.index,
                word_start,
                widest_word,
                widest_width,
            ),
            CaptionPreviewSample(
                "lowest_positioned_cue",
                lowest_cue.index,
                (lowest_cue.start_ms + lowest_cue.end_ms) // 2,
                lowest_cue.text,
                lowest_width,
            ),
        )

    @staticmethod
    def create_preview_variants(source_path: str) -> list[str]:
        source = Path(source_path)
        created = [str(source)]
        with Image.open(source) as image:
            for suffix, ratio in (("75", 0.75), ("small_phone", 1 / 3)):
                resized = image.resize(
                    (
                        max(1, round(image.width * ratio)),
                        max(1, round(image.height * ratio)),
                    ),
                    Image.Resampling.LANCZOS,
                )
                destination = source.with_name(f"{source.stem}_{suffix}{source.suffix}")
                resized.save(destination, quality=92)
                created.append(str(destination))
        return created

    def _text_width(self, text: str) -> float:
        return float(self._font.getlength(text))

    @classmethod
    def _ends_sentence(cls, text: str) -> bool:
        return text.rstrip().endswith(cls._HARD_ENDINGS)

    @staticmethod
    def _load_font(font_path: str | None, size: int) -> ImageFont.FreeTypeFont:
        candidates = [
            font_path,
            "C:/Windows/Fonts/ariblk.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "DejaVuSans-Bold.ttf",
        ]
        for candidate in candidates:
            if not candidate:
                continue
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
        raise CaptionUxError("No bold caption font is available for width measurement.")
