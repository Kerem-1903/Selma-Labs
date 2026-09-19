"""Librosa-backed selector for high-energy short-form music highlights."""
from __future__ import annotations

import asyncio
import math

try:
    import librosa
except ImportError:  # pragma: no cover - exercised through the public error path
    librosa = None  # type: ignore[assignment]

from core.domain.entities.audio_asset import AudioAsset
from core.domain.exceptions import HighlightSelectionError
from core.domain.ports.highlight_selector_port import HighlightSelectorPort
from core.domain.value_objects.selected_highlight import SelectedHighlight


class LibrosaHighlightSelector(HighlightSelectorPort):
    """Selects the most energetic fixed-length window from an audio asset.

    RMS measures sustained loudness while onset strength rewards rhythmic
    changes. Combining them avoids selecting a loud but static segment when
    a similarly loud chorus or beat drop has stronger musical movement.
    """

    _HOP_LENGTH = 512

    async def select(
        self,
        audio_asset: AudioAsset,
        *,
        target_duration_ms: int,
    ) -> SelectedHighlight:
        """Return the highest-scoring window without blocking the event loop."""
        if target_duration_ms <= 0:
            raise HighlightSelectionError("target_duration_ms must be greater than zero.")
        if target_duration_ms > audio_asset.duration_ms:
            raise HighlightSelectionError(
                "target_duration_ms cannot exceed the source audio duration."
            )
        if librosa is None:
            raise HighlightSelectionError(
                "librosa is required for audio highlight selection but is not installed."
            )

        return await asyncio.to_thread(
            self._select_sync,
            audio_asset,
            target_duration_ms,
        )

    def _select_sync(
        self,
        audio_asset: AudioAsset,
        target_duration_ms: int,
    ) -> SelectedHighlight:
        """Run CPU-bound waveform analysis in a worker thread."""
        try:
            waveform, sample_rate = librosa.load(
                audio_asset.local_path,
                sr=None,
                mono=True,
            )
            if len(waveform) == 0 or sample_rate <= 0:
                raise HighlightSelectionError("librosa decoded an empty audio waveform.")

            rms_frames = [
                float(value)
                for value in librosa.feature.rms(
                    y=waveform,
                    hop_length=self._HOP_LENGTH,
                )[0]
            ]
            onset_frames = [
                float(value)
                for value in librosa.onset.onset_strength(
                    y=waveform,
                    sr=sample_rate,
                    hop_length=self._HOP_LENGTH,
                )
            ]
        except HighlightSelectionError:
            raise
        except Exception as exc:  # noqa: BLE001 - library failures must not leak outward
            raise HighlightSelectionError(
                f"librosa could not analyze '{audio_asset.local_path}': {exc}"
            ) from exc

        frame_count = min(len(rms_frames), len(onset_frames))
        if frame_count == 0:
            raise HighlightSelectionError("librosa produced no energy or onset frames.")

        rms = self._normalize(rms_frames[:frame_count])
        onset = self._normalize(onset_frames[:frame_count])
        # RMS is the dominant signal for sustained intensity; onset preserves
        # rhythmic lifts that often make a chorus or beat drop feel compelling.
        frame_scores = [0.70 * energy + 0.30 * rhythm for energy, rhythm in zip(rms, onset)]
        window_frames = max(
            1,
            math.ceil(target_duration_ms * sample_rate / (1_000 * self._HOP_LENGTH)),
        )
        best_index, best_score = self._best_window(frame_scores, window_frames)
        start_ms = round(best_index * self._HOP_LENGTH * 1_000 / sample_rate)
        start_ms = min(start_ms, audio_asset.duration_ms - target_duration_ms)
        end_ms = start_ms + target_duration_ms

        return SelectedHighlight(
            audio_asset_id=audio_asset.id,
            start_ms=start_ms,
            end_ms=end_ms,
            score=best_score,
            selector_used="librosa:rms-onset:v1",
            hook_type="energy_peak",
            rationale=(
                "Selected the fixed-duration window with the highest weighted "
                "RMS-energy and onset-strength score."
            ),
        )

    @staticmethod
    def _normalize(values: list[float]) -> list[float]:
        minimum = min(values)
        maximum = max(values)
        spread = maximum - minimum
        if spread <= 0:
            return [0.5 if value > 0 else 0.0 for value in values]
        return [(value - minimum) / spread for value in values]

    @staticmethod
    def _best_window(frame_scores: list[float], window_frames: int) -> tuple[int, float]:
        actual_window = min(window_frames, len(frame_scores))
        prefix_sums = [0.0]
        for score in frame_scores:
            prefix_sums.append(prefix_sums[-1] + score)

        best_index = 0
        best_average = -1.0
        for start_index in range(len(frame_scores) - actual_window + 1):
            total = prefix_sums[start_index + actual_window] - prefix_sums[start_index]
            average = total / actual_window
            if average > best_average:
                best_index = start_index
                best_average = average
        return best_index, max(0.0, min(1.0, best_average))
