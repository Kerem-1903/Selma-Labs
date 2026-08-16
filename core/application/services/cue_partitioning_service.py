"""Pure application service for grouping word timings into readable cues."""
from __future__ import annotations

from collections.abc import Sequence
from collections.abc import Callable

from core.domain.exceptions import CuePartitioningError
from core.domain.value_objects.subtitle_cue import SubtitleCue
from core.domain.value_objects.word_timing import WordTiming


class CuePartitioningService:
    """Partitions word-aligned lyrics for high-retention karaoke subtitles."""

    def __init__(
        self,
        *,
        minimum_words_per_cue: int = 2,
        maximum_words_per_cue: int = 4,
        maximum_cue_duration_ms: int = 2_200,
        line_width_validator: Callable[[Sequence[WordTiming]], bool] | None = None,
    ) -> None:
        if minimum_words_per_cue <= 0:
            raise ValueError("minimum_words_per_cue must be greater than zero.")
        if maximum_words_per_cue <= 0:
            raise ValueError("maximum_words_per_cue must be greater than zero.")
        if minimum_words_per_cue > maximum_words_per_cue:
            raise ValueError(
                "minimum_words_per_cue must not exceed maximum_words_per_cue."
            )
        if maximum_cue_duration_ms <= 0:
            raise ValueError("maximum_cue_duration_ms must be greater than zero.")
        self._minimum_words_per_cue = minimum_words_per_cue
        self._maximum_words_per_cue = maximum_words_per_cue
        self._maximum_cue_duration_ms = maximum_cue_duration_ms
        self._line_width_validator = line_width_validator

    def partition(self, word_timings: Sequence[WordTiming]) -> list[SubtitleCue]:
        """Group ordered words by count, punctuation, and on-screen duration."""
        if not word_timings:
            return []
        ordered = sorted(word_timings, key=lambda word: (word.start_ms, word.end_ms))
        cues: list[SubtitleCue] = []
        current_words: list[WordTiming] = []

        for word in ordered:
            if word.end_ms - word.start_ms > self._maximum_cue_duration_ms:
                raise CuePartitioningError(
                    f"Word '{word.text}' exceeds the maximum cue duration on its own."
                )
            if current_words and self._must_start_new_cue(current_words, word):
                width_break = (
                    self._words_fit(current_words)
                    and not self._words_fit([*current_words, word])
                )
                if (
                    len(current_words) < self._minimum_words_per_cue
                    and not width_break
                ):
                    raise CuePartitioningError(
                        "Could not form a readable subtitle cue with at least "
                        f"{self._minimum_words_per_cue} words inside the timing limit."
                    )
                cues.append(self._build_cue(current_words, len(cues) + 1))
                current_words = []

            current_words.append(word)
            if (
                self._ends_sentence(word.text)
                or (
                    self._ends_clause(word.text)
                    and len(current_words) >= self._minimum_words_per_cue
                )
            ):
                cues.append(self._build_cue(current_words, len(cues) + 1))
                current_words = []

        if current_words:
            if self._can_merge_trailing_words(cues, current_words):
                previous = cues.pop()
                cues.append(
                    self._build_cue(
                        [*previous.words, *current_words],
                        len(cues) + 1,
                    )
                )
            elif self._can_rebalance_trailing_words(cues, current_words):
                previous = cues.pop()
                borrowed_count = self._minimum_words_per_cue - len(current_words)
                split_at = len(previous.words) - borrowed_count
                cues.append(self._build_cue(previous.words[:split_at], len(cues) + 1))
                cues.append(
                    self._build_cue(
                        [*previous.words[split_at:], *current_words],
                        len(cues) + 1,
                    )
                )
            else:
                if len(current_words) < self._minimum_words_per_cue:
                    # A hard sentence boundary must never be crossed merely to
                    # satisfy the usual 2-word density preference. The
                    # formatter renders this intentional singleton without a
                    # scale pulse when its timing is very short.
                    isolated_for_width = bool(cues) and (
                        self._words_fit(current_words)
                        and not self._words_fit(
                            [*cues[-1].words, *current_words]
                        )
                    )
                    if (
                        cues
                        and not self._ends_sentence(cues[-1].words[-1].text)
                        and not isolated_for_width
                    ):
                        raise CuePartitioningError(
                            "Could not form a readable subtitle cue with at least "
                            f"{self._minimum_words_per_cue} words inside the timing limit."
                        )
                cues.append(self._build_cue(current_words, len(cues) + 1))
        return cues

    def _can_merge_trailing_words(
        self,
        cues: list[SubtitleCue],
        trailing_words: list[WordTiming],
    ) -> bool:
        """Avoid a final one-word flash when the preceding cue has room."""
        if len(trailing_words) >= self._minimum_words_per_cue or not cues:
            return False
        previous_words = cues[-1].words
        combined_count = len(previous_words) + len(trailing_words)
        combined_duration = trailing_words[-1].end_ms - previous_words[0].start_ms
        return (
            combined_count <= self._maximum_words_per_cue
            and combined_duration <= self._maximum_cue_duration_ms
            and not self._ends_sentence(previous_words[-1].text)
            and self._words_fit([*previous_words, *trailing_words])
        )

    def _can_rebalance_trailing_words(
        self,
        cues: list[SubtitleCue],
        trailing_words: list[WordTiming],
    ) -> bool:
        """Borrow words from the prior cue to turn a trailing singleton into a pair."""
        if len(trailing_words) >= self._minimum_words_per_cue or not cues:
            return False
        previous_words = cues[-1].words
        borrowed_count = self._minimum_words_per_cue - len(trailing_words)
        if len(previous_words) - borrowed_count < self._minimum_words_per_cue:
            return False
        if self._ends_sentence(previous_words[-1].text):
            return False
        split_at = len(previous_words) - borrowed_count
        rebalanced_trailing = [*previous_words[split_at:], *trailing_words]
        return (
            rebalanced_trailing[-1].end_ms - rebalanced_trailing[0].start_ms
            <= self._maximum_cue_duration_ms
            and self._words_fit(rebalanced_trailing)
        )

    def _must_start_new_cue(
        self,
        current_words: list[WordTiming],
        next_word: WordTiming,
    ) -> bool:
        if len(current_words) >= self._maximum_words_per_cue:
            return True
        if not self._words_fit([*current_words, next_word]):
            return True
        if (
            len(current_words) >= self._minimum_words_per_cue
            and self._is_conjunction(next_word.text)
        ):
            return True
        if (
            len(current_words) >= self._minimum_words_per_cue
            and next_word.start_ms - current_words[-1].end_ms >= 450
        ):
            return True
        projected_duration = next_word.end_ms - current_words[0].start_ms
        return (
            projected_duration > self._maximum_cue_duration_ms
        )

    def _words_fit(self, words: Sequence[WordTiming]) -> bool:
        return (
            self._line_width_validator is None
            or self._line_width_validator(words)
        )

    @staticmethod
    def _ends_sentence(text: str) -> bool:
        return text.rstrip().endswith((".", "?", "!"))

    @staticmethod
    def _ends_clause(text: str) -> bool:
        return text.rstrip().endswith((",", ";", ":"))

    @staticmethod
    def _is_conjunction(text: str) -> bool:
        normalized = text.casefold().strip(".,!?;:")
        return normalized in {
            "ama", "ancak", "çünkü", "fakat", "oysa", "ve", "veya",
            "but", "because", "however", "while", "whereas", "and", "or",
        }

    @staticmethod
    def _build_cue(words: list[WordTiming], index: int) -> SubtitleCue:
        return SubtitleCue.from_words(words, index=index)
