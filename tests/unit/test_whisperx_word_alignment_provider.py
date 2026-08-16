from __future__ import annotations

import asyncio
import sys
import threading
from types import SimpleNamespace

import pytest

from core.domain.entities.audio_asset import AudioAsset
from core.domain.exceptions import WordAlignmentError
from core.domain.value_objects.selected_highlight import SelectedHighlight
from infrastructure.providers.audio import whisperx_word_alignment_provider as provider_module
from infrastructure.providers.audio.whisperx_word_alignment_provider import (
    WhisperXWordAlignmentProvider,
)


def _asset() -> AudioAsset:
    return AudioAsset.create(
        source_provider="local",
        source_asset_id="track-1",
        local_path="C:/media/track.mp3",
        duration_ms=40_000,
        media_type="audio/mpeg",
        license="Commercial",
        usage_rights="youtube_shorts_commercial",
    )


def _highlight(asset: AudioAsset) -> SelectedHighlight:
    return SelectedHighlight(
        audio_asset_id=asset.id,
        start_ms=10_000,
        end_ms=30_000,
        score=0.9,
        selector_used="fake",
        hook_type="chorus",
        rationale="Test hook.",
    )


@pytest.mark.asyncio
async def test_align_runs_whisperx_off_event_loop_and_filters_untimed_words(monkeypatch):
    calls: list[str] = []

    class FakeModel:
        def transcribe(self, audio, **kwargs):
            calls.append("transcribe")
            assert kwargs == {"batch_size": 4, "language": "en"}
            return {"language": "en", "segments": [{"text": "test"}]}

    def load_model(model_name, device, *, compute_type):
        calls.append("load_model")
        assert (model_name, device, compute_type) == ("small", "cpu", "int8")
        return FakeModel()

    def load_audio(path):
        calls.append("load_audio")
        return "decoded-audio"

    def load_align_model(*, language_code, device):
        calls.append("load_align_model")
        assert (language_code, device) == ("en", "cpu")
        return "align-model", {"language": "en"}

    def align(segments, model, metadata, audio, device, *, return_char_alignments):
        calls.append("align")
        assert return_char_alignments is False
        return {
            "segments": [
                {
                    "words": [
                        {"word": "Inside", "start": 10.125, "end": 10.500, "score": 0.99},
                        {"word": "Missing", "start": None, "end": None},
                        {"word": "Outside", "start": 31.0, "end": 31.4},
                    ]
                }
            ]
        }

    monkeypatch.setattr(
        provider_module,
        "whisperx",
        SimpleNamespace(
            load_model=load_model,
            load_audio=load_audio,
            load_align_model=load_align_model,
            align=align,
        ),
    )
    original_to_thread = asyncio.to_thread

    async def observing_to_thread(function, *args, **kwargs):
        calls.append("to_thread")
        return await original_to_thread(function, *args, **kwargs)

    monkeypatch.setattr(provider_module.asyncio, "to_thread", observing_to_thread)

    asset = _asset()
    timings = await WhisperXWordAlignmentProvider().align(
        asset,
        _highlight(asset),
        language="en",
    )

    assert calls[0] == "to_thread"
    assert calls[1:] == ["load_model", "load_audio", "transcribe", "load_align_model", "align"]
    assert [(timing.text, timing.start_ms, timing.end_ms) for timing in timings] == [
        ("Inside", 10_125, 10_500)
    ]


@pytest.mark.asyncio
async def test_align_force_aligns_trusted_transcript_without_running_asr(monkeypatch):
    calls: list[str] = []
    trusted_transcript = "Ahtapotların üç kalbi vardır."

    def load_model(*args, **kwargs):
        raise AssertionError("ASR must not run when transcript and language are trusted.")

    def load_audio(path):
        calls.append("load_audio")
        assert path == "C:/media/track.mp3"
        return "decoded-audio"

    def load_align_model(*, language_code, device):
        calls.append("load_align_model")
        assert (language_code, device) == ("tr", "cpu")
        return "align-model", {"language": "tr"}

    def align(segments, model, metadata, audio, device, *, return_char_alignments):
        calls.append("align")
        assert segments == [
            {
                "start": 10.0,
                "end": 30.0,
                "text": trusted_transcript,
            }
        ]
        assert (model, metadata, audio, device) == (
            "align-model",
            {"language": "tr"},
            "decoded-audio",
            "cpu",
        )
        assert return_char_alignments is False
        return {
            "segments": [
                {
                    "words": [
                        {"word": "Ahtapotların", "start": 10.0, "end": 10.8},
                        {"word": "üç", "start": 10.9, "end": 11.1},
                        {"word": "kalbi", "start": 11.2, "end": 11.5},
                        {"word": "vardır.", "start": 11.6, "end": 12.0},
                    ]
                }
            ]
        }

    monkeypatch.setattr(
        provider_module,
        "whisperx",
        SimpleNamespace(
            load_model=load_model,
            load_audio=load_audio,
            load_align_model=load_align_model,
            align=align,
        ),
    )

    asset = _asset()
    timings = await WhisperXWordAlignmentProvider().align(
        asset,
        _highlight(asset),
        language="tr",
        transcript=trusted_transcript,
    )

    assert calls == ["load_audio", "load_align_model", "align"]
    assert [timing.text for timing in timings] == [
        "Ahtapotların",
        "üç",
        "kalbi",
        "vardır.",
    ]


@pytest.mark.asyncio
async def test_align_wraps_whisperx_errors(monkeypatch):
    class BrokenWhisperX:
        @staticmethod
        def load_model(*args, **kwargs):
            raise RuntimeError("GPU unavailable")

    monkeypatch.setattr(provider_module, "whisperx", BrokenWhisperX())
    asset = _asset()

    with pytest.raises(WordAlignmentError, match="GPU unavailable"):
        await WhisperXWordAlignmentProvider().align(asset, _highlight(asset))


@pytest.mark.asyncio
async def test_align_rejects_highlight_from_another_asset():
    asset = _asset()
    other_asset = _asset()

    with pytest.raises(WordAlignmentError, match="different AudioAsset"):
        await WhisperXWordAlignmentProvider().align(asset, _highlight(other_asset))


@pytest.mark.asyncio
async def test_close_releases_cached_models_and_cuda_cache(monkeypatch):
    cache_calls: list[str] = []
    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(
            is_available=lambda: True,
            empty_cache=lambda: cache_calls.append("empty_cache"),
            ipc_collect=lambda: cache_calls.append("ipc_collect"),
        )
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    provider = WhisperXWordAlignmentProvider(device="cuda")
    provider._transcription_model = object()
    provider._alignment_models["en"] = (object(), {"language": "en"})

    await provider.aclose()

    assert provider._transcription_model is None
    assert provider._alignment_models == {}
    assert cache_calls == ["empty_cache", "ipc_collect"]


@pytest.mark.asyncio
async def test_cancellation_waits_for_native_inference_to_finish(monkeypatch):
    monkeypatch.setattr(provider_module, "whisperx", object())
    provider = WhisperXWordAlignmentProvider()
    started = threading.Event()
    release = threading.Event()

    def blocking_alignment(*args):
        started.set()
        release.wait(timeout=2)
        return []

    monkeypatch.setattr(provider, "_align_sync", blocking_alignment)
    asset = _asset()
    task = asyncio.create_task(provider.align(asset, _highlight(asset)))
    assert await asyncio.to_thread(started.wait, 1)

    task.cancel()
    await asyncio.sleep(0.02)
    assert task.done() is False

    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
