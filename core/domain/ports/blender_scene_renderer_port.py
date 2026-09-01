from abc import ABC, abstractmethod
from typing import Any, Dict

from core.domain.value_objects.blender_render_manifest import BlenderRenderManifest


class BlenderSceneRendererPort(ABC):
    """
    Abstract port for rendering scenes in Blender and extracting rendering stats.
    """

    @abstractmethod
    async def render_turntable(
        self, model_path: str, output_dir: str, resolution_profile: str
    ) -> BlenderRenderManifest:
        """
        Renders a 360-degree turntable animation for the specified 3D model.
        """
        raise NotImplementedError

    @abstractmethod
    async def run_benchmark(self, model_path: str) -> Dict[str, Any]:
        """
        Runs rendering benchmarks at multiple resolutions (e.g., 540p, 720p, 1080p).
        Returns a dictionary with benchmark metrics.
        """
        raise NotImplementedError
