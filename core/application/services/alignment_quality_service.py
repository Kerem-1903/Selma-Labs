"""Deterministic premium quality gate for word-level alignment output."""
from __future__ import annotations

from collections.abc import Sequence

from core.domain.exceptions import AlignmentQualityError
from core.domain.value_objects.selected_highlight import SelectedHighlight
from core.domain.value_objects.word_timing import WordTiming


class AlignmentQualityService:
    """Rejects alignments that leave the audience without readable captions."""

    def __init__(
        self,
        *,
        maximum_silence_gap_ms: int = 5_000,
        minimum_coverage_ratio: float = 0.20,
    ) -> None:
        if maximum_silence_gap_ms < 0:
            raise ValueError("maximum_silence_gap_ms must not be negative.")
        if not 0.0 <= minimum_coverage_ratio <= 1.0:
            raise ValueError("minimum_coverage_ratio must be between 0.0 and 1.0.")
        self._maximum_silence_gap_ms = maximum_silence_gap_ms
        self._minimum_coverage_ratio = minimum_coverage_ratio

    def validate(
        self,
        word_timings: Sequence[WordTiming],
        highlight: SelectedHighlight,
    ) -> None:
        """Raise when timing gaps or text coverage fail premium policy.

        Timings are asset-relative. The selected highlight supplies the exact
        audio window against which leading, internal, and trailing silence are
        evaluated.
        """
        if not word_timings:
            raise AlignmentQualityError("Word alignment contains no timed words.")

        ordered = sorted(word_timings, key=lambda timing: (timing.start_ms, timing.end_ms))
        self._validate_bounds(ordered, highlight)
        self._validate_silence_gaps(ordered, highlight)
        coverage_ratio = self._coverage_ratio(ordered, highlight)
        if coverage_ratio < self._minimum_coverage_ratio:
            raise AlignmentQualityError(
                f"Word timing coverage {coverage_ratio:.3f} is below the required "
                f"ratio {self._minimum_coverage_ratio:.3f}."
            )

    @staticmethod
    def _validate_bounds(
        timings: Sequence[WordTiming], highlight: SelectedHighlight
    ) -> None:
        for timing in timings:
            if timing.start_ms < highlight.start_ms or timing.end_ms > highlight.end_ms:
                raise AlignmentQualityError(
                    "Word timing falls outside the selected highlight bounds."
                )

    def _validate_silence_gaps(
        self,
        timings: Sequence[WordTiming],
        highlight: SelectedHighlight,
    ) -> None:
        cursor = highlight.start_ms
        for timing in timings:
            if timing.start_ms - cursor > self._maximum_silence_gap_ms:
                raise AlignmentQualityError(
                    "Word alignment contains a silence gap longer than the allowed maximum."
                )
            cursor = max(cursor, timing.end_ms)
        if highlight.end_ms - cursor > self._maximum_silence_gap_ms:
            raise AlignmentQualityError(
                "Word alignment ends with a silence gap longer than the allowed maximum."
            )

    @staticmethod
    def _coverage_ratio(
        timings: Sequence[WordTiming], highlight: SelectedHighlight
    ) -> float:
        covered_ms = 0
        interval_start = timings[0].start_ms
        interval_end = timings[0].end_ms
        for timing in timings[1:]:
            if timing.start_ms <= interval_end:
                interval_end = max(interval_end, timing.end_ms)
                continue
            covered_ms += interval_end - interval_start
            interval_start, interval_end = timing.start_ms, timing.end_ms
        covered_ms += interval_end - interval_start
        return covered_ms / highlight.duration_ms
