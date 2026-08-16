"""WhisperX adapter that converts forced alignment output into WordTiming values."""
from __future__ import annotations

import asyncio
import gc
import logging
import threading
from typing import Any

try:
    import whisperx
except ImportError:  # pragma: no cover - exercised through the public error path
    whisperx = None  # type: ignore[assignment]

from core.domain.entities.audio_asset import AudioAsset
from core.domain.exceptions import WordAlignmentError
from core.domain.ports.word_alignment_port import WordAlignmentPort
from core.domain.value_objects.selected_highlight import SelectedHighlight
from core.domain.value_objects.word_timing import WordTiming


LOGGER = logging.getLogger(__name__)


class WhisperXWordAlignmentProvider(WordAlignmentPort):
    """Runs WhisperX transcription and forced alignment behind a stable port.

    Models are cached per provider instance. The lock serializes model loading
    and inference so one local GPU is not accidentally overcommitted by
    concurrent pipeline runs; scale is achieved by adding worker processes.
    """

    def __init__(
        self,
        *,
        model_name: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        batch_size: int = 4,
    ) -> None:
        if not model_name.strip():
            raise ValueError("model_name must not be empty.")
        if not device.strip():
            raise ValueError("device must not be empty.")
        if not compute_type.strip():
            raise ValueError("compute_type must not be empty.")
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero.")
        self._model_name = model_name
        self._device = device
        self._compute_type = compute_type
        self._batch_size = batch_size
        self._transcription_model: Any | None = None
        self._alignment_models: dict[str, tuple[Any, Any]] = {}
        self._inference_lock = threading.Lock()

    async def align(
        self,
        audio_asset: AudioAsset,
        highlight: SelectedHighlight,
        *,
        language: str | None = None,
        transcript: str | None = None,
    ) -> list[WordTiming]:
        """Return valid asset-relative word timings inside ``highlight``.

        WhisperX is synchronous and model-heavy. ``asyncio.to_thread`` keeps
        its loading and inference out of the caller's event loop. When a
        trusted transcript is supplied, that exact text is force-aligned
        instead of accepting Whisper's transcription as the subtitle source.
        """
        if highlight.audio_asset_id != audio_asset.id:
            raise WordAlignmentError("Highlight belongs to a different AudioAsset.")
        if whisperx is None:
            raise WordAlignmentError(
                "whisperx is required for word alignment but is not installed."
            )
        trusted_transcript = (transcript or "").strip() or None
        worker = asyncio.create_task(
            asyncio.to_thread(
                self._align_sync,
                audio_asset,
                highlight,
                language,
                trusted_transcript,
            )
        )
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            # Python cannot forcibly stop a thread that is inside native
            # WhisperX/PyTorch inference. Keep cancellation pending until the
            # worker exits so the caller never releases its run lock while an
            # orphan GPU job is still mutating this provider's model state.
            LOGGER.warning("Waiting for active WhisperX inference before cancellation.")
            try:
                await asyncio.shield(worker)
            except Exception:
                LOGGER.debug(
                    "WhisperX inference failed while cancellation was pending.",
                    exc_info=True,
                )
            raise

    async def aclose(self) -> None:
        """Release cached models and unused CUDA allocations explicitly."""
        await asyncio.to_thread(self.close)

    def close(self) -> None:
        """Release model references so a local worker can return VRAM to CUDA."""
        with self._inference_lock:
            transcription_model = self._transcription_model
            alignment_models = self._alignment_models
            self._transcription_model = None
            self._alignment_models = {}
            del transcription_model
            del alignment_models
        gc.collect()
        self._clear_cuda_cache()

    def __del__(self) -> None:
        """Best-effort cleanup for callers that do not explicitly close us."""
        try:
            self.close()
        except Exception:
            return

    def _align_sync(
        self,
        audio_asset: AudioAsset,
        highlight: SelectedHighlight,
        language: str | None,
        transcript: str | None,
    ) -> list[WordTiming]:
        """Load/cache models and run WhisperX without sharing GPU inference."""
        try:
            with self._inference_lock:
                transcription: dict[str, Any] | None = None
                language_code = (language or "").strip()
                requires_transcription = transcript is None or not language_code

                # A supplied language lets the premium narration path bypass
                # ASR completely: the approved script itself becomes the
                # alignment input. If language is unknown, ASR is used only to
                # detect it; its words are still not substituted for the script.
                if requires_transcription:
                    if self._transcription_model is None:
                        self._transcription_model = whisperx.load_model(
                            self._model_name,
                            self._device,
                            compute_type=self._compute_type,
                        )
                audio = whisperx.load_audio(audio_asset.local_path)
                if requires_transcription:
                    transcribe_options: dict[str, Any] = {
                        "batch_size": self._batch_size
                    }
                    if language_code:
                        transcribe_options["language"] = language_code
                    transcription = self._transcription_model.transcribe(
                        audio,
                        **transcribe_options,
                    )
                    language_code = language_code or str(
                        transcription.get("language") or ""
                    ).strip()
                if not language_code:
                    raise WordAlignmentError("WhisperX did not return a transcript language.")

                if transcript is not None:
                    segments = [
                        {
                            "start": highlight.start_ms / 1_000,
                            "end": highlight.end_ms / 1_000,
                            "text": transcript,
                        }
                    ]
                else:
                    segments = (transcription or {}).get("segments") or []

                alignment_model, metadata = self._alignment_models.get(language_code, (None, None))
                if alignment_model is None:
                    alignment_model, metadata = whisperx.load_align_model(
                        language_code=language_code,
                        device=self._device,
                    )
                    self._alignment_models[language_code] = (alignment_model, metadata)
                aligned = whisperx.align(
                    segments,
                    alignment_model,
                    metadata,
                    audio,
                    self._device,
                    return_char_alignments=False,
                )
        except WordAlignmentError:
            raise
        except Exception as exc:  # noqa: BLE001 - provider internals must not leak outward
            raise WordAlignmentError(
                f"WhisperX could not align '{audio_asset.local_path}': {exc}"
            ) from exc
        finally:
            self._clear_cuda_cache()

        return self._to_word_timings(aligned, highlight)

    def _clear_cuda_cache(self) -> None:
        """Ask PyTorch to release cached blocks without unloading live models."""
        if not self._device.lower().startswith("cuda"):
            return
        try:
            import torch
        except ImportError:
            return
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                if hasattr(torch.cuda, "ipc_collect"):
                    torch.cuda.ipc_collect()
        except Exception:
            LOGGER.warning("Could not release cached CUDA allocations.", exc_info=True)

    @staticmethod
    def _to_word_timings(
        aligned: dict[str, Any], highlight: SelectedHighlight
    ) -> list[WordTiming]:
        timings: list[WordTiming] = []
        segments = aligned.get("segments") or []
        if not isinstance(segments, list):
            raise WordAlignmentError("WhisperX alignment response has invalid segments.")

        for segment in segments:
            if not isinstance(segment, dict):
                continue
            words = segment.get("words") or []
            if not isinstance(words, list):
                continue
            for word in words:
                if not isinstance(word, dict):
                    continue
                start_seconds = word.get("start")
                end_seconds = word.get("end")
                # WhisperX documents that some words cannot be aligned. They
                # have no safe timestamp, so exclude them instead of inventing one.
                if start_seconds is None or end_seconds is None:
                    continue
                try:
                    start_ms = round(float(start_seconds) * 1_000)
                    end_ms = round(float(end_seconds) * 1_000)
                    timing = WordTiming(
                        text=str(word.get("word") or word.get("text") or "").strip(),
                        start_ms=start_ms,
                        end_ms=end_ms,
                        confidence=(
                            float(word["score"])
                            if word.get("score") is not None
                            else None
                        ),
                    )
                except (TypeError, ValueError) as exc:
                    raise WordAlignmentError(
                        f"WhisperX returned an invalid timed word: {word!r}."
                    ) from exc
                if timing.start_ms >= highlight.start_ms and timing.end_ms <= highlight.end_ms:
                    timings.append(timing)

        return sorted(timings, key=lambda timing: (timing.start_ms, timing.end_ms))
