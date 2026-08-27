import re

with open("server.py", "r") as f:
    code = f.read()

code = code.replace(
    "async def run_pipeline(job_id: str, prompt: str, duration: int, image_path: Optional[str] = None, script_provider: Optional[str] = None, voice_provider: Optional[str] = None, voice_file_path: Optional[str] = None, style: str = \"cinematic\"):",
    "async def run_pipeline(job_id: str, prompt: str, duration: int, image_path: Optional[str] = None, script_provider: Optional[str] = None, voice_provider: Optional[str] = None, voice_file_path: Optional[str] = None, style: str = \"cinematic\", storyboard: bool = False):"
)

injection = """        if style in style_map:
            request_settings.comfyui_workflow_path = style_map[style]

        if storyboard:
            # Bypass slow components for fast drafting
            request_settings.video_generation_provider = "none" # or set to a placeholder static image provider
            request_settings.mastering_enabled = False # skip re-encoding / heavy color grading
            JOB_STATUS[job_id]["message"] = "Storyboard mod aktif: Hızlı taslak oluşturuluyor (Video motoru atlanıyor)..."
"""

old_code = """        if style in style_map:
            request_settings.comfyui_workflow_path = style_map[style]"""

code = code.replace(old_code, injection)

with open("server.py", "w") as f:
    f.write(code)
