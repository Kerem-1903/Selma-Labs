from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class UploadReadinessCheck:
    name: str
    status: str
    required: bool
    details: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "required": self.required,
            "details": self.details,
        }


@dataclass(frozen=True)
class YoutubeUploadPackage:
    package_directory: str
    video_path: str
    caption_path: str
    thumbnail_frame_path: str
    metadata_path: str
    quality_report_path: str
    checklist_path: str
    ready_to_upload: bool
    checks: tuple[UploadReadinessCheck, ...]
    manual_checks: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_directory": self.package_directory,
            "video_path": self.video_path,
            "caption_path": self.caption_path,
            "thumbnail_frame_path": self.thumbnail_frame_path,
            "metadata_path": self.metadata_path,
            "quality_report_path": self.quality_report_path,
            "checklist_path": self.checklist_path,
            "ready_to_upload": self.ready_to_upload,
            "checks": [check.to_dict() for check in self.checks],
            "manual_checks": list(self.manual_checks),
        }
