from abc import ABC, abstractmethod

class LipSyncPort(ABC):
    @abstractmethod
    async def generate_lipsync_clip(self, source_image_or_video_path: str, audio_path: str, output_video_path: str) -> str:
        pass
