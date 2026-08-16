from __future__ import annotations

import asyncio
import hashlib
import json

import pytest

from core.domain.exceptions import (
    AudioLicenseError,
    AudioSourceError,
    UnsupportedAudioFormatError,
)
from infrastructure.providers.audio.local_audio_source_provider import (
    LocalAudioSourceProvider,
)


class _FakeProcess:
    def __init__(self, *, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr


class _HangingProcess:
    def __init__(self) -> None:
        self.returncode: int | None = None
        self.terminated = False
        self.killed = False
        self._finished = asyncio.Event()

    async def communicate(self) -> tuple[bytes, bytes]:
        await self._finished.wait()
        return b"", b""

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9
        self._finished.set()

    async def wait(self) -> int:
        self.returncode = -15
        self._finished.set()
        return self.returncode


def _probe_payload(**format_overrides) -> bytes:
    media_format = {
        "format_name": "mp3",
        "duration": "21.4996",
        "tags": {"title": "Night Drive", "artist": "SELMA"},
    }
    media_format.update(format_overrides)
    return json.dumps(
        {
            "format": media_format,
            "streams": [
                {
                    "codec_type": "audio",
                    "codec_name": "mp3",
                    "sample_rate": "44100",
                    "channels": 2,
                }
            ],
        }
    ).encode()


@pytest.mark.asyncio
async def test_acquire_maps_ffprobe_metadata_to_audio_asset(tmp_path, monkeypatch):
    audio_file = tmp_path / "night-drive.mp3"
    audio_file.write_bytes(b"not-a-real-mp3-but-present")
    commands: list[tuple[str, ...]] = []

    async def fake_create_subprocess_exec(*command, **kwargs):
        commands.append(command)
        assert kwargs["stdout"] is asyncio.subprocess.PIPE
        assert kwargs["stderr"] is asyncio.subprocess.PIPE
        return _FakeProcess(stdout=_probe_payload())

    monkeypatch.setattr(
        "infrastructure.providers.audio.local_audio_source_provider.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    asset = await LocalAudioSourceProvider().acquire(str(audio_file))

    assert asset.source_provider == "local"
    assert asset.local_path == str(audio_file.resolve())
    assert asset.duration_ms == 21_500
    assert asset.media_type == "audio/mpeg"
    assert asset.title == "Night Drive"
    assert asset.artist == "SELMA"
    assert asset.sample_rate_hz == 44_100
    assert asset.channels == 2
    assert asset.license == "Development license assertion"
    assert commands[0][0] == "ffprobe"
    assert "-show_streams" in commands[0]


@pytest.mark.asyncio
async def test_acquire_rejects_missing_or_empty_file(tmp_path):
    missing = tmp_path / "missing.mp3"

    with pytest.raises(AudioSourceError, match="missing or empty"):
        await LocalAudioSourceProvider().acquire(str(missing))


@pytest.mark.asyncio
async def test_acquire_rejects_unsupported_extension(tmp_path):
    source = tmp_path / "song.flac"
    source.write_bytes(b"audio")

    with pytest.raises(UnsupportedAudioFormatError, match="Unsupported local audio format"):
        await LocalAudioSourceProvider().acquire(str(source))


@pytest.mark.asyncio
async def test_acquire_rejects_unlicensed_source_before_probing(tmp_path):
    source = tmp_path / "song.wav"
    source.write_bytes(b"audio")

    with pytest.raises(AudioLicenseError, match="not licensed"):
        await LocalAudioSourceProvider(is_licensed=False).acquire(str(source))


def test_license_manifest_rejects_noncommercial_usage(tmp_path):
    source = tmp_path / "song.wav"
    source.write_bytes(b"audio")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = tmp_path / "license_manifest.json"
    manifest.write_text(
        json.dumps({"assets": {digest: {"license": "CC-BY-NC", "usage_rights": "noncommercial"}}}),
        encoding="utf-8",
    )
    provider = LocalAudioSourceProvider(
        license_manifest_path=manifest,
        require_license_manifest=True,
    )

    with pytest.raises(AudioLicenseError, match="commercial YouTube"):
        provider._license_for(source)


def test_schema_v2_license_requires_traceable_evidence(tmp_path):
    source = tmp_path / "song.wav"
    source.write_bytes(b"audio")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = tmp_path / "license_manifest.json"
    manifest.write_text(
        json.dumps({"schema_version": 2, "assets": {digest: {"license": "Owned", "usage_rights": "self_owned_commercial"}}}),
        encoding="utf-8",
    )
    provider = LocalAudioSourceProvider(
        license_manifest_path=manifest,
        require_license_manifest=True,
    )

    with pytest.raises(AudioLicenseError, match="rights evidence"):
        provider._license_for(source)


@pytest.mark.asyncio
async def test_acquire_wraps_missing_ffprobe_binary(tmp_path, monkeypatch):
    source = tmp_path / "song.wav"
    source.write_bytes(b"audio")

    async def missing_binary(*args, **kwargs):
        raise FileNotFoundError("ffprobe")

    monkeypatch.setattr(
        "infrastructure.providers.audio.local_audio_source_provider.asyncio.create_subprocess_exec",
        missing_binary,
    )

    with pytest.raises(AudioSourceError, match="Could not find ffprobe"):
        await LocalAudioSourceProvider().acquire(str(source))


@pytest.mark.asyncio
async def test_acquire_wraps_ffprobe_failure(tmp_path, monkeypatch):
    source = tmp_path / "song.wav"
    source.write_bytes(b"audio")

    async def failed_probe(*args, **kwargs):
        return _FakeProcess(returncode=1, stderr=b"Invalid data found")

    monkeypatch.setattr(
        "infrastructure.providers.audio.local_audio_source_provider.asyncio.create_subprocess_exec",
        failed_probe,
    )

    with pytest.raises(AudioSourceError, match="Invalid data found"):
        await LocalAudioSourceProvider().acquire(str(source))


@pytest.mark.asyncio
async def test_acquire_timeout_terminates_and_reaps_ffprobe(tmp_path, monkeypatch):
    source = tmp_path / "song.wav"
    source.write_bytes(b"audio")
    process = _HangingProcess()

    async def hanging_probe(*args, **kwargs):
        return process

    monkeypatch.setattr(
        "infrastructure.providers.audio.local_audio_source_provider.asyncio.create_subprocess_exec",
        hanging_probe,
    )

    with pytest.raises(AudioSourceError, match="timed out"):
        await LocalAudioSourceProvider(subprocess_timeout_seconds=0.01).acquire(str(source))

    assert process.terminated is True
    assert process.returncode == -15


@pytest.mark.asyncio
async def test_acquire_rejects_payload_without_audio_stream(tmp_path, monkeypatch):
    source = tmp_path / "song.wav"
    source.write_bytes(b"audio")
    payload = json.dumps(
        {"format": {"duration": "2.0"}, "streams": [{"codec_type": "video"}]}
    ).encode()

    async def no_audio_stream(*args, **kwargs):
        return _FakeProcess(stdout=payload)

    monkeypatch.setattr(
        "infrastructure.providers.audio.local_audio_source_provider.asyncio.create_subprocess_exec",
        no_audio_stream,
    )

    with pytest.raises(UnsupportedAudioFormatError, match="does not contain an audio stream"):
        await LocalAudioSourceProvider().acquire(str(source))
