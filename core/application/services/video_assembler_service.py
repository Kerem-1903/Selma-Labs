import asyncio
import os
import tempfile
from typing import List
from core.domain.entities.media_asset import MediaAsset
from core.domain.ports.storage_port import StoragePort

class VideoAssemblerService:
    """
    A8.1 Pilot Production: Combines multiple video clips (shots) into a single continuous sequence.
    This simple implementation uses FFmpeg's concat demuxer.
    """
    def __init__(self, storage: StoragePort):
        self._storage = storage

    async def assemble_sequence(self, shot_assets: List[MediaAsset], output_path: str) -> str:
        """
        Combines multiple video assets in order.

        Args:
            shot_assets: List of MediaAssets representing the approved shots.
            output_path: Path where the assembled video should be saved.

        Returns:
            The path to the assembled video.
        """
        if not shot_assets:
            raise ValueError("No shots provided for assembly.")

        # Download all assets locally
        temp_dir = tempfile.mkdtemp(prefix="selma_assembler_")
        local_files = []

        for i, asset in enumerate(shot_assets):
            ext = "mp4" # Simplify extension logic, assume mp4 for video clips
            local_path = os.path.join(temp_dir, f"shot_{i:04d}.{ext}")

            # Asset should have local_path already from VideoProvider, but if not we can use storage
            if asset.local_path and os.path.exists(asset.local_path):
                local_files.append(asset.local_path)
                continue

            success = self._storage.download_file(asset.original_url, local_path)
            if not success:
                if hasattr(self._storage, 'get'):
                    data = await self._storage.get(asset.original_url)
                    with open(local_path, "wb") as f:
                        f.write(data)
                else:
                    raise RuntimeError(f"Failed to download asset {asset.id}")
            local_files.append(local_path)

        # Create FFmpeg concat list
        list_file_path = os.path.join(temp_dir, "concat_list.txt")
        with open(list_file_path, "w") as f:
            for file in local_files:
                f.write(f"file '{file}'\n")

        # Run FFmpeg to concatenate
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file_path,
            "-c", "copy", output_path
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            raise RuntimeError(f"FFmpeg assembly failed: {stderr.decode()}")

        return output_path
