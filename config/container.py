from core.application.services.script_breakdown_service import ScriptBreakdownService
from core.application.services.animation_orchestrator_service import AnimationOrchestratorService
from infrastructure.providers.motion.comfyui_motion_adapter import ComfyUIMotionAdapter
from infrastructure.providers.lipsync.liveportrait_adapter import LivePortraitAdapter
from infrastructure.compositor.layered_compositor import LayeredCompositor
from config.settings import get_settings

def create_container():
    settings = get_settings()

    # Instantiate providers/adapters
    motion_generator = ComfyUIMotionAdapter(server_address=settings.comfyui_api_url.replace("http://", ""), cache_dir="cache/motion")
    lipsync_generator = LivePortraitAdapter(output_dir="cache/lipsync")
    compositor = LayeredCompositor(output_dir="cache/compositor")

    # Instantiate services
    script_breakdown_service = ScriptBreakdownService()
    animation_orchestrator_service = AnimationOrchestratorService(
        motion_generator=motion_generator,
        lipsync_generator=lipsync_generator,
        compositor=compositor
    )

    return {
        "script_breakdown_service": script_breakdown_service,
        "animation_orchestrator_service": animation_orchestrator_service
    }
