from core.domain.ports.keyframe_generation_port import KeyframeGenerationPort
from core.domain.value_objects.generated_keyframe import GeneratedKeyframe
from core.domain.value_objects.keyframe_generation_request import KeyframeGenerationRequest

class ComfyUIKeyframeProvider(KeyframeGenerationPort):
    def __init__(self, settings):
        self.settings = settings

    @property
    def name(self) -> str:
        return "comfyui_keyframe"

    async def generate_keyframe(self, request: KeyframeGenerationRequest) -> GeneratedKeyframe:
        pass
