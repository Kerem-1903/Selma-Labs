from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MediaInspection:
    format_names: tuple[str, ...]
    duration_seconds: float
    width: int
    height: int
    fps: float
    video_codec: str
    pixel_format: str | None
    audio_codec: str | None
    audio_sample_rate: int | None
    audio_bitrate: int | None
    file_size_bytes: int
    color_primaries: str | None = None
    color_transfer: str | None = None
    color_space: str | None = None
    color_range: str | None = None
    field_order: str | None = None
    audio_channels: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_names": list(self.format_names),
            "duration_seconds": self.duration_seconds,
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "video_codec": self.video_codec,
            "pixel_format": self.pixel_format,
            "audio_codec": self.audio_codec,
            "audio_sample_rate": self.audio_sample_rate,
            "audio_bitrate": self.audio_bitrate,
            "file_size_bytes": self.file_size_bytes,
            "color_primaries": self.color_primaries,
            "color_transfer": self.color_transfer,
            "color_space": self.color_space,
            "color_range": self.color_range,
            "field_order": self.field_order,
            "audio_channels": self.audio_channels,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "MediaInspection":
        return MediaInspection(
            format_names=tuple(str(value) for value in data.get("format_names", [])),
            duration_seconds=float(data["duration_seconds"]),
            width=int(data["width"]),
            height=int(data["height"]),
            fps=float(data["fps"]),
            video_codec=str(data["video_codec"]),
            pixel_format=(str(data["pixel_format"]) if data.get("pixel_format") else None),
            audio_codec=(str(data["audio_codec"]) if data.get("audio_codec") else None),
            audio_sample_rate=(
                int(data["audio_sample_rate"])
                if data.get("audio_sample_rate") is not None
                else None
            ),
            audio_bitrate=(
                int(data["audio_bitrate"])
                if data.get("audio_bitrate") is not None
                else None
            ),
            file_size_bytes=int(data["file_size_bytes"]),
            color_primaries=(
                str(data["color_primaries"]) if data.get("color_primaries") else None
            ),
            color_transfer=(
                str(data["color_transfer"]) if data.get("color_transfer") else None
            ),
            color_space=(str(data["color_space"]) if data.get("color_space") else None),
            color_range=(str(data["color_range"]) if data.get("color_range") else None),
            field_order=(str(data["field_order"]) if data.get("field_order") else None),
            audio_channels=(
                int(data["audio_channels"])
                if data.get("audio_channels") is not None
                else None
            ),
        )
