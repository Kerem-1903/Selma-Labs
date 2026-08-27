import re

with open("server.py", "r") as f:
    code = f.read()

code = code.replace(
    "async def run_pipeline(job_id: str, prompt: str, duration: int, image_path: Optional[str] = None, script_provider: Optional[str] = None, voice_provider: Optional[str] = None, voice_file_path: Optional[str] = None):",
    "async def run_pipeline(job_id: str, prompt: str, duration: int, image_path: Optional[str] = None, script_provider: Optional[str] = None, voice_provider: Optional[str] = None, voice_file_path: Optional[str] = None, style: str = \"cinematic\"):"
)

injection = """
        if voice_file_path:
            request_settings.voice_clone_reference_path = voice_file_path

        # Handle Visual Styles
        style_map = {
            "cinematic": "assets/comfyui_workflow.json",
            "anime": "assets/comfyui_anime_workflow.json",
            "3d": "assets/comfyui_3d_workflow.json",
            "cyberpunk": "assets/comfyui_cyberpunk_workflow.json"
        }
        if style in style_map:
            request_settings.comfyui_workflow_path = style_map[style]
"""

code = code.replace(
    """        if voice_file_path:
            request_settings.voice_clone_reference_path = voice_file_path""",
    injection.strip()
)

with open("server.py", "w") as f:
    f.write(code)
