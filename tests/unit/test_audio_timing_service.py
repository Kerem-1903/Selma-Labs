from __future__ import annotations

import wave

from core.application.services.audio_timing_service import AudioTimingService


def _wav(path, *, sample_rate: int, samples: int) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\0\0" * samples)


def test_wav_duration_uses_sample_count_and_allows_padding(tmp_path):
    path = tmp_path / "line.wav"
    _wav(path, sample_rate=48000, samples=48001)

    timing = AudioTimingService.inspect_dialogue(path, allocated_frames=25)

    assert timing.required_frames == 25
    assert timing.status == "OK"
    assert timing.padding_frames == 0


def test_dialogue_overflow_is_blocked_without_changing_allocation(tmp_path):
    path = tmp_path / "long-line.wav"
    _wav(path, sample_rate=48000, samples=48001)

    timing = AudioTimingService.inspect_dialogue(path, allocated_frames=24)

    assert timing.status == "BLOCKED"
    assert timing.required_frames == 25
    assert timing.overflow_frames == 1
    assert timing.allocated_frames == 24
