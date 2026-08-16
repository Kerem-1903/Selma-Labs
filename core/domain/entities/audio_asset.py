"""Provider-independent representation of one licensed audio input."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class AudioAsset:
    """An acquired song or music track that can enter the Shorts pipeline.

    ``local_path`` points at the persisted source file that media adapters
    analyze. Licensing fields are mandatory because an asset without an
    auditable usage right must never reach autonomous publication.
    """

    id: str
    source_provider: str
    source_asset_id: str
    local_path: str
    duration_ms: int
    media_type: str
    license: str
    usage_rights: str
    original_url: str | None = None
    title: str | None = None
    artist: str | None = None
    language: str | None = None
    content_hash: str | None = None
    sample_rate_hz: int | None = None
    channels: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.source_provider.strip():
            raise ValueError("AudioAsset source_provider must not be empty.")
        if not self.source_asset_id.strip():
            raise ValueError("AudioAsset source_asset_id must not be empty.")
        if not self.local_path.strip():
            raise ValueError("AudioAsset local_path must not be empty.")
        if self.duration_ms <= 0:
            raise ValueError("AudioAsset duration_ms must be greater than zero.")
        if not self.media_type.strip():
            raise ValueError("AudioAsset media_type must not be empty.")
        if not self.license.strip() or not self.usage_rights.strip():
            raise ValueError("AudioAsset requires license and usage_rights metadata.")
        if self.sample_rate_hz is not None and self.sample_rate_hz <= 0:
            raise ValueError("AudioAsset sample_rate_hz must be greater than zero.")
        if self.channels is not None and self.channels <= 0:
            raise ValueError("AudioAsset channels must be greater than zero.")

    @classmethod
    def create(
        cls,
        *,
        source_provider: str,
        source_asset_id: str,
        local_path: str,
        duration_ms: int,
        media_type: str,
        license: str,
        usage_rights: str,
        original_url: str | None = None,
        title: str | None = None,
        artist: str | None = None,
        language: str | None = None,
        content_hash: str | None = None,
        sample_rate_hz: int | None = None,
        channels: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "AudioAsset":
        return cls(
            id=str(uuid4()),
            source_provider=source_provider,
            source_asset_id=source_asset_id,
            local_path=local_path,
            duration_ms=duration_ms,
            media_type=media_type,
            license=license,
            usage_rights=usage_rights,
            original_url=original_url,
            title=title,
            artist=artist,
            language=language,
            content_hash=content_hash,
            sample_rate_hz=sample_rate_hz,
            channels=channels,
            metadata=metadata or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_provider": self.source_provider,
            "source_asset_id": self.source_asset_id,
            "local_path": self.local_path,
            "duration_ms": self.duration_ms,
            "media_type": self.media_type,
            "license": self.license,
            "usage_rights": self.usage_rights,
            "original_url": self.original_url,
            "title": self.title,
            "artist": self.artist,
            "language": self.language,
            "content_hash": self.content_hash,
            "sample_rate_hz": self.sample_rate_hz,
            "channels": self.channels,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AudioAsset":
        """Rehydrate an asset previously persisted in a pipeline artifact."""
        return cls(
            id=str(data["id"]),
            source_provider=str(data["source_provider"]),
            source_asset_id=str(data["source_asset_id"]),
            local_path=str(data["local_path"]),
            duration_ms=int(data["duration_ms"]),
            media_type=str(data["media_type"]),
            license=str(data["license"]),
            usage_rights=str(data["usage_rights"]),
            original_url=data.get("original_url"),
            title=data.get("title"),
            artist=data.get("artist"),
            language=data.get("language"),
            content_hash=data.get("content_hash"),
            sample_rate_hz=data.get("sample_rate_hz"),
            channels=data.get("channels"),
            metadata=dict(data.get("metadata", {})),
            created_at=datetime.fromisoformat(data["created_at"]),
        )
