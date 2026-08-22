from __future__ import annotations

from pathlib import Path

from core.domain.entities.media_asset import MediaAsset
from core.domain.ports.video_source_port import VideoSourcePort


class UserUploadedAssetProvider(VideoSourcePort):
    """Search and download visual assets from a local user library."""

    VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}

    def __init__(self, asset_directory: str | Path = "output/user_uploads") -> None:
        self.asset_directory = Path(asset_directory)
        self.asset_directory.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return "user_uploads"

    async def search(self, query: str, max_results: int) -> list[MediaAsset]:
        query_terms = {term.lower() for term in query.split() if term.strip()}
        paths = sorted(
            path
            for path in self.asset_directory.iterdir()
            if path.is_file() and path.suffix.lower() in self.VIDEO_EXTENSIONS
        )
        matching = [
            path for path in paths
            if not query_terms or query_terms & set(path.stem.lower().replace("_", " ").split())
        ]
        selected = (matching or paths)[:max_results]
        return [self._asset(path) for path in selected]

    async def download(self, asset: MediaAsset) -> bytes:
        path = Path(asset.local_path or asset.original_url)
        if not path.is_file():
            raise FileNotFoundError(f"Uploaded asset not found: {path}")
        return path.read_bytes()

    def _asset(self, path: Path) -> MediaAsset:
        return MediaAsset(
            id=f"user_uploads:{path.name}",
            provider=self.name,
            provider_asset_id=path.name,
            original_url=str(path),
            local_path=str(path),
            tags=[path.stem],
            attribution="User uploaded",
            license="user-provided",
            metadata={"filename": path.name},
        )