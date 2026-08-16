"""Local-file adapter for acquiring licensed MP3 and WAV audio assets."""
from __future__ import annotations

import asyncio
import hashlib
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from core.domain.entities.audio_asset import AudioAsset
from core.domain.exceptions import (
    AudioLicenseError,
    AudioSourceError,
    UnsupportedAudioFormatError,
)
from core.domain.ports.audio_source_port import AudioSourcePort


_SUPPORTED_MEDIA_TYPES = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
}


class LocalAudioSourceProvider(AudioSourcePort):
    """Turns a local, rights-cleared audio file into an ``AudioAsset``.

    The current project has no rights catalogue yet. ``is_licensed`` is a
    deliberately explicit temporary policy switch: callers may use it in
    development tests, but production composition must obtain it from a
    license manifest before calling this adapter.
    """

    def __init__(
        self,
        ffprobe_binary: str = "ffprobe",
        *,
        is_licensed: bool = True,
        license_name: str = "Development license assertion",
        usage_rights: str = "youtube_shorts_commercial",
        license_manifest_path: str | Path | None = None,
        require_license_manifest: bool = False,
        subprocess_timeout_seconds: float = 300.0,
        termination_grace_seconds: float = 5.0,
    ) -> None:
        if subprocess_timeout_seconds <= 0:
            raise ValueError("subprocess_timeout_seconds must be greater than zero.")
        if termination_grace_seconds <= 0:
            raise ValueError("termination_grace_seconds must be greater than zero.")
        self._ffprobe = ffprobe_binary
        self._is_licensed = is_licensed
        self._license_name = license_name
        self._usage_rights = usage_rights
        self._license_manifest_path = (
            Path(license_manifest_path) if license_manifest_path else None
        )
        self._require_license_manifest = require_license_manifest
        self._subprocess_timeout_seconds = subprocess_timeout_seconds
        self._termination_grace_seconds = termination_grace_seconds

    async def acquire(self, source_reference: str) -> AudioAsset:
        """Inspect one local MP3 or WAV file and return a licensed asset.

        Args:
            source_reference: Absolute or relative path to a local audio file.

        Raises:
            AudioLicenseError: The temporary rights policy rejects the source.
            AudioSourceError: The file is missing, empty, or ffprobe fails.
            UnsupportedAudioFormatError: The extension or detected stream is invalid.
        """
        path = Path(source_reference).expanduser()
        if not path.is_file() or path.stat().st_size <= 0:
            raise AudioSourceError(
                f"Local audio source is missing or empty at '{source_reference}'."
            )

        media_type = _SUPPORTED_MEDIA_TYPES.get(path.suffix.lower())
        if media_type is None:
            raise UnsupportedAudioFormatError(
                f"Unsupported local audio format '{path.suffix}'. Supported: .mp3, .wav."
            )
        if not self._is_licensed:
            raise AudioLicenseError(
                f"Local audio source '{source_reference}' is not licensed for publishing."
            )

        license_name, usage_rights = await asyncio.to_thread(self._license_for, path)

        probe = await self._probe(path)
        audio_stream = self._audio_stream(probe, path)
        duration_ms = self._duration_ms(probe, audio_stream, path)
        tags = {**(probe.get("format", {}).get("tags") or {}), **(audio_stream.get("tags") or {})}

        return AudioAsset.create(
            source_provider="local",
            source_asset_id=str(path.resolve()),
            local_path=str(path.resolve()),
            duration_ms=duration_ms,
            media_type=media_type,
            license=license_name,
            usage_rights=usage_rights,
            title=self._optional_tag(tags, "title"),
            artist=self._optional_tag(tags, "artist"),
            language=self._optional_tag(tags, "language"),
            sample_rate_hz=self._optional_positive_int(audio_stream.get("sample_rate")),
            channels=self._optional_positive_int(audio_stream.get("channels")),
            metadata={
                "format_name": probe.get("format", {}).get("format_name"),
                "codec_name": audio_stream.get("codec_name"),
                "bit_rate": audio_stream.get("bit_rate"),
                "license_policy": (
                    "manifest_sha256" if self._license_manifest_path else "constructor_assertion"
                ),
            },
        )

    async def _probe(self, path: Path) -> dict[str, Any]:
        command = [
            self._ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
        process: asyncio.subprocess.Process | None = None
        try:
            process = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=self._subprocess_timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise AudioSourceError(
                f"Could not find ffprobe binary '{self._ffprobe}'."
            ) from exc
        except asyncio.TimeoutError as exc:
            raise AudioSourceError(
                f"Timed out starting ffprobe for '{path}'."
            ) from exc

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self._subprocess_timeout_seconds,
            )
            if process.returncode != 0:
                error = (stderr or b"").decode("utf-8", errors="replace")[-2_000:]
                raise AudioSourceError(
                    f"ffprobe failed while inspecting '{path}': {error}"
                )
        except asyncio.TimeoutError as exc:
            raise AudioSourceError(
                f"ffprobe timed out after {self._subprocess_timeout_seconds:.0f}s for '{path}'."
            ) from exc
        except asyncio.CancelledError:
            await asyncio.shield(self._stop_process(process))
            raise
        finally:
            if process.returncode is None:
                await asyncio.shield(self._stop_process(process))

        try:
            data = json.loads((stdout or b"").decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            raise AudioSourceError(
                f"ffprobe returned invalid JSON for '{path}': {exc}"
            ) from exc
        if not isinstance(data, dict):
            raise AudioSourceError(f"ffprobe returned an invalid payload for '{path}'.")
        return data

    def _license_for(self, path: Path) -> tuple[str, str]:
        if self._license_manifest_path is None:
            if self._require_license_manifest:
                raise AudioLicenseError("A license manifest is required for production audio.")
            return self._license_name, self._usage_rights
        try:
            manifest = json.loads(self._license_manifest_path.read_text(encoding="utf-8"))
            assets = manifest["assets"]
            record = assets[self._sha256(path)]
            license_name = str(record["license"]).strip()
            usage_rights = str(record["usage_rights"]).strip()
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise AudioLicenseError(
                f"No valid license manifest entry exists for '{path.name}'."
            ) from error
        if not license_name or not usage_rights:
            raise AudioLicenseError(f"License manifest entry for '{path.name}' is incomplete.")
        allowed_rights = {
            "youtube_shorts_commercial",
            "youtube_commercial",
            "commercial_worldwide",
            "self_owned_commercial",
        }
        if usage_rights.casefold() not in allowed_rights:
            raise AudioLicenseError(
                f"Audio usage rights for '{path.name}' do not explicitly allow commercial YouTube publishing."
            )
        if int(manifest.get("schema_version", 1)) >= 2:
            source_url = str(record.get("source_url") or "").strip()
            evidence_reference = str(record.get("evidence_reference") or "").strip()
            if not source_url or not evidence_reference:
                raise AudioLicenseError(
                    f"Schema v2 rights evidence for '{path.name}' is incomplete."
                )
        return license_name, usage_rights

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    async def _stop_process(self, process: asyncio.subprocess.Process) -> None:
        """Terminate and reap a timed-out ffprobe child process."""
        if process.returncode is not None:
            return
        try:
            process.terminate()
        except ProcessLookupError:
            return

        await asyncio.sleep(0.1)
        if process.returncode is None:
            try:
                await asyncio.wait_for(process.wait(), timeout=self._termination_grace_seconds)
            except asyncio.TimeoutError:
                try:
                    process.kill()
                except ProcessLookupError:
                    return

        try:
            await asyncio.wait_for(process.communicate(), timeout=self._termination_grace_seconds)
        except asyncio.TimeoutError:
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    return
            await process.communicate()

    @staticmethod
    def _audio_stream(probe: dict[str, Any], path: Path) -> dict[str, Any]:
        streams = probe.get("streams")
        if not isinstance(streams, list):
            raise AudioSourceError(f"ffprobe returned no streams for '{path}'.")
        stream = next(
            (
                candidate
                for candidate in streams
                if isinstance(candidate, dict) and candidate.get("codec_type") == "audio"
            ),
            None,
        )
        if stream is None:
            raise UnsupportedAudioFormatError(
                f"Local source '{path}' does not contain an audio stream."
            )
        return stream

    @staticmethod
    def _duration_ms(
        probe: dict[str, Any], audio_stream: dict[str, Any], path: Path
    ) -> int:
        raw_duration = probe.get("format", {}).get("duration") or audio_stream.get("duration")
        try:
            duration_ms = int(
                (Decimal(str(raw_duration)) * Decimal("1000")).to_integral_value(
                    rounding=ROUND_HALF_UP
                )
            )
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise AudioSourceError(
                f"ffprobe returned an invalid duration for '{path}': {raw_duration!r}."
            ) from exc
        if duration_ms <= 0:
            raise AudioSourceError(
                f"ffprobe returned a non-positive duration for '{path}': {raw_duration!r}."
            )
        return duration_ms

    @staticmethod
    def _optional_positive_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise AudioSourceError(f"ffprobe returned an invalid integer value: {value!r}.") from exc
        return parsed if parsed > 0 else None

    @staticmethod
    def _optional_tag(tags: dict[str, Any], name: str) -> str | None:
        value = tags.get(name) or tags.get(name.upper())
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None
